# chat/views.py


from django.http import JsonResponse, HttpResponseForbidden, HttpResponseBadRequest
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render
import json
from asgiref.sync import sync_to_async

# replace with your actual helper imports
from core.db_helpers import get_tenant_conn, exec_sql
import time
import logging
import pymysql
import logging

def team_chat_page(request, peer_id=None):
    """
    Render the full-page Slack-style team chat UI.
    """
    tenant_id = request.session.get('tenant_id', '') 
    tenant_name = request.session.get('tenant_name', 'Team Chat')
    # Prefer email/ident_email as canonical identity for chat; fall back to member_id if no email
    def _chat_identity(req):
        ident = req.session.get('ident_email') or getattr(req.user, 'email', None)
        if ident:
            return str(ident).strip()
        # fall back to member_id (numeric) if no email available
        return str(req.session.get('member_id') or '').strip()

    current_user = _chat_identity(request)
    current_user_name = str(request.session.get('member_name') or request.session.get('cn') or getattr(request.user, 'get_full_name', lambda: '')() or current_user).strip()
    
    return render(request, 'core/team_chat.html', {
        'tenant_id': tenant_id,
        'tenant_name': tenant_name,
        'current_user': current_user,
        'current_user_name': current_user_name,
        'initial_peer': str(peer_id or '').strip(),

    })


def _normalize_identity(tenant_conn, val):
    """If val looks like a numeric member id, try to resolve to member email.
       Otherwise return val as-is (string). Returns string.
    """
    if val is None:
        return ''
    s = str(val).strip()
    if not s:
        return ''
    # if purely numeric, try lookup
    if s.isdigit():
        try:
            row = exec_sql(tenant_conn, "SELECT email FROM members WHERE id=%s", [int(s)])
            if row and row[0].get('email'):
                return str(row[0]['email']).strip().lower()
        except Exception:
            pass
    return s.lower()


@require_GET
def tenant_members(request):
    tenant_conn = get_tenant_conn(request)
    if not tenant_conn:
        return HttpResponseForbidden("No tenant connection")
    # prefer numeric member_id for client-side identifiers
    me_pk = request.session.get('member_id')
    me_id = (request.session.get('ident_email') or getattr(request.user, 'email', None)) or me_pk
    me_id = str(me_id).strip() if me_id is not None else ''
    me_name = str(request.session.get('member_name') or request.session.get('cn') or getattr(request.user, 'get_full_name', lambda: "")())

    rows = exec_sql(tenant_conn, """
        SELECT id, email, first_name, last_name, phone
        FROM members
        ORDER BY last_name, first_name
    """, [])

    members = []
    if me_pk:
        members.append({
            "id": int(me_pk),
            "pk": int(me_pk),
            "name": f"Self ({me_name}) <{me_id}>",
            "email": me_id if isinstance(me_id, str) else "",
            "phone": "",
            "is_self": True,
        })

    for r in rows:
        email = (r.get("email") or "").strip()
        pk = r.get("id")
        if not pk:
            continue
        if me_pk and int(pk) == int(me_pk):
            continue
        last_name = (r.get("last_name") or "").strip()
        first_name = (r.get("first_name") or "").strip()
        display = " ".join(p for p in (last_name, first_name, f"<{email}>") if p)
        members.append({
            "id": int(pk),
            "pk": pk,
            "name": display,
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
       
    logger = logging.getLogger(__name__)
    peer = request.GET.get("peer")
    if not peer:
            logger.error("conversation_history: Missing 'peer' param")
            return HttpResponseBadRequest("Missing 'peer'")
    tenant_conn = get_tenant_conn(request)
    me_raw = (request.session.get('ident_email') or getattr(request.user, 'email', None)) or request.session.get('member_id')
    me = _normalize_identity(tenant_conn, me_raw)
    peer = _normalize_identity(tenant_conn, peer)
    users = sorted([me, peer])
    logger.info(f"conversation_history: me={me}, peer={peer}, users(sorted)={users}")
    conv = exec_sql(tenant_conn, """
        SELECT id FROM chat_conversation
        WHERE tenant_id=%s AND user_a=%s AND user_b=%s
        """, [str(request.session.get("tenant_id","")), users[0], users[1]])
    logger.info(f"conversation_history: conversation lookup result: {conv}")
    if not conv:
            logger.warning(f"conversation_history: No conversation found for users {users}")
            return JsonResponse({"messages": []})
    conv_id = conv[0]["id"]
    msgs = exec_sql(tenant_conn, """
        SELECT id, sender, text, is_read, created_at
        FROM chat_message
        WHERE conversation_id=%s
        ORDER BY created_at ASC
    """, [conv_id])
    for m in msgs:
            m["created_at"] = m["created_at"].isoformat() if hasattr(m["created_at"], "isoformat") else str(m["created_at"])
    logger.info(f"conversation_history: Returning {len(msgs)} messages for conv_id={conv_id}")
    return JsonResponse({"messages": msgs})



@require_POST
def send_message(request):
    """HTTP fallback endpoint to send a message. Expects JSON body { to, text }."""
    try:
        payload = json.loads(request.body.decode())
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    to_user = payload.get("to")
    text = payload.get("text", "").strip()
    if not to_user or not text:
        return HttpResponseBadRequest("Missing 'to' or 'text'")

    tenant_conn = get_tenant_conn(request)
    logger = logging.getLogger(__name__)

    # Normalize identities to canonical form (prefer email)
    me_raw = (request.session.get('ident_email') or getattr(request.user, 'email', None)) or request.session.get('member_id')
    me = _normalize_identity(tenant_conn, me_raw)
    to_user = _normalize_identity(tenant_conn, to_user)
    tenant_id = str(request.session.get("tenant_id", ""))

    # canonical sorted pair
    a, b = sorted([me, to_user])
    logger.info(f"send_message: me={me}, to_user={to_user}, tenant_id={tenant_id}, pair=({a},{b})")

    # upsert conversation
    conv_rows = exec_sql(tenant_conn, """
      SELECT id FROM chat_conversation
      WHERE tenant_id=%s AND user_a=%s AND user_b=%s
    """, [tenant_id, a, b])
    if conv_rows:
        conv_id = conv_rows[0]["id"]
    else:
        exec_sql(tenant_conn, """
          INSERT INTO chat_conversation (tenant_id, user_a, user_b) VALUES (%s,%s,%s)
        """, [tenant_id, a, b])
        conv_rows = exec_sql(tenant_conn, """
          SELECT id FROM chat_conversation
          WHERE tenant_id=%s AND user_a=%s AND user_b=%s
        """, [tenant_id, a, b])
        conv_id = conv_rows[0]["id"]

    # always insert message
    exec_sql(tenant_conn, """
        INSERT INTO chat_message (conversation_id, sender, text, is_read) VALUES (%s,%s,%s,0)
    """, [conv_id, me, text])
    logger.info(f"send_message: inserted message into conv_id={conv_id}")

    # Optionally notify via websocket/consumer
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
    # Resolve same identity as UI/session
    me_raw = (request.session.get('ident_email') or getattr(request.user, 'email', None)) or request.session.get('member_id')
    me = _normalize_identity(tenant_conn, me_raw)
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
    Accepts JSON body: { "peer": "<email>" }
    Also accepts form-encoded POST (peer param) for robustness.
    """
    import logging
    logger = logging.getLogger(__name__)
    tenant_conn = get_tenant_conn(request)
    if not tenant_conn:
        logger.error("No tenant connection in mark_read")
        return JsonResponse({"ok": False, "error": "no_tenant"}, status=400)

    # Try JSON first
    peer = None
    try:
        body = request.body.decode('utf-8').strip()
        logger.info(f"mark_read request body: {body}")
        if body:
            payload = json.loads(body)
            peer = payload.get("peer")
    except Exception as e:
        logger.warning(f"mark_read JSON decode failed: {e}")
        peer = None

    # Fallback to form POST (application/x-www-form-urlencoded) or POST param
    if not peer:
        peer = request.POST.get("peer") or request.GET.get("peer")

    logger.info(f"mark_read peer resolved: {peer}")
    if not peer:
        logger.error("Missing peer in mark_read")
        return JsonResponse({"ok": False, "error": "missing_peer"}, status=400)

    # Now do the normal logic; resolve identity from session like the UI
    me_raw = (request.session.get('ident_email') or getattr(request.user, 'email', None)) or request.session.get('member_id')
    me = _normalize_identity(tenant_conn, me_raw)
    tenant_id = str(request.session.get("tenant_id", ""))
    logger.info(f"mark_read me: {me}, tenant_id: {tenant_id}")

    peer = _normalize_identity(tenant_conn, peer)
    a, b = sorted([me, peer])
    conv = exec_sql(tenant_conn, """
      SELECT id FROM chat_conversation WHERE tenant_id=%s AND user_a=%s AND user_b=%s
    """, [tenant_id, a, b])
    logger.info(f"mark_read found conversation: {conv}")
    if not conv:
        logger.info("No conversation found to mark as read")
        return JsonResponse({"ok": True})  # nothing to mark

    conv_id = conv[0]["id"]

    # Perform updates in small batches to reduce lock contention and avoid
    # InnoDB lock wait timeouts when many rows must be updated at once.
    batch_size = 500
    max_retries = 3
    total_updated = 0

    while True:
        try:
            logger.info(f"mark_read updating messages for conv_id={conv_id}, me={me}")
            exec_sql(tenant_conn, """
                UPDATE chat_message
                SET is_read = 1
                WHERE conversation_id=%s AND sender <> %s AND is_read = 0
                """, [conv_id, me], fetch=False)
            rows_affected = tenant_conn.cursor().rowcount



            try:
                updated = int(rows_affected or 0)
            except Exception:
                updated = 0

            total_updated += updated
            logger.info(f"mark_read updated {updated} messages, total_updated={total_updated}")
            if updated == 0:
                break

            # pause briefly to yield locks if there's contention
            time.sleep(0.05)
        except pymysql.err.OperationalError as oe:
            logger.warning(f'mark_read OperationalError, retrying: {oe}')
            max_retries -= 1
            if max_retries <= 0:
                logger.exception('mark_read failed after retries')
                return JsonResponse({"ok": False, "error": "db_lock_timeout"}, status=500)
            time.sleep(0.2)
            continue
        except Exception as e:
            logger.exception(f'mark_read unexpected error: {e}')
            return JsonResponse({"ok": False, "error": "internal_error"}, status=500)

    logger.info(f"mark_read finished, total_updated={total_updated}")
    return JsonResponse({"ok": True})
