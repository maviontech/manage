from django.http import JsonResponse, HttpResponseForbidden, HttpResponseBadRequest
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
import json
from asgiref.sync import sync_to_async

# replace with your actual helper imports
from core.db_helpers import get_tenant_conn, exec_sql


@require_GET
def tenant_members(request):
    """
    Return all members in the same tenant.
    Includes the logged-in user at the top as 'Self'.
    Display format: "<LastName> <FirstName> <Email>"
    """
    tenant_conn = get_tenant_conn(request)
    if not tenant_conn:
        return HttpResponseForbidden("No tenant connection")

    # Identify current user
    me_email = getattr(request.user, "emp_code", request.user.username)
    me_display = request.session.get("cn") or request.user.get_full_name() or me_email

    # Fetch all members
    rows = exec_sql(tenant_conn, """
        SELECT id, email, first_name, last_name, phone
        FROM members
        ORDER BY last_name, first_name
    """, [])

    members = []

    # Add self entry first
    members.append({
        "id": me_email,
        "pk": 0,
        "name": f"Self ({me_display})",
        "email": me_email,
        "phone": "",
        "is_self": True,
    })

    # Then add all others
    for r in rows:
        email = (r.get("email") or "").strip()
        if email.lower() == str(me_email).lower():
            continue  # skip duplicate self
        last_name = (r.get("last_name") or "").strip()
        first_name = (r.get("first_name") or "").strip()
        parts = [p for p in [last_name, first_name, f"<{email}>"] if p]
        display_name = " ".join(parts)

        members.append({
            "id": email,
            "pk": r.get("id"),
            "name": display_name,
            "email": email,
            "phone": r.get("phone"),
            "is_self": False,
        })

    return JsonResponse({"members": members})



@require_GET
def conversation_history(request):
    """
    Return conversation messages between current user and peer.
    GET params: ?peer=<emp_code>
    """
    peer = request.GET.get("peer")
    if not peer:
        return HttpResponseBadRequest("Missing 'peer'")
    tenant_conn = get_tenant_conn(request)
    me = getattr(request.user, "emp_code", request.user.username)
    # Use canonical ordering for conversation
    users = sorted([me, peer])
    conv = exec_sql(tenant_conn, """
      SELECT id FROM chat_conversation
      WHERE tenant_id=%s AND user_a=%s AND user_b=%s
      """, [str(request.session.get("tenant_id","")), users[0], users[1]])
    if not conv:
        return JsonResponse({"messages": []})
    conv_id = conv[0]["id"]
    msgs = exec_sql(tenant_conn, """
      SELECT id, sender, text, is_read, created_at
      FROM chat_message
      WHERE conversation_id=%s
      ORDER BY created_at ASC
    """, [conv_id])
    # convert to serializable
    for m in msgs:
        m["created_at"] = m["created_at"].isoformat() if hasattr(m["created_at"], "isoformat") else str(m["created_at"])
    return JsonResponse({"messages": msgs})



@require_POST
def send_message(request):
    """
    HTTP fallback endpoint to send message.
    body: JSON { "to": "<emp_code>", "text": "..." }
    """
    try:
        payload = json.loads(request.body.decode())
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")
    to_user = payload.get("to")
    text = payload.get("text","").strip()
    if not to_user or not text:
        return HttpResponseBadRequest("Missing 'to' or 'text'")
    tenant_conn = get_tenant_conn(request)
    me = getattr(request.user, "emp_code", request.user.username)
    tenant_id = str(request.session.get("tenant_id",""))

    # canonical sorted pair
    a,b = sorted([me, to_user])

    # upsert conversation
    conv_rows = exec_sql(tenant_conn, """
      SELECT id FROM chat_conversation
      WHERE tenant_id=%s AND user_a=%s AND user_b=%s
    """, [tenant_id, a, b])
    if conv_rows:
        conv_id = conv_rows[0]["id"]
    else:
        res = exec_sql(tenant_conn, """
          INSERT INTO chat_conversation (tenant_id, user_a, user_b) VALUES (%s,%s,%s)
        """, [tenant_id, a, b])
        # get last insert id - exec_sql should return inserted ID or we re-query
        conv_rows = exec_sql(tenant_conn, """
          SELECT id FROM chat_conversation
          WHERE tenant_id=%s AND user_a=%s AND user_b=%s
        """, [tenant_id, a, b])
        conv_id = conv_rows[0]["id"]

    # insert message
    exec_sql(tenant_conn, """
      INSERT INTO chat_message (conversation_id, sender, text, is_read) VALUES (%s,%s,%s,0)
    """, [conv_id, me, text])

    # Optionally call a background notifier here (if you have channels, the websocket consumer will handle real-time)
    return JsonResponse({"ok": True})


# chat/views.py (append these handlers)
from django.views.decorators.http import require_POST, require_GET
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
import json

@require_GET
def unread_counts(request):
    """
    Return unread counts for current user grouped by sender.
    Response:
      { "unread": [{ "from": "<email>", "count": 3 }, ...] }
    """
    tenant_conn = get_tenant_conn(request)
    if not tenant_conn:
        return JsonResponse({"unread": []})

    me = getattr(request.user, "emp_code", request.user.username)
    tenant_id = str(request.session.get("tenant_id", ""))

    # Find conversations for this tenant where messages are unread and receiver is me.
    # Since conversation stores two users, find conversations where me appears and unread messages exist from the other side.
    rows = exec_sql(tenant_conn, """
      SELECT m.sender AS `from`, COUNT(*) AS cnt
      FROM chat_conversation c
      JOIN chat_message m ON m.conversation_id = c.id
      WHERE c.tenant_id=%s
        AND m.is_read = 0
        -- message sender is not me
        AND m.sender <> %s
        -- conversation includes me
        AND (c.user_a = %s OR c.user_b = %s)
      GROUP BY m.sender
    """, [tenant_id, me, me, me])

    out = [{"from": r["from"], "count": int(r["cnt"])} for r in rows]
    return JsonResponse({"unread": out})


@require_POST
def mark_read(request):
    """
    Mark messages in conversation between current user and 'peer' as read.
    POST body: { "peer": "<email>" }
    """
    try:
        payload = json.loads(request.body.decode())
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")
    peer = payload.get("peer")
    if not peer:
        return HttpResponseBadRequest("Missing peer")

    tenant_conn = get_tenant_conn(request)
    if not tenant_conn:
        return JsonResponse({"ok": False})

    me = getattr(request.user, "emp_code", request.user.username)
    tenant_id = str(request.session.get("tenant_id", ""))

    a, b = sorted([me, peer])
    conv = exec_sql(tenant_conn, """
      SELECT id FROM chat_conversation WHERE tenant_id=%s AND user_a=%s AND user_b=%s
    """, [tenant_id, a, b])
    if not conv:
        return JsonResponse({"ok": True})  # nothing to mark

    conv_id = conv[0]["id"]
    exec_sql(tenant_conn, """
      UPDATE chat_message SET is_read = 1
      WHERE conversation_id=%s AND sender <> %s AND is_read = 0
    """, [conv_id, me], fetch=False)

    return JsonResponse({"ok": True})

