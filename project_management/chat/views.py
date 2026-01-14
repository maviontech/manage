# chat/views.py


from django.http import JsonResponse, HttpResponseForbidden, HttpResponseBadRequest
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect
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
    # Check authentication - redirect to login if not authenticated
    member_id = request.session.get('member_id')
    if not member_id:
        return redirect('login_password')
    
    # Check tenant configuration
    tenant_config = request.session.get('tenant_config')
    if not tenant_config:
        return redirect('identify')
    
    tenant_id = request.session.get('tenant_id', '')
    
    # Validate tenant_id - if missing, redirect to identify page
    if not tenant_id or tenant_id == 'None':
        logging.warning(f"Missing or invalid tenant_id in session for member {member_id}")
        return redirect('identify')
    
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
    # Check authentication
    if not request.session.get('member_id'):
        return HttpResponseForbidden("Not authenticated")
    
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
    # Check authentication
    if not request.session.get('member_id'):
        return HttpResponseForbidden("Not authenticated")
       
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
    # Check authentication
    if not request.session.get('member_id'):
        return HttpResponseForbidden("Not authenticated")
    
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
    # Check authentication
    if not request.session.get('member_id'):
        return JsonResponse({"unread": []})
    
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
    # Check authentication
    if not request.session.get('member_id'):
        return HttpResponseForbidden("Not authenticated")
    
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
    ids = []

    while True:
        try:
            logger.info(f"mark_read updating messages for conv_id={conv_id}, me={me}")
            # collect ids that will be marked so we can notify senders
            ids_rows = exec_sql(tenant_conn, """
                SELECT id FROM chat_message
                WHERE conversation_id=%s AND sender <> %s AND is_read = 0
            """, [conv_id, me])
            if ids_rows:
                ids = [r.get('id') for r in ids_rows if r.get('id')]

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
    # Notify via channel layer so other participants (senders) can see receipts in real-time
    try:
        if total_updated > 0 and ids:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            layer = get_channel_layer()
            payload = {
                'type': 'chat.message_read',
                'event': 'message_read',
                'conversation_id': conv_id,
                'message_ids': ids,
            }
            room = f'chat_{tenant_id}_{a}_{b}'
            async_to_sync(layer.group_send)(room, payload)
    except Exception:
        # best-effort: if channels aren't configured, ignore
        pass
    return JsonResponse({"ok": True})


# ---- Group (thread) support (server-backed) ----
def _ensure_group_tables(tenant_conn):
    """Create group-related tables if they do not exist."""
    try:
        exec_sql(tenant_conn, """
            CREATE TABLE IF NOT EXISTS chat_group (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                tenant_id VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                created_by VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """, [], fetch=False)

        exec_sql(tenant_conn, """
            CREATE TABLE IF NOT EXISTS chat_group_member (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                group_id BIGINT NOT NULL,
                member VARCHAR(255) NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX (group_id),
                INDEX (member)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """, [], fetch=False)

        exec_sql(tenant_conn, """
            CREATE TABLE IF NOT EXISTS chat_group_message (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                group_id BIGINT NOT NULL,
                sender VARCHAR(255) NOT NULL,
                text TEXT,
                is_read TINYINT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX (group_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """, [], fetch=False)
        exec_sql(tenant_conn, """
            CREATE TABLE IF NOT EXISTS chat_group_read (
                id BIGINT PRIMARY KEY AUTO_INCREMENT,
                group_id BIGINT NOT NULL,
                member VARCHAR(255) NOT NULL,
                last_read_at TIMESTAMP NULL,
                INDEX (group_id),
                INDEX (member)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """, [], fetch=False)
    except Exception:
        # best-effort creation; if it fails, higher-level handlers will return errors
        pass


@require_GET
def groups_list(request):
    """Return list of groups for current tenant.

    Response: { groups: [{ id, name, created_by, member_count }, ...] }
    """
    # Check authentication
    if not request.session.get('member_id'):
        return JsonResponse({"groups": []})
    
    tenant_conn = get_tenant_conn(request)
    if not tenant_conn:
        return JsonResponse({"groups": []})
    tenant_id = str(request.session.get('tenant_id', ''))
    _ensure_group_tables(tenant_conn)

    # fetch groups
    rows = exec_sql(tenant_conn, """
        SELECT g.id, g.name, g.created_by
        FROM chat_group g
        WHERE g.tenant_id=%s
        ORDER BY g.created_at DESC
    """, [tenant_id])

    # resolve current user for unread calculations
    me_raw = (request.session.get('ident_email') or getattr(request.user, 'email', None)) or request.session.get('member_id')
    me = _normalize_identity(tenant_conn, me_raw)

    out = []
    for r in rows:
        gid = int(r.get('id'))
        # members
        mems = exec_sql(tenant_conn, """
            SELECT member FROM chat_group_member WHERE group_id=%s
        """, [gid])
        members = [m.get('member') for m in mems if m.get('member')]

        # unread: count messages where created_at > last_read_at (per-member)
        last_read = exec_sql(tenant_conn, """
            SELECT last_read_at FROM chat_group_read WHERE group_id=%s AND member=%s ORDER BY id DESC LIMIT 1
        """, [gid, me])
        if last_read and last_read[0].get('last_read_at'):
            lr = last_read[0]['last_read_at']
            unread_rows = exec_sql(tenant_conn, """
                SELECT COUNT(*) AS cnt FROM chat_group_message WHERE group_id=%s AND created_at > %s AND sender <> %s
            """, [gid, lr, me])
            unread = int(unread_rows[0].get('cnt') or 0) if unread_rows else 0
        else:
            unread_rows = exec_sql(tenant_conn, """
                SELECT COUNT(*) AS cnt FROM chat_group_message WHERE group_id=%s AND sender <> %s
            """, [gid, me])
            unread = int(unread_rows[0].get('cnt') or 0) if unread_rows else 0

        out.append({
            "id": gid,
            "name": r.get('name'),
            "created_by": r.get('created_by'),
            "member_count": len(members),
            "members": members,
            "unread": unread,
        })
    return JsonResponse({"groups": out})


@require_POST
def create_group(request):
    """Create a new group. JSON body: { name: str, members: [<id_or_email>, ...] }

    Returns: { ok: True, group: { id, name } }
    """
    # Check authentication
    if not request.session.get('member_id'):
        return HttpResponseForbidden("Not authenticated")
    
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest('Invalid JSON')

    name = (payload.get('name') or '').strip()
    members = payload.get('members') or []
    if not name:
        return HttpResponseBadRequest('Missing group name')

    tenant_conn = get_tenant_conn(request)
    if not tenant_conn:
        return HttpResponseForbidden('No tenant')

    _ensure_group_tables(tenant_conn)

    # creator identity
    me_raw = (request.session.get('ident_email') or getattr(request.user, 'email', None)) or request.session.get('member_id')
    me = _normalize_identity(tenant_conn, me_raw)
    tenant_id = str(request.session.get('tenant_id', ''))

    # insert group
    exec_sql(tenant_conn, """
        INSERT INTO chat_group (tenant_id, name, created_by) VALUES (%s, %s, %s)
    """, [tenant_id, name, me])

    row = exec_sql(tenant_conn, """
        SELECT id FROM chat_group WHERE tenant_id=%s AND name=%s ORDER BY id DESC LIMIT 1
    """, [tenant_id, name])
    if not row:
        return JsonResponse({"ok": False, "error": "insert_failed"}, status=500)
    group_id = int(row[0]['id'])

    # add members
    for m in members:
        try:
            mem = _normalize_identity(tenant_conn, m)
            if mem:
                exec_sql(tenant_conn, """
                    INSERT INTO chat_group_member (group_id, member) VALUES (%s, %s)
                """, [group_id, mem])
        except Exception:
            continue

    # ensure creator is a member as well
    try:
        exec_sql(tenant_conn, """
            INSERT INTO chat_group_member (group_id, member) SELECT %s, %s FROM DUAL
            WHERE NOT EXISTS (SELECT 1 FROM chat_group_member WHERE group_id=%s AND member=%s)
        """, [group_id, me, group_id, me])
    except Exception:
        pass

    return JsonResponse({"ok": True, "group": {"id": group_id, "name": name}})


@require_GET
def group_history(request):
    """Return messages for a group. GET param: ?group_id=<id>
    Response: { messages: [{ id, sender, text, created_at }, ...] }
    """
    # Check authentication
    if not request.session.get('member_id'):
        return HttpResponseForbidden("Not authenticated")
    
    group_id = request.GET.get('group_id')
    if not group_id:
        return HttpResponseBadRequest('Missing group_id')
    tenant_conn = get_tenant_conn(request)
    if not tenant_conn:
        return HttpResponseForbidden('No tenant')

    _ensure_group_tables(tenant_conn)

    msgs = exec_sql(tenant_conn, """
        SELECT id, sender, text, is_read, created_at
        FROM chat_group_message
        WHERE group_id=%s
        ORDER BY created_at ASC
    """, [int(group_id)])

    for m in msgs:
        m["created_at"] = m["created_at"].isoformat() if hasattr(m["created_at"], "isoformat") else str(m["created_at"])
    return JsonResponse({"messages": msgs})


@require_POST
def group_send(request):
    """Send a message to a group. JSON body: { group_id: <id>, text: <str> }

    Returns: { ok: True }
    """
    # Check authentication
    if not request.session.get('member_id'):
        return HttpResponseForbidden("Not authenticated")
    
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest('Invalid JSON')

    group_id = payload.get('group_id')
    text = (payload.get('text') or '').strip()
    if not group_id or not text:
        return HttpResponseBadRequest('Missing group_id or text')

    tenant_conn = get_tenant_conn(request)
    if not tenant_conn:
        return HttpResponseForbidden('No tenant')

    _ensure_group_tables(tenant_conn)

    me_raw = (request.session.get('ident_email') or getattr(request.user, 'email', None)) or request.session.get('member_id')
    me = _normalize_identity(tenant_conn, me_raw)

    try:
        exec_sql(tenant_conn, """
            INSERT INTO chat_group_message (group_id, sender, text, is_read) VALUES (%s, %s, %s, 0)
        """, [int(group_id), me, text])
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)

    # Broadcast to channels layer so connected websocket clients receive the message
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        from datetime import datetime
        layer = get_channel_layer()
        now_iso = datetime.utcnow().isoformat()
        payload = {
            'type': 'chat.message',
            'event': 'message',
            'message': {
                'sender': me,
                'text': text,
                'created_at': now_iso,
                'group_id': int(group_id),
            }
        }
        async_to_sync(layer.group_send)(f'chat_group_{tenant_id}_{int(group_id)}', payload)
    except Exception:
        # channels not configured or error sending: ignore (polling still works)
        pass

    return JsonResponse({"ok": True})


@require_POST
def mark_group_read(request):
    """Mark group as read for current user. JSON body: { group_id: <id> }"""
    # Check authentication
    if not request.session.get('member_id'):
        return HttpResponseForbidden("Not authenticated")
    
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest('Invalid JSON')
    group_id = payload.get('group_id')
    if not group_id:
        return HttpResponseBadRequest('Missing group_id')
    tenant_conn = get_tenant_conn(request)
    if not tenant_conn:
        return HttpResponseForbidden('No tenant')
    _ensure_group_tables(tenant_conn)

    me_raw = (request.session.get('ident_email') or getattr(request.user, 'email', None)) or request.session.get('member_id')
    me = _normalize_identity(tenant_conn, me_raw)
    try:
        exec_sql(tenant_conn, """
            INSERT INTO chat_group_read (group_id, member, last_read_at) VALUES (%s, %s, NOW())
        """, [int(group_id), me], fetch=False)
    except Exception:
        try:
            exec_sql(tenant_conn, """
                UPDATE chat_group_read SET last_read_at=NOW() WHERE group_id=%s AND member=%s
            """, [int(group_id), me], fetch=False)
        except Exception:
            pass
    return JsonResponse({"ok": True})


@require_POST
def group_update(request):
    """Perform group settings actions: rename, add_member, remove_member.
    JSON body: { group_id: id, action: 'rename'|'add_member'|'remove_member', value: ... }
    """
    # Check authentication
    if not request.session.get('member_id'):
        return HttpResponseForbidden("Not authenticated")
    
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except Exception:
        return HttpResponseBadRequest('Invalid JSON')
    group_id = payload.get('group_id')
    action = payload.get('action')
    value = payload.get('value')
    if not group_id or not action:
        return HttpResponseBadRequest('Missing params')
    tenant_conn = get_tenant_conn(request)
    if not tenant_conn:
        return HttpResponseForbidden('No tenant')
    _ensure_group_tables(tenant_conn)

    # basic actions
    try:
        if action == 'rename':
            name = (value or '').strip()
            if not name:
                return HttpResponseBadRequest('Missing name')
            exec_sql(tenant_conn, """
                UPDATE chat_group SET name=%s WHERE id=%s
            """, [name, int(group_id)], fetch=False)
            return JsonResponse({"ok": True})
        elif action == 'add_member':
            mem = _normalize_identity(tenant_conn, value)
            if not mem:
                return HttpResponseBadRequest('Invalid member')
            exec_sql(tenant_conn, """
                INSERT INTO chat_group_member (group_id, member) SELECT %s, %s FROM DUAL
                WHERE NOT EXISTS (SELECT 1 FROM chat_group_member WHERE group_id=%s AND member=%s)
            """, [int(group_id), mem, int(group_id), mem], fetch=False)
            return JsonResponse({"ok": True})
        elif action == 'remove_member':
            mem = _normalize_identity(tenant_conn, value)
            if not mem:
                return HttpResponseBadRequest('Invalid member')
            exec_sql(tenant_conn, """
                DELETE FROM chat_group_member WHERE group_id=%s AND member=%s
            """, [int(group_id), mem], fetch=False)
            return JsonResponse({"ok": True})
        else:
            return HttpResponseBadRequest('Unknown action')
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@require_POST
def mark_all_read(request):
    """Mark all chat notifications (DMs and groups) as read for current user."""
    # Check authentication
    if not request.session.get('member_id'):
        return HttpResponseForbidden("Not authenticated")
    
    tenant_conn = get_tenant_conn(request)
    if not tenant_conn:
        return HttpResponseForbidden('No tenant')

    me_raw = (request.session.get('ident_email') or getattr(request.user, 'email', None)) or request.session.get('member_id')
    me = _normalize_identity(tenant_conn, me_raw)
    tenant_id = str(request.session.get('tenant_id', ''))

    try:
        # mark DM messages as read where receiver is me
        exec_sql(tenant_conn, """
            UPDATE chat_message m
            JOIN chat_conversation c ON m.conversation_id = c.id
            SET m.is_read = 1
            WHERE c.tenant_id=%s AND m.is_read = 0 AND m.sender <> %s AND (c.user_a = %s OR c.user_b = %s)
        """, [tenant_id, me, me, me], fetch=False)

        # mark all groups where I'm a member as read by inserting/updating chat_group_read
        groups = exec_sql(tenant_conn, """
            SELECT group_id FROM chat_group_member WHERE member=%s
        """, [me])
        for g in groups:
            gid = g.get('group_id') or g.get('group_id')
            if not gid:
                continue
            try:
                exec_sql(tenant_conn, """
                    INSERT INTO chat_group_read (group_id, member, last_read_at)
                    SELECT %s, %s, NOW() FROM DUAL
                    WHERE NOT EXISTS (SELECT 1 FROM chat_group_read WHERE group_id=%s AND member=%s)
                """, [gid, me, gid, me], fetch=False)
                exec_sql(tenant_conn, """
                    UPDATE chat_group_read SET last_read_at=NOW() WHERE group_id=%s AND member=%s
                """, [gid, me], fetch=False)
            except Exception:
                continue

    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)

    return JsonResponse({"ok": True})
