from channels.generic.websocket import AsyncJsonWebsocketConsumer
from asgiref.sync import sync_to_async
import json

# import your helpers (adapt path)
from core.db_helpers import get_tenant_conn, exec_sql

class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close()
            return

        # Expect query_string: ?tenant=...&peer=...
        q = self.scope["query_string"].decode()
        import urllib.parse as u
        params = dict(u.parse_qsl(q))
        tenant = params.get("tenant")
        peer = params.get("peer")
        me = getattr(user, "emp_code", user.username)

        if not tenant or not peer:
            await self.close()
            return

        # canonical room name
        users = sorted([me, peer])
        self.room_name = f"chat_{tenant}_{users[0]}_{users[1]}"
        await self.channel_layer.group_add(self.room_name, self.channel_name)
        self.tenant = tenant
        self.peer = peer
        self.me = me
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "room_name"):
            await self.channel_layer.group_discard(self.room_name, self.channel_name)

    async def receive_json(self, content):
        typ = content.get("type")
        if typ != "message":
            return
        text = content.get("text","").strip()
        to_user = content.get("to")
        if not text or not to_user:
            return

        # persist message using sync wrapper
        saved = await sync_to_async(self._persist_message)(self.tenant, self.me, to_user, text)
        payload = {
            "sender": self.me,
            "text": text,
            "created_at": saved.get("created_at"),
            "id": saved.get("id"),
        }
        # broadcast to group (both participants)
        await self.channel_layer.group_send(self.room_name, {
            "type": "chat.message",
            "message": payload
        })

    async def chat_message(self, event):
        # forwards the message to the client
        await self.send_json(event["message"])

    def _persist_message(self, tenant_id, sender, to_user, text):
        """
        synchronous DB operations using exec_sql helper.
        """
        conn = None
        # mimic get_tenant_conn by using requestless helper or global registry
        # If your get_tenant_conn requires request, adapt to a tenant manager.
        # For now assume prism.utils.get_tenant_conn_by_id exists or exec_sql can operate given tenant_id.
        conn = get_tenant_conn(None, tenant_id=tenant_id) if hasattr(get_tenant_conn, "__call__") else None
        # If your function signature differs, change accordingly.
        a,b = sorted([sender, to_user])
        # find or insert conv
        conv = exec_sql(conn, """
          SELECT id FROM chat_conversation WHERE tenant_id=%s AND user_a=%s AND user_b=%s
        """, [tenant_id, a, b])
        if conv:
            conv_id = conv[0]["id"]
        else:
            exec_sql(conn, """
              INSERT INTO chat_conversation (tenant_id, user_a, user_b) VALUES (%s,%s,%s)
            """, [tenant_id, a, b])
            conv = exec_sql(conn, """
              SELECT id FROM chat_conversation WHERE tenant_id=%s AND user_a=%s AND user_b=%s
            """, [tenant_id, a, b])
            conv_id = conv[0]["id"]

        exec_sql(conn, """
          INSERT INTO chat_message (conversation_id, sender, text, is_read) VALUES (%s,%s,%s,0)
        """, [conv_id, sender, text])

        # fetch last inserted message id / timestamp (may differ based on exec_sql)
        msg = exec_sql(conn, """
          SELECT id, created_at FROM chat_message WHERE conversation_id=%s ORDER BY created_at DESC LIMIT 1
        """, [conv_id])
        created_at = msg[0]["created_at"].isoformat() if hasattr(msg[0]["created_at"], "isoformat") else str(msg[0]["created_at"])
        return {"id": msg[0]["id"], "created_at": created_at}
