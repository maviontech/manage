# views.py
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from core.auth import identify_tenant_by_email, authenticate
from core.tenant_context import set_current_tenant, get_current_tenant
from core.db_connector import get_connection_from_config

def identify_view(request):
    if request.method == 'GET':
        return render(request, 'core/identify.html', {})
    email = request.POST.get('email','').strip()
    if not email or '@' not in email:
        return render(request, 'core/identify.html', {'error': 'Enter a valid email.'})
    tenant = identify_tenant_by_email(email)
    if not tenant:
        return render(request, 'core/identify.html', {'error': 'No tenant found for this email domain.'})
    # store tenant row (dict) in session
    request.session['tenant_config'] = {
        'db_engine': tenant.get('db_engine', 'mysql'),
        'db_name': tenant.get('db_name'),
        'db_host': tenant.get('db_host') or '127.0.0.1',
        'db_port': tenant.get('db_port') or 3306,
        'db_user': tenant.get('db_user'),
        'db_password': tenant.get('db_password'),
        'domain_postfix': tenant.get('domain_postfix')
    }
    request.session['ident_email'] = email
    return redirect('login_password')

def login_password_view(request):
    if request.method == 'GET':
        if not request.session.get('tenant_config') or not request.session.get('ident_email'):
            return redirect('identify')
        return render(request, 'core/login.html', {
            'email': request.session.get('ident_email'),
            'domain': request.session['tenant_config'].get('domain_postfix')
        })

    email = request.session.get('ident_email')
    tenant_conf = request.session.get('tenant_config')
    password = request.POST.get('password', '')

    if not email or not tenant_conf:
        return redirect('identify')

    try:
        user = authenticate(email, password, tenant_conf)
    except Exception as e:
        return render(request, 'core/login.html', {'email': email, 'error': 'Auth error: ' + str(e)})

    if not user:
        return render(request, 'core/login.html', {'email': email, 'error': 'Invalid credentials'})

    # ✅ Auth success
    request.session['user'] = user

    # ✅ Ensure tenant_config present
    request.session['tenant_config'] = tenant_conf
    set_current_tenant(tenant_conf)

    # ✅ Add explicit tenant connection info for db_helpers.py
    request.session['tenant_db_name'] = tenant_conf.get('db_name')
    request.session['tenant_db_user'] = tenant_conf.get('db_user')
    request.session['tenant_db_password'] = tenant_conf.get('db_password')
    request.session['tenant_db_host'] = tenant_conf.get('db_host', '127.0.0.1')
    request.session['tenant_db_port'] = tenant_conf.get('db_port', 3306)

    return redirect('dashboard')


def logout_view(request):
    request.session.flush()
    return redirect('identify')

def dashboard_view(request):
    tenant = get_current_tenant() or request.session.get('tenant_config')
    if not tenant:
        return redirect('identify')
    user = request.session.get('user')
    conn = get_connection_from_config({
        'db_engine': tenant.get('db_engine','mysql'),
        'db_name': tenant.get('db_name'),
        'db_host': tenant.get('db_host'),
        'db_port': tenant.get('db_port'),
        'db_user': tenant.get('db_user'),
        'db_password': tenant.get('db_password')
    })
    cur = conn.cursor()
    assigned_count = 0
    if user:
        cur.execute("SELECT COUNT(*) AS c FROM tasks WHERE assigned_to = %s", (user['id'],))
        r = cur.fetchone()
        assigned_count = r['c'] if r and 'c' in r else (r[0] if r else 0)
    cur.close()
    conn.close()
    return render(request, 'core/dashboard.html', {'user': user, 'assigned_count': assigned_count})
