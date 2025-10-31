# views.py
from django.shortcuts import render, redirect
from django.urls import reverse
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest
from django.core import signing
from django.core.mail import send_mail
from django.utils import timezone
from django.views.decorators.http import require_http_methods
import datetime

# Token config
RESET_TOKEN_SALT = "mavion_password_reset_salt_v1"
RESET_TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24  # 24 hours

#
# --- Helper stubs you MUST adapt to your project ---
#
def get_user_by_email(email):
    """
    Replace with lookup against your user database.
    Should return a user-like object or None. Minimal contract:
      - user.email
      - user.get_domain() or user.email.split('@')[1]
      - optionally: user.last_login
    If you use Django's auth User model, this could be:
      from django.contrib.auth import get_user_model
      User = get_user_model()
      return User.objects.filter(email__iexact=email).first()
    """
    # TODO: Replace with real lookup.
    return None

def authenticate_user(email, password):
    """
    Replace with your authentication check.
    Return True if credentials are valid for given email, else False.
    If using Django auth:
      from django.contrib.auth import authenticate
      user = authenticate(request=None, username=email, password=password)
      return user is not None
    """
    # TODO: Replace with real auth.
    return False

def set_user_password(user, new_password):
    """
    Replace with code to persist new password for user.
    If using Django's auth User model:
      user.set_password(new_password); user.save()
    """
    # TODO: persist password change.
    return

def build_reset_url(request, email):
    """
    Create signed token and build a full URL to password_reset_confirm.
    """
    ts = timezone.now().timestamp()
    payload = {"email": email, "ts": int(ts)}
    token = signing.dumps(payload, salt=RESET_TOKEN_SALT)
    # Use reverse to build relative URL, then make absolute
    rel = reverse("password_reset_confirm") + f"?token={token}"
    host = request.get_host()
    scheme = "https" if request.is_secure() else "http"
    return f"{scheme}://{host}{rel}"

def verify_reset_token(token):
    """
    Return (email) if token valid and not expired, else return None.
    """
    try:
        payload = signing.loads(token, salt=RESET_TOKEN_SALT, max_age=RESET_TOKEN_MAX_AGE_SECONDS)
        email = payload.get("email")
        return email
    except signing.BadSignature:
        return None
    except signing.SignatureExpired:
        return None

def send_reset_email(to_email, reset_url):
    """
    Replace or configure your email sending here.
    This uses Django's send_mail configured via settings.EMAIL_BACKEND.
    """
    subject = "Reset your MavionTech password"
    message = f"Hi,\n\nA request was received to reset your password. Click the link below to set a new password (link valid for 24 hours):\n\n{reset_url}\n\nIf you didn't request this, ignore this email.\n\nRegards,\nMavionTech"
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@{host}".format(host=getattr(settings, "DEFAULT_HOST", "example.com")))
    send_mail(subject, message, from_email, [to_email], fail_silently=False)

#
# --- Views ---
#

@require_http_methods(["GET", "POST"])
def identify_view(request):
    """
    Collect email and forward to login step.
    Matches the identify.html frontend.
    """
    error = None
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        if not email:
            error = "Email is required."
        else:
            # Basic server-side validation
            if "@" not in email:
                error = "Enter a valid email address."
            else:
                # Save email in session and go to login view
                request.session["auth_email"] = email
                # If you need domain split:
                request.session["auth_domain"] = email.split("@", 1)[1].lower()
                return redirect("login")
    return render(request, "identify.html", {"error": error})

@require_http_methods(["GET", "POST"])
def login_view(request):
    """
    Login page that expects email in session (from identify) or GET param.
    """
    error = None
    email = request.session.get("auth_email") or request.GET.get("email", "")
    domain = email.split("@",1)[1] if "@" in email else ""
    last_login = None
    # If you have user object and can show last_login, supply it here
    user = get_user_by_email(email) if email else None
    if user and hasattr(user, "last_login"):
        last_login = user.last_login

    if request.method == "POST":
        password = request.POST.get("password", "")
        if not password:
            error = "Password is required."
        else:
            if authenticate_user(email, password):
                # On success: clear session keys and redirect to your app home
                request.session.pop("auth_email", None)
                request.session.pop("auth_domain", None)
                # TODO: set your login/session as appropriate
                # e.g., request.session['logged_in_user'] = email
                # redirect to dashboard/home
                return redirect("/")  # change to your landing page
            else:
                error = "Invalid credentials. Please try again."

    return render(request, "login.html", {"email": email, "domain": domain, "error": error, "last_login": last_login})

@require_http_methods(["GET", "POST"])
def password_reset_request_view(request):
    """
    User enters email to receive password reset link.
    For security, do not reveal whether the email exists.
    """
    error = None
    message = None

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        if not email:
            error = "Email is required."
        else:
            # Always show a neutral message — whether or not the user exists.
            message = "If that email address is registered, you will receive a password reset link shortly."

            # Attempt to find user and send email if found
            user = get_user_by_email(email)
            if user:
                try:
                    reset_url = build_reset_url(request, email)
                    send_reset_email(email, reset_url)
                    # optionally log the event
                except Exception as ex:
                    # If mail sending fails, we still show neutral message but log for debugging
                    # In production, use logging: logger.exception(...)
                    print("Failed to send reset email:", ex)

    return render(request, "core/password_reset_request.html", {"error": error, "message": message})

@require_http_methods(["GET", "POST"])
def password_reset_confirm_view(request):
    """
    User navigates here from the emailed link (token in query param).
    Presents new password form and applies change when token valid.
    """
    token = request.GET.get("token") or request.POST.get("token")
    if not token:
        return HttpResponseBadRequest("Missing token.")

    email = verify_reset_token(token)
    if not email:
        # token invalid/expired
        return render(request, "password_reset_confirm.html", {"error": "Invalid or expired reset link. Please request a new link.", "email": ""})

    # lookup user
    user = get_user_by_email(email)
    if not user:
        # shouldn't happen if token was issued for a valid user, but guard anyway
        return render(request, "password_reset_confirm.html", {"error": "Could not find user for reset link.", "email": email})

    if request.method == "POST":
        new_pw = request.POST.get("password", "")
        confirm = request.POST.get("confirm", "")
        if not new_pw or len(new_pw) < 8:
            return render(request, "password_reset_confirm.html", {"error": "Password must be at least 8 characters.", "email": email, "token": token})
        if new_pw != confirm:
            return render(request, "password_reset_confirm.html", {"error": "Passwords do not match.", "email": email, "token": token})
        # Good: apply password change
        try:
            set_user_password(user, new_pw)
            # Optionally: revoke other sessions, notify user by email that password changed
            message = "Your password has been updated. You may now sign in."
            return render(request, "password_reset_confirm.html", {"message": message, "email": email})
        except Exception as ex:
            return render(request, "password_reset_confirm.html", {"error": "Failed to update password. Try again or contact admin.", "email": email, "token": token})

    # GET -> show form
    return render(request, "password_reset_confirm.html", {"email": email, "token": token})
