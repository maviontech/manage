from channels.generic.websocket import AsyncJsonWebsocketConsumer
from urllib.parse import parse_qs
from asgiref.sync import sync_to_async
from core.db_helpers import exec_sql, get_tenant_conn


def normalize(val):
    return str(val).strip().lower() if val else ""

class ChatConsumer(AsyncJsonWebsocketConsumer):

    async def connect(self):
        # Get session data (this app uses session-based auth, not Django User auth)
        session = self.scope.get("session", {})
        
        # Check for session-based authentication
        member_id = session.get("member_id")
        user_id = session.get("user_id")
        
        if not member_id and not user_id:
            print("WS rejected: no authenticated session")
            await self.close(code=4001)
            return

        qs = parse_qs(self.scope["query_string"].decode())
        self.tenant_id = qs.get("tenant", [None])[0]

        if not self.tenant_id:
            print("WS rejected: tenant missing")
            await self.close(code=4002)
            return

        # Get user identity from session
        self.me = (
            session.get("ident_email")
            or session.get("member_name")
            or session.get("user")
        )

        self.presence_group = f"presence_{self.tenant_id}"

        await self.channel_layer.group_add(self.presence_group, self.channel_name)
        await self.accept()

        print(f"✅ WS connected: {self.me} (tenant: {self.tenant_id})")

    async def disconnect(self, close_code):
        if hasattr(self, "presence_group"):
            await self.channel_layer.group_send(
                self.presence_group,
                {
                    "type": "presence_update",
                    "status": "offline",
                    "user": self.me,
                },
            )
            await self.channel_layer.group_discard(
                self.presence_group, self.channel_name
            )

    async def receive_json(self, content):
        if content.get("type") != "message":
            return

        text = content.get("message")
        to_user = content.get("to")

        if not text or not to_user:
            return

        saved = await sync_to_async(self.save_message)(
            self.tenant_id, self.me, to_user, text
        )

        await self.channel_layer.group_send(
            self.presence_group,
            {
                "type": "new_message",
                "message": text,
                "from": self.me,
                "to": to_user,
                "created_at": saved["created_at"],
            },
        )

    async def new_message(self, event):
        await self.send_json(event)

    async def presence_update(self, event):
        await self.send_json(event)

    def save_message(self, tenant, sender, receiver, text):
        conn = get_tenant_conn(tenant_id=tenant)
        exec_sql(
            conn,
            """
            INSERT INTO chat_message (sender, receiver, text, is_read)
            VALUES (%s,%s,%s,0)
            """,
            [sender, receiver, text],
            fetch=False,
        )
        row = exec_sql(
            conn,
            "SELECT created_at FROM chat_message ORDER BY id DESC LIMIT 1"
        )
        return {"created_at": row[0]["created_at"].isoformat()}



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
