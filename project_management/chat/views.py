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
    Display format: "<LastName> <FirstName> <Email>"
    """
    tenant_conn = get_tenant_conn(request)
    if not tenant_conn:
        return HttpResponseForbidden("No tenant connection")

    # Fetch all members
    rows = exec_sql(tenant_conn, """
        SELECT id, email, first_name, last_name, phone
        FROM members
        ORDER BY last_name, first_name
    """, [])

    members = []
    for r in rows:
        last_name = (r.get("last_name") or "").strip()
        first_name = (r.get("first_name") or "").strip()
        email = (r.get("email") or "").strip()

        # Construct display name "<LastName> <FirstName> <Email>"
        parts = [p for p in [last_name, first_name, f"<{email}>"] if p]
        display_name = " ".join(parts)

        members.append({
            "id": email,           # email used as chat identifier
            "pk": r.get("id"),     # numeric member id
            "name": display_name,  # formatted name
            "phone": r.get("phone"),
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
from django.shortcuts import render

# Create your views here.
