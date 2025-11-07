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
                "sender": self.me,
                "text": text,
                "created_at": saved.get("created_at"),
                "id": saved.get("id"),
            }
        }

        # broadcast to conversation room (if created)
        # ensure group exists (if peer provided)
        a, b = sorted([self.me, to_user])
        room = f"chat_{self.tenant_id}_{a}_{b}"
        await self.channel_layer.group_send(room, {"type": "chat.message", **payload})

        # notify presence group for unread badge update
        await self.channel_layer.group_send(
            self.presence_group,
            {
                "type": "presence.update",
                "event": "new_message",
                "from": self.me,
                "to": to_user,
                "tenant": self.tenant_id,
            },
        )

    async def chat_message(self, event):
        # forward message event to client
        await self.send_json(event)

    async def presence_update(self, event):
        # forward presence events
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

        a, b = sorted([sender, to_user])

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
        is_read_flag = 1 if (sender == to_user) else 0

        exec_sql(tenant_conn, """
            INSERT INTO chat_message (conversation_id, sender, text, is_read) VALUES (%s,%s,%s,%s)
        """, [conv_id, sender, text, is_read_flag], fetch=False)

        msg = exec_sql(tenant_conn, """
            SELECT id, created_at FROM chat_message WHERE conversation_id=%s ORDER BY created_at DESC LIMIT 1
        """, [conv_id])
        created_at = msg[0]["created_at"]
        created_iso = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)
        return {"id": msg[0]["id"], "created_at": created_iso}
