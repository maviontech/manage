from channels.generic.websocket import AsyncJsonWebsocketConsumer
from asgiref.sync import sync_to_async
import json
import urllib.parse as u

# import your helpers (adapt path)
from core.db_helpers import get_tenant_conn, exec_sql

class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close()
            return

        q = self.scope["query_string"].decode()
        params = dict(u.parse_qsl(q))
        tenant = params.get("tenant")
        peer = params.get("peer")
        self.me = getattr(user, "emp_code", user.username)

        if not tenant or not peer:
            await self.close()
            return

        users = sorted([self.me, peer])
        self.room_name = f"chat_{tenant}_{users[0]}_{users[1]}"
        self.presence_group = f"presence_{tenant}"
        self.tenant_id = tenant
        self.peer = peer

        # join both groups
        await self.channel_layer.group_add(self.room_name, self.channel_name)
        await self.channel_layer.group_add(self.presence_group, self.channel_name)
        await self.accept()

        # notify presence (announce this user is online)
        await self.channel_layer.group_send(
            self.presence_group,
            {
                "type": "presence.update",
                "event": "presence",
                "user": self.me,
                "status": "online",
            }
        )

    async def disconnect(self, close_code):
        # announce offline before leaving groups
        try:
            await self.channel_layer.group_send(
                self.presence_group,
                {
                    "type": "presence.update",
                    "event": "presence",
                    "user": self.me,
                    "status": "offline",
                }
            )
        except Exception:
            pass

        if hasattr(self, "room_name"):
            await self.channel_layer.group_discard(self.room_name, self.channel_name)
        if hasattr(self, "presence_group"):
            await self.channel_layer.group_discard(self.presence_group, self.channel_name)

    async def receive_json(self, content):
        typ = content.get("type")
        if typ != "message":
            return
        text = content.get("text", "").strip()
        to_user = content.get("to")
        if not text or not to_user:
            return

        # persist message (sync DB work)
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
        # broadcast to the conversation room
        await self.channel_layer.group_send(self.room_name, {"type": "chat.message", **payload})

        # notify presence group so other UI elements (unread badges) can update if desired
        await self.channel_layer.group_send(
            self.presence_group,
            {
                "type": "presence.update",
                "event": "new_message",
                "from": self.me,
                "to": to_user,
                "tenant": self.tenant_id,
            }
        )

    async def chat_message(self, event):
        # event contains: event="message", message={...}
        await self.send_json(event)

    async def presence_update(self, event):
        # forward presence events to client
        await self.send_json(event)

    # Synchronous DB logic
    def _persist_message(self, tenant_id, sender, to_user, text):
        """
        Insert message into chat_message with is_read=0. Create conversation if needed.
        This function expects exec_sql(conn, query, params) available. Adjust get_tenant_conn usage
        if your tenant DBs are per-tenant.
        """
        # Attempt to obtain tenant_conn if you have a helper that accepts tenant_id.
        tenant_conn = None
        try:
            # try a helper that can accept tenant_id (if implemented)
            tenant_conn = get_tenant_conn(tenant_id=tenant_id)  # adapt if your helper has different signature
        except TypeError:
            # fallback to calling with no args if helper requires request
            try:
                tenant_conn = get_tenant_conn(None)
            except Exception:
                tenant_conn = None

        # canonical sorted pair
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

        exec_sql(tenant_conn, """
            INSERT INTO chat_message (conversation_id, sender, text, is_read) VALUES (%s,%s,%s,0)
        """, [conv_id, sender, text], fetch=False)

        # return the last inserted message (timestamp + id)
        msg = exec_sql(tenant_conn, """
            SELECT id, created_at FROM chat_message WHERE conversation_id=%s ORDER BY created_at DESC LIMIT 1
        """, [conv_id])
        created_at = msg[0]["created_at"].isoformat() if hasattr(msg[0]["created_at"], "isoformat") else str(msg[0]["created_at"])
        return {"id": msg[0]["id"], "created_at": created_at}
