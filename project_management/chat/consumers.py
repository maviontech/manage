import json
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from urllib.parse import parse_qs
from asgiref.sync import sync_to_async
from django.utils import timezone

# import your helpers - adjust path if necessary
from core.db_helpers import exec_sql, get_tenant_conn


def _normalize_identity_for_tenant(tenant_conn, val):
    """Resolve numeric member id to email when possible and lowercase."""
    if val is None:
        return ''
    s = str(val).strip()
    if not s:
        return ''
    if s.isdigit():
        try:
            row = exec_sql(tenant_conn, "SELECT email FROM members WHERE id=%s", [int(s)])
            if row and row[0].get('email'):
                return str(row[0]['email']).strip().lower()
        except Exception:
            pass
    return s.lower()


class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        print(f"[ChatConsumer.connect] user={user}, is_authenticated={getattr(user, 'is_authenticated', False)}")
        if not user or not getattr(user, 'is_authenticated', False):
            print("[ChatConsumer.connect] REJECT: User not authenticated")
            await self.close()
            return

        qs = parse_qs(self.scope.get('query_string', b'').decode())
        tenant = qs.get('tenant', [None])[0]
        print(f"[ChatConsumer.connect] tenant={tenant}, query_string={self.scope.get('query_string', b'').decode()}")
        if not tenant:
            print("[ChatConsumer.connect] REJECT: No tenant parameter")
            await self.close()
            return

        # Get current user identity from session
        session = self.scope.get('session', {})
        self.me = str(session.get('ident_email') or session.get('member_name') or session.get('cn') or getattr(user, 'email', '') or getattr(user, 'username', ''))
        
        # Get member name for display
        self.my_name = session.get('cn') or session.get('member_name') or getattr(user, 'username', 'User')

        # normalize using tenant DB (best-effort)
        try:
            tenant_conn = get_tenant_conn(tenant_id=tenant)
            self.me = _normalize_identity_for_tenant(tenant_conn, self.me)
        except Exception:
            self.me = str(self.me).strip().lower()

        # Tenant-wide presence group for this tenant
        self.presence_group = f'presence_{tenant}'
        self.tenant_id = tenant

        # Join presence group
        await self.channel_layer.group_add(self.presence_group, self.channel_name)
        await self.accept()

        # Announce user is online
        await self.channel_layer.group_send(
            self.presence_group,
            {
                'type': 'presence_update',
                'status': 'online',
                'user_id': session.get('member_id'),
                'user_email': self.me,
                'user_name': self.my_name,
            },
        )

    async def disconnect(self, close_code):
        # Announce user is offline
        try:
            session = self.scope.get('session', {})
            await self.channel_layer.group_send(
                self.presence_group,
                {
                    'type': 'presence_update',
                    'status': 'offline',
                    'user_id': session.get('member_id'),
                    'user_email': self.me,
                    'user_name': self.my_name,
                },
            )
        except Exception:
            pass

        if getattr(self, 'presence_group', None):
            await self.channel_layer.group_discard(self.presence_group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        typ = content.get('type')
        
        # Handle presence updates (user manually sending presence)
        if typ == 'presence':
            status = content.get('status', 'online')
            session = self.scope.get('session', {})
            await self.channel_layer.group_send(
                self.presence_group,
                {
                    'type': 'presence_update',
                    'status': status,
                    'user_id': session.get('member_id'),
                    'user_email': self.me,
                    'user_name': self.my_name,
                },
            )
            return
        
        # Handle direct messages
        if typ == 'message':
            chat_type = content.get('chat_type')  # 'dm' or 'group'
            chat_id = content.get('chat_id')      # peer id or group id
            text = content.get('message', '').strip()
            
            if not text or not chat_id:
                return
            
            if chat_type == 'dm':
                # Persist DM message
                saved = await sync_to_async(self._persist_message)(self.tenant_id, self.me, chat_id, text)
                
                # Broadcast to all users in tenant
                await self.channel_layer.group_send(
                    self.presence_group,
                    {
                        'type': 'new_message',
                        'chat_type': 'dm',
                        'chat_id': str(chat_id),
                        'message': text,
                        'sender_email': self.me,
                        'sender_name': self.my_name,
                        'timestamp': saved.get('created_at'),
                        'is_self': False,
                    },
                )
            
            elif chat_type == 'group':
                # Persist group message
                saved = await sync_to_async(self._persist_group_message)(self.tenant_id, int(chat_id), self.me, text)
                
                # Broadcast to all users in tenant
                await self.channel_layer.group_send(
                    self.presence_group,
                    {
                        'type': 'new_message',
                        'chat_type': 'group',
                        'chat_id': str(chat_id),
                        'message': text,
                        'sender_email': self.me,
                        'sender_name': self.my_name,
                        'timestamp': saved.get('created_at'),
                        'is_self': False,
                    },
                )
            
            return

    async def new_message(self, event):
        """Forward new message to WebSocket client"""
        await self.send_json(event)

    async def presence_update(self, event):
        """Forward presence update to WebSocket client"""
        await self.send_json(event)

    # ---------- sync DB helpers ----------
    def _persist_message(self, tenant_id, sender, to_user, text):
        """Persist message and return ids + normalized sender/to."""
        tenant_conn = None
        try:
            tenant_conn = get_tenant_conn(tenant_id=tenant_id)
        except TypeError:
            try:
                tenant_conn = get_tenant_conn(None)
            except Exception:
                tenant_conn = None

        sender_norm = _normalize_identity_for_tenant(tenant_conn, sender)
        to_norm = _normalize_identity_for_tenant(tenant_conn, to_user)

        a, b = sorted([sender_norm, to_norm])

        conv = exec_sql(tenant_conn, """
            SELECT id FROM chat_conversation WHERE tenant_id=%s AND user_a=%s AND user_b=%s
        """, [tenant_id, a, b])

        if conv:
            conv_id = conv[0]['id']
        else:
            exec_sql(tenant_conn, """
                INSERT INTO chat_conversation (tenant_id, user_a, user_b) VALUES (%s,%s,%s)
            """, [tenant_id, a, b], fetch=False)
            conv = exec_sql(tenant_conn, """
                SELECT id FROM chat_conversation WHERE tenant_id=%s AND user_a=%s AND user_b=%s
            """, [tenant_id, a, b])
            conv_id = conv[0]['id']

        is_read_flag = 1 if (sender_norm == to_norm) else 0

        exec_sql(tenant_conn, """
            INSERT INTO chat_message (conversation_id, sender, text, is_read) VALUES (%s,%s,%s,%s)
        """, [conv_id, sender_norm, text, is_read_flag], fetch=False)

        msg = exec_sql(tenant_conn, """
            SELECT id, created_at FROM chat_message WHERE conversation_id=%s ORDER BY created_at DESC LIMIT 1
        """, [conv_id])
        created_at = msg[0]['created_at']
        created_iso = created_at.isoformat() if hasattr(created_at, 'isoformat') else str(created_at)
        return {'id': msg[0]['id'], 'created_at': created_iso, 'sender': sender_norm, 'to': to_norm}

    def _persist_group_message(self, tenant_id, group_id, sender, text):
        """Persist a message to `chat_group_message` and return metadata."""
        tenant_conn = None
        try:
            tenant_conn = get_tenant_conn(tenant_id=tenant_id)
        except TypeError:
            try:
                tenant_conn = get_tenant_conn(None)
            except Exception:
                tenant_conn = None

        sender_norm = _normalize_identity_for_tenant(tenant_conn, sender)

        exec_sql(tenant_conn, """
            INSERT INTO chat_group_message (group_id, sender, text, is_read) VALUES (%s,%s,%s,0)
        """, [int(group_id), sender_norm, text], fetch=False)

        msg = exec_sql(tenant_conn, """
            SELECT id, created_at FROM chat_group_message WHERE group_id=%s ORDER BY created_at DESC LIMIT 1
        """, [int(group_id)])
        created_at = msg[0]['created_at']
        created_iso = created_at.isoformat() if hasattr(created_at, 'isoformat') else str(created_at)
        return {'id': msg[0]['id'], 'created_at': created_iso, 'sender': sender_norm}
# chat/consumers.py
import json
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from urllib.parse import parse_qs
from asgiref.sync import sync_to_async
from django.utils import timezone

# import your helpers - adjust path if necessary
from core.db_helpers import exec_sql, get_tenant_conn

class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        # require authenticated user
        user = self.scope.get("user")
        if not user or not getattr(user, "is_authenticated", False):
            await self.close()
            return

        # parse querystring for tenant and peer
        qs = parse_qs(self.scope.get("query_string", b"").decode())
        tenant = qs.get("tenant", [None])[0]
        peer = qs.get("peer", [None])[0]
        if not tenant:
            await self.close()
            return

        # canonical identity (use emp_code or username if you store)
            self.me = str(self.scope["session"].get("member_id") or getattr(user, "email", "") or getattr(user, "username", ""))

            # normalize to tenant identity (resolve numeric member_id -> email where possible)
            try:
                tenant_conn = get_tenant_conn(tenant_id=tenant)
                self.me = _normalize_identity_for_tenant(tenant_conn, self.me)
            except Exception:
                # best-effort normalization; continue even if lookup fails
                self.me = str(self.me).strip().lower()

        # create room names
        # conversation room: unique deterministic room for a pair
        # if peer not provided we still accept connection (useful for presence channel)
        if peer:
            a, b = sorted([self.me, str(peer)])
            self.room_name = f"chat_{tenant}_{a}_{b}"
        else:
            self.room_name = None

        # presence group for tenant-wide presence/unread notifications
        self.presence_group = f"presence_{tenant}"
        self.tenant_id = tenant
        self.peer = peer

        # join groups
        if self.room_name:
            await self.channel_layer.group_add(self.room_name, self.channel_name)
        await self.channel_layer.group_add(self.presence_group, self.channel_name)

        await self.accept()

        # announce presence
        await self.channel_layer.group_send(
            self.presence_group,
            {"type": "presence.update", "event": "presence", "user": self.me, "status": "online"},
        )

    async def disconnect(self, close_code):
        # announce offline
        try:
            await self.channel_layer.group_send(
                self.presence_group,
                {"type": "presence.update", "event": "presence", "user": self.me, "status": "offline"},
            )
        except Exception:
            pass

        if getattr(self, "room_name", None):
            await self.channel_layer.group_discard(self.room_name, self.channel_name)
        if getattr(self, "presence_group", None):
            await self.channel_layer.group_discard(self.presence_group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        typ = content.get("type")
        if typ != "message":
            return
        text = content.get("text", "").strip()
        to_user = content.get("to")
        if not text or not to_user:
            return

        # persist message synchronously in threadpool
            saved = await sync_to_async(self._persist_message)(self.tenant_id, self.me, to_user, text)

        payload = {
            "event": "message",
            "message": {
                    "sender": saved.get("sender"),
                "text": text,
                "created_at": saved.get("created_at"),
                "id": saved.get("id"),
            }
        }

        # broadcast to conversation room (if created)
        # ensure group exists (if peer provided)
        a, b = sorted([saved.get("sender"), saved.get("to")])
        room = f"chat_{self.tenant_id}_{a}_{b}"
        await self.channel_layer.group_send(room, {"type": "chat.message", **payload})

        # notify presence group for unread badge update
        await self.channel_layer.group_send(
            self.presence_group,
            {
                "type": "presence.update",
                "event": "new_message",
                    "from": saved.get("sender"),
                    "to": saved.get("to"),
                "tenant": self.tenant_id,
            },
        )

    async def chat_message(self, event):
        # forward message event to client
        await self.send_json(event)

    async def presence_update(self, event):
        # forward presence events
        await self.send_json(event)
    
    async def chat_message_read(self, event):
        # forward read-receipt events
        await self.send_json(event)

    # ---------- sync DB helpers ----------
    def _persist_message(self, tenant_id, sender, to_user, text):
        """
        Persist message; return id and created_at as ISO string.
        Uses exec_sql helper (synchronous).
        """
        tenant_conn = None
        try:
            tenant_conn = get_tenant_conn(tenant_id=tenant_id)
        except TypeError:
            # fallback if your helper expects request or no arg
            try:
                tenant_conn = get_tenant_conn(None)
            except Exception:
                tenant_conn = None

            # normalize identities for tenant
            sender_norm = _normalize_identity_for_tenant(tenant_conn, sender)
            to_norm = _normalize_identity_for_tenant(tenant_conn, to_user)

            a, b = sorted([sender_norm, to_norm])

        # find or create conversation
        conv = exec_sql(tenant_conn, """
            SELECT id FROM chat_conversation WHERE tenant_id=%s AND user_a=%s AND user_b=%s
        """, [tenant_id, a, b])

        if conv:
            conv_id = conv[0]["id"]
        else:
            exec_sql(tenant_conn, """
                INSERT INTO chat_conversation (tenant_id, user_a, user_b) VALUES (%s,%s,%s)
            """, [tenant_id, a, b], fetch=False)
            conv = exec_sql(tenant_conn, """
                SELECT id FROM chat_conversation WHERE tenant_id=%s AND user_a=%s AND user_b=%s
            """, [tenant_id, a, b])
            conv_id = conv[0]["id"]

        # For self messages mark is_read=1 else 0
            is_read_flag = 1 if (sender_norm == to_norm) else 0

        exec_sql(tenant_conn, """
            INSERT INTO chat_message (conversation_id, sender, text, is_read) VALUES (%s,%s,%s,%s)
        """, [conv_id, sender, text, is_read_flag], fetch=False)

        msg = exec_sql(tenant_conn, """
            SELECT id, created_at FROM chat_message WHERE conversation_id=%s ORDER BY created_at DESC LIMIT 1
        """, [conv_id])
        created_at = msg[0]["created_at"]
        created_iso = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
        return {"id": msg[0]["id"], "created_at": created_iso, "sender": sender_norm, "to": to_norm}


# --- Notification and typing consumers ---
class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """Subscribe to tenant presence/notification events and user-specific notifications.

    Clients that only want tenant-wide notifications (unread counts, incoming
    messages for any conversation, presence changes) can connect here.
    Also handles user-specific system notifications (task assignments, mentions, etc.)
    """

    async def connect(self):
        user = self.scope.get('user')
        if not user or not getattr(user, 'is_authenticated', False):
            await self.close()
            return

        qs = parse_qs(self.scope.get("query_string", b"").decode())
        tenant = qs.get("tenant", [None])[0]
        if not tenant:
            await self.close()
            return

        # Get member_id from session
        session = self.scope.get('session', {})
        self.member_id = session.get('member_id')
        self.tenant_id = tenant

        # Join tenant-wide presence group (for chat/presence updates)
        self.presence_group = f"presence_{tenant}"
        await self.channel_layer.group_add(self.presence_group, self.channel_name)

        # Join user-specific notification group (for system notifications)
        if self.member_id:
            self.user_notification_group = f"user_notifications_{tenant}_{self.member_id}"
            await self.channel_layer.group_add(self.user_notification_group, self.channel_name)

        await self.accept()

    async def disconnect(self, close_code):
        # Leave presence group
        if getattr(self, "presence_group", None):
            await self.channel_layer.group_discard(self.presence_group, self.channel_name)
        
        # Leave user notification group
        if getattr(self, "user_notification_group", None):
            await self.channel_layer.group_discard(self.user_notification_group, self.channel_name)

    async def presence_update(self, event):
        # forward presence and notification events to client
        await self.send_json(event)

    async def new_message(self, event):
        # forward new chat messages to client
        await self.send_json(event)

    async def chat_message(self, event):
        # forward chat messages that were also broadcast to presence_group
        await self.send_json(event)

    async def system_notification(self, event):
        """Handle system notifications (task assignments, mentions, etc.)"""
        await self.send_json({
            'event': 'system_notification',
            'notification_id': event.get('notification_id'),
            'type': event.get('notification_type', 'info'),
            'title': event.get('title'),
            'message': event.get('message'),
            'link': event.get('link'),
            'created_at': event.get('created_at'),
        })


class TypingIndicatorConsumer(AsyncJsonWebsocketConsumer):
    """Broadcast typing indicators to the tenant presence group.

    Clients send {type: 'typing', to: '<peer>', status: 'typing'|'idle'} and
    this consumer relays the event to the tenant presence_group so other
    connected sockets can update typing UI.
    """

    async def connect(self):
        qs = parse_qs(self.scope.get("query_string", b"").decode())
        tenant = qs.get("tenant", [None])[0]
        if not tenant:
            await self.close()
            return

        self.presence_group = f"presence_{tenant}"
        await self.channel_layer.group_add(self.presence_group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if getattr(self, "presence_group", None):
            await self.channel_layer.group_discard(self.presence_group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        typ = content.get("type")
        if typ != "typing":
            return
        to_user = content.get("to")
        status = content.get("status")
        if not to_user or not status:
            return

        # relay typing indicator to presence group
        await self.channel_layer.group_send(
            self.presence_group,
            {
                "type": "typing.update",
                "from": content.get("from"),
                "to": to_user,
                "status": status,
            },
        )

    async def typing_update(self, event):
        await self.send_json(event)
