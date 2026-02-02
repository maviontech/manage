from channels.generic.websocket import AsyncJsonWebsocketConsumer
from urllib.parse import parse_qs
from asgiref.sync import sync_to_async
from core.db_helpers import exec_sql, get_tenant_conn
import pymysql
import os
import logging

# Use the project logger configured in settings.LOGGING so messages
# route to the websocket/notifications handler (websocket.log)
logger = logging.getLogger('notifications')

# Master DB connection config
MASTER_DB_CONFIG = {
    'db_host': os.environ.get('MYSQL_ADMIN_HOST', '127.0.0.1'),
    'db_port': int(os.environ.get('MYSQL_ADMIN_PORT') or 3306),
    'db_user': os.environ.get('MYSQL_ADMIN_USER', 'root'),
    'db_password': os.environ.get('MYSQL_ADMIN_PWD', 'root'),
    'db_name': os.environ.get('MASTER_DB_NAME', 'master_db')
}


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
            logger.info("WS rejected: no authenticated session")
            await self.close(code=4001)
            return

        qs = parse_qs(self.scope["query_string"].decode())
        self.tenant_id = qs.get("tenant", [None])[0]

        if not self.tenant_id:
            logger.info("WS rejected: tenant missing")
            await self.close(code=4002)
            return

        # Get user identity from session
        self.me = (
            session.get("ident_email")
            or session.get("member_name")
            or session.get("user")
        )

        # also keep numeric member_id if available for user-specific groups
        self.member_id = session.get("member_id")

        # Get peer from query string for DM conversations
        self.peer = qs.get("peer", [None])[0]
        
        # Get group from query string for group conversations
        self.group_id = qs.get("group", [None])[0]

        self.presence_group = f"presence_{self.tenant_id}"

        await self.channel_layer.group_add(self.presence_group, self.channel_name)
        
        # Join group-specific channel if group_id provided
        if self.group_id:
            self.group_channel = f"chat_group_{self.tenant_id}_{self.group_id}"
            await self.channel_layer.group_add(self.group_channel, self.channel_name)
            logger.info(f"📨 Joined group channel: {self.group_channel}")
        
        # Join conversation-specific room for read receipts if peer is specified
        if self.peer and self.me:
            # Normalize both identities and sanitize for channel group names
            # Replace invalid characters (@, spaces, etc.) with underscores
            import re
            me_norm = str(self.me).strip().lower()
            peer_norm = str(self.peer).strip().lower()
            # Sanitize: only allow alphanumerics, hyphens, underscores, periods
            me_clean = re.sub(r'[^a-z0-9\-_.]', '_', me_norm)
            peer_clean = re.sub(r'[^a-z0-9\-_.]', '_', peer_norm)
            # Sort to match the server logic in views.py
            a, b = sorted([me_clean, peer_clean])
            self.conversation_room = f"chat_{self.tenant_id}_{a}_{b}"
            # Ensure total length is under 100 characters
            if len(self.conversation_room) < 100:
                await self.channel_layer.group_add(self.conversation_room, self.channel_name)
                logger.info(f"📨 Joined conversation room: {self.conversation_room}")
            else:
                logger.info(f"⚠️ Conversation room name too long, skipping: {len(self.conversation_room)} chars")
                self.conversation_room = None
        else:
            self.conversation_room = None
        
        await self.accept()

        logger.info(f"✅ WS connected: {self.me} (tenant: {self.tenant_id})")
        
        # Broadcast online presence to all users in tenant
        try:
            await self.channel_layer.group_send(
                self.presence_group,
                {
                    "type": "presence_update",
                    "status": "online",
                    "user_email": str(self.me).strip().lower(),
                },
            )
        except Exception as e:
            logger.error(f"Error broadcasting online presence: {e}")

    async def disconnect(self, close_code):
        logger.info(f"🔌 WS disconnect: {getattr(self, 'me', 'unknown')} (code: {close_code})")
        if hasattr(self, "presence_group"):
            try:
                await self.channel_layer.group_send(
                    self.presence_group,
                    {
                        "type": "presence_update",
                        "status": "offline",
                        "user_email": str(getattr(self, "me", "unknown")).strip().lower(),
                    },
                )
            except Exception as e:
                logger.error(f"Error sending presence update: {e}")
            
            try:
                await self.channel_layer.group_discard(
                    self.presence_group, self.channel_name
                )
            except Exception as e:
                logger.error(f"Error leaving group: {e}")
        
        # Leave conversation room if joined
        if hasattr(self, "conversation_room") and self.conversation_room:
            try:
                await self.channel_layer.group_discard(
                    self.conversation_room, self.channel_name
                )
                logger.info(f"📤 Left conversation room: {self.conversation_room}")
            except Exception as e:
                logger.error(f"Error leaving conversation room: {e}")
        
        # Leave group channel if joined
        if hasattr(self, "group_channel") and self.group_channel:
            try:
                await self.channel_layer.group_discard(
                    self.group_channel, self.channel_name
                )
                logger.info(f"📤 Left group channel: {self.group_channel}")
            except Exception as e:
                logger.error(f"Error leaving group channel: {e}")

    async def receive_json(self, content):
        logger.info(f"📨 Received: {content}")
        
        msg_type = content.get("type")
        
        # Handle group messages
        if msg_type == "group_message":
            group_id = content.get("group_id")
            text = content.get("text")
            cid = content.get("cid")
            
            if not text or not group_id:
                logger.warning(f"⚠️ Missing text or group_id: text={bool(text)}, group_id={bool(group_id)}")
                return
            
            logger.info(f"💬 Saving group message from {self.me} to group {group_id}: {text[:50]}...")
            
            try:
                saved = await sync_to_async(self.save_group_message)(
                    self.tenant_id, group_id, self.me, text
                )
                
                logger.info(f"✅ Group message saved, broadcasting...")
                
                # Broadcast to group channel
                group_channel = f"chat_group_{self.tenant_id}_{group_id}"
                await self.channel_layer.group_send(
                    group_channel,
                    {
                        "type": "chat_message",
                        "event": "message",
                        "message": {
                            "sender": self.me,
                            "text": text,
                            "created_at": saved["created_at"],
                            "id": saved.get("id"),
                            "group_id": int(group_id),
                            "cid": cid,
                        }
                    },
                )
                
                logger.info(f"✅ Group message broadcasted successfully")
            except Exception as e:
                logger.error(f"❌ Error processing group message: {e}")
                import traceback
                traceback.print_exc()
            return
        
        # Handle direct messages
        if msg_type != "message":
            logger.warning(f"⚠️ Ignoring non-message type: {msg_type}")
            return

        text = content.get("message")
        to_user = content.get("to")
        cid = content.get("cid")  # Get client ID for optimistic UI matching

        if not text or not to_user:
            logger.warning(f"⚠️ Missing text or to_user: text={bool(text)}, to_user={bool(to_user)}")
            return

        logger.info(f"💬 Saving message from {self.me} to {to_user}: {text[:50]}...")
        
        try:
            saved = await sync_to_async(self.save_message)(
                self.tenant_id, self.me, to_user, text
            )

            logger.info(f"✅ Message saved, broadcasting...")
            # Build event payload for clients
            event = {
                "type": "new_message",
                "message": text,
                "from": self.me,
                "to": to_user,
                "created_at": saved["created_at"],
                "id": saved.get("id"),
                "cid": cid,
            }

            # Send to recipient's user-specific group ONLY (no fallback broadcast)
            to_member_id = saved.get("to_member_id")
            if to_member_id:
                user_group = f"user_notifications_{self.tenant_id}_{to_member_id}"
                try:
                    await self.channel_layer.group_send(user_group, event)
                    logger.info(f"✅ Sent direct message to user group: {user_group}")
                except Exception as e:
                    logger.error(f"❌ Error sending to user group {user_group}: {e}")
            else:
                # CRITICAL: Do NOT broadcast to presence_group for personal messages
                # This would expose private messages to all users in the tenant
                logger.error(f"❌ Cannot send direct message notification: recipient member_id not found for {to_user}")
                logger.error(f"   Message saved but notification not sent. Recipient must refresh to see message.")

            # Also send the event to the sender's own user group if we have their member_id
            if getattr(self, "member_id", None):
                try:
                    sender_group = f"user_notifications_{self.tenant_id}_{self.member_id}"
                    await self.channel_layer.group_send(sender_group, event)
                    logger.info(f"✅ Also sent new_message to sender group: {sender_group}")
                except Exception as e:
                    logger.error(f"❌ Error sending new_message to sender group: {e}")

            logger.info(f"✅ Direct message dispatch complete")
        except Exception as e:
            logger.error(f"❌ Error processing message: {e}")
            import traceback
            traceback.print_exc()

    async def new_message(self, event):
        try:
            await self.send_json(event)
        except Exception as e:
            logger.error(f"❌ Error in ChatConsumer.new_message: {e}")

    async def presence_update(self, event):
        try:
            await self.send_json(event)
        except Exception as e:
            logger.error(f"❌ Error in ChatConsumer.presence_update: {e}")
            import traceback
            traceback.print_exc()

    async def typing_update(self, event):
        """Handle typing indicator updates"""
        try:
            await self.send_json(event)
        except Exception as e:
            logger.error(f"❌ Error in ChatConsumer.typing_update: {e}")

    async def chat_message_read(self, event):
        """Handle read receipt notifications and broadcast to clients"""
        logger.info(f"📖 Read receipt handler called: {event}")
        logger.info(f"📖 Sending {len(event.get('message_ids', []))} message IDs as read")
        # Forward the entire event to the client
        await self.send_json({
            'type': event.get('type', 'message_read'),
            'event': 'message_read',
            'message_ids': event.get('message_ids', []),
            'conversation_id': event.get('conversation_id')
        })
    
    async def chat_message(self, event):
        """Handle group chat messages"""
        await self.send_json(event)

    def save_message(self, tenant, sender, receiver, text):
        # Get tenant credentials from clients_master using direct pymysql connection
        master_conn = pymysql.connect(
            host=MASTER_DB_CONFIG['db_host'],
            port=MASTER_DB_CONFIG['db_port'],
            user=MASTER_DB_CONFIG['db_user'],
            password=MASTER_DB_CONFIG['db_password'],
            database=MASTER_DB_CONFIG['db_name'],
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True
        )
        
        try:
            with master_conn.cursor() as cur:
                cur.execute("""
                    SELECT db_name, db_host, db_user, db_password
                    FROM clients_master
                    WHERE id = %s OR client_name = %s OR domain_postfix = %s
                    LIMIT 1
                """, [tenant, tenant, tenant])
                row = cur.fetchone()
        finally:
            master_conn.close()
            
        if not row:
            raise Exception(f"Tenant {tenant} not found in clients_master")
        
        # Connect to tenant MySQL database
        conn = pymysql.connect(
            host=row['db_host'],
            port=3306,  # Default MySQL port
            user=row['db_user'],
            password=row['db_password'],
            database=row['db_name'],
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True
        )
        
        try:
            with conn.cursor() as cur:
                # Normalize sender and receiver - convert member IDs to emails
                sender_norm = str(sender).strip().lower()
                receiver_norm = str(receiver).strip().lower()
                
                # If receiver is numeric (member ID), look up email
                if receiver_norm.isdigit():
                    cur.execute("SELECT email FROM members WHERE id=%s", [int(receiver_norm)])
                    member_row = cur.fetchone()
                    if member_row and member_row.get('email'):
                        receiver_norm = str(member_row['email']).strip().lower()
                
                # If sender is numeric (member ID), look up email
                if sender_norm.isdigit():
                    cur.execute("SELECT email FROM members WHERE id=%s", [int(sender_norm)])
                    member_row = cur.fetchone()
                    if member_row and member_row.get('email'):
                        sender_norm = str(member_row['email']).strip().lower()

                # Try to resolve member ids for sender and receiver (if available)
                sender_member_id = None
                receiver_member_id = None
                cur.execute("SELECT id FROM members WHERE email=%s", [sender_norm])
                _s = cur.fetchone()
                if _s and _s.get('id'):
                    sender_member_id = _s.get('id')

                cur.execute("SELECT id FROM members WHERE email=%s", [receiver_norm])
                _r = cur.fetchone()
                if _r and _r.get('id'):
                    receiver_member_id = _r.get('id')
                
                # Sort users for consistent conversation matching
                users = sorted([sender_norm, receiver_norm])
                
                # Find existing conversation
                cur.execute("""
                    SELECT id FROM chat_conversation
                    WHERE tenant_id=%s AND user_a=%s AND user_b=%s
                """, [tenant, users[0], users[1]])
                row = cur.fetchone()
                
                if row:
                    conv_id = row['id']
                else:
                    # Create new conversation
                    cur.execute("""
                        INSERT INTO chat_conversation (tenant_id, user_a, user_b)
                        VALUES (%s,%s,%s)
                    """, [tenant, users[0], users[1]])
                    conv_id = conn.insert_id()
                
                # Insert message
                cur.execute("""
                    INSERT INTO chat_message (conversation_id, sender, text, is_read)
                    VALUES (%s,%s,%s,0)
                """, [conv_id, sender_norm, text])
                
                # Get the message ID and created_at timestamp
                message_id = conn.insert_id()
                cur.execute("""
                    SELECT created_at FROM chat_message 
                    WHERE id=%s
                """, [message_id])
                timestamp_row = cur.fetchone()
                
            return {
                "id": message_id,
                "created_at": timestamp_row['created_at'].isoformat() if timestamp_row else None,
                "from_member_id": sender_member_id,
                "to_member_id": receiver_member_id,
            }
        finally:
            conn.close()
    
    def save_group_message(self, tenant, group_id, sender, text):
        """Save a group message to the database"""
        # Get tenant credentials from clients_master using direct pymysql connection
        master_conn = pymysql.connect(
            host=MASTER_DB_CONFIG['db_host'],
            port=MASTER_DB_CONFIG['db_port'],
            user=MASTER_DB_CONFIG['db_user'],
            password=MASTER_DB_CONFIG['db_password'],
            database=MASTER_DB_CONFIG['db_name'],
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True
        )
        
        try:
            with master_conn.cursor() as cur:
                cur.execute("""
                    SELECT db_name, db_host, db_user, db_password
                    FROM clients_master
                    WHERE id = %s OR client_name = %s OR domain_postfix = %s
                    LIMIT 1
                """, [tenant, tenant, tenant])
                row = cur.fetchone()
        finally:
            master_conn.close()
            
        if not row:
            raise Exception(f"Tenant {tenant} not found in clients_master")
        
        # Connect to tenant MySQL database
        conn = pymysql.connect(
            host=row['db_host'],
            port=3306,  # Default MySQL port
            user=row['db_user'],
            password=row['db_password'],
            database=row['db_name'],
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True
        )
        
        try:
            with conn.cursor() as cur:
                # Normalize sender - convert member ID to email if needed
                sender_norm = str(sender).strip().lower()
                
                if sender_norm.isdigit():
                    cur.execute("SELECT email FROM members WHERE id=%s", [int(sender_norm)])
                    member_row = cur.fetchone()
                    if member_row and member_row.get('email'):
                        sender_norm = str(member_row['email']).strip().lower()
                
                # Ensure group tables exist
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS chat_group (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        tenant_id VARCHAR(128),
                        name VARCHAR(255),
                        created_by VARCHAR(255),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_tenant (tenant_id)
                    )
                """)
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS chat_group_message (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        group_id INT,
                        sender VARCHAR(255),
                        text TEXT,
                        is_read TINYINT DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_group (group_id),
                        INDEX idx_created (created_at)
                    )
                """)
                
                # Insert message
                cur.execute("""
                    INSERT INTO chat_group_message (group_id, sender, text, is_read)
                    VALUES (%s, %s, %s, 0)
                """, [int(group_id), sender_norm, text])
                
                # Get the message ID and created_at timestamp
                message_id = conn.insert_id()
                cur.execute("""
                    SELECT created_at FROM chat_group_message
                    WHERE id=%s
                """, [message_id])
                timestamp_row = cur.fetchone()
                
            return {
                "id": message_id,
                "created_at": timestamp_row['created_at'].isoformat() if timestamp_row else None
            }
        finally:
            conn.close()



# --- Notification and typing consumers ---
class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """Subscribe to tenant presence/notification events and user-specific notifications.

    Clients that only want tenant-wide notifications (unread counts, incoming
    messages for any conversation, presence changes) can connect here.
    Also handles user-specific system notifications (task assignments, mentions, etc.)
    """

    async def connect(self):
        # Get session data (this app uses session-based auth, not Django User auth)
        session = self.scope.get("session", {})
        
        # Debug: Log session contents
        logger.debug(f"🔍 NotificationConsumer session keys: {list(session.keys()) if session else 'None'}")
        logger.debug(f"🔍 Session data: member_id={session.get('member_id')}, user_id={session.get('user_id')}")
        
        # Check for session-based authentication
        member_id = session.get("member_id")
        user_id = session.get("user_id")
        
        if not member_id and not user_id:
            logger.error("❌ Notification WS rejected: no authenticated session")
            logger.error(f"   Available session keys: {list(session.keys())}")
            await self.close(code=4001)
            return

        qs = parse_qs(self.scope.get("query_string", b"").decode())
        tenant = qs.get("tenant", [None])[0]
        if not tenant:
            logger.error("❌ Notification WS rejected: tenant missing")
            await self.close(code=4002)
            return

        # Get member_id from session
        self.member_id = session.get('member_id')
        self.tenant_id = tenant

        try:
            # Join tenant-wide presence group (for chat/presence updates)
            self.presence_group = f"presence_{tenant}"
            await self.channel_layer.group_add(self.presence_group, self.channel_name)
            logger.info(f"✅ Joined presence group: {self.presence_group}")

            # Join user-specific notification group (for system notifications)
            if self.member_id:
                self.user_notification_group = f"user_notifications_{tenant}_{self.member_id}"
                await self.channel_layer.group_add(self.user_notification_group, self.channel_name)
                logger.info(f"✅ Joined user notification group: {self.user_notification_group}")
                logger.info(f"✅ NotificationConsumer connected: member_id={self.member_id}, tenant={tenant}")
            else:
                logger.info(f"✅ NotificationConsumer connected: user_id={user_id}, tenant={tenant}")
        except Exception as e:
            logger.error(f"❌ Error joining channel groups: {e}")
            import traceback
            traceback.print_exc()
            await self.close(code=4003)
            return

        await self.accept()
        logger.info(f"✅ NotificationConsumer WebSocket accepted and ready")

    async def disconnect(self, close_code):
        logger.info(f"🔌 NotificationConsumer disconnect: code={close_code}, member_id={getattr(self, 'member_id', 'unknown')}")
        # Leave presence group
        if getattr(self, "presence_group", None):
            await self.channel_layer.group_discard(self.presence_group, self.channel_name)
        
        # Leave user notification group
        if getattr(self, "user_notification_group", None):
            await self.channel_layer.group_discard(self.user_notification_group, self.channel_name)

    async def receive_json(self, content):
        """Handle any incoming messages from client (currently read-only, but prevents crashes)"""
        logger.info(f"📥 NotificationConsumer received message: {content}")
        # NotificationConsumer is primarily for receiving server-pushed notifications
        # If client needs to send data, handle it here
        pass

    async def presence_update(self, event):
        # forward presence and notification events to client
        try:
            # Remove 'type' field and add 'event' field for client
            client_event = {k: v for k, v in event.items() if k != 'type'}
            client_event['event'] = 'presence_update'
            await self.send_json(client_event)
        except Exception as e:
            logger.error(f"❌ Error sending presence_update: {e}")

    async def new_message(self, event):
        # forward new chat messages to client
        try:
            logger.info(f"📨 NotificationConsumer forwarding new_message: {event.get('from')} -> {event.get('to')}")
            # Remove 'type' field before sending to client to avoid confusion
            # The 'type' field is for Django Channels routing, not for the client
            client_event = {k: v for k, v in event.items() if k != 'type'}
            client_event['event'] = 'new_message'  # Add event field for client
            await self.send_json(client_event)
            logger.info(f"✅ Successfully sent new_message to client")
        except Exception as e:
            logger.error(f"❌ Error sending new_message: {e}")
            import traceback
            traceback.print_exc()

    async def chat_message(self, event):
        # forward chat messages that were also broadcast to presence_group
        try:
            logger.info(f"📨 NotificationConsumer forwarding chat_message: {event}")
            # Remove 'type' field and add 'event' field for client
            client_event = {k: v for k, v in event.items() if k != 'type'}
            if 'event' not in client_event:
                client_event['event'] = 'chat_message'
            await self.send_json(client_event)
            logger.info(f"✅ Successfully sent chat_message to client")
        except Exception as e:
            logger.error(f"❌ Error sending chat_message: {e}")

    async def system_notification(self, event):
        """Handle system notifications (task assignments, mentions, etc.)"""
        try:
            await self.send_json({
                'event': 'system_notification',
                'notification_id': event.get('notification_id'),
                'type': event.get('notification_type', 'info'),
                'title': event.get('title'),
                'message': event.get('message'),
                'link': event.get('link'),
                'created_at': event.get('created_at'),
            })
        except Exception as e:
            logger.error(f"❌ Error sending system_notification: {e}")

    async def typing_update(self, event):
        """Handle typing indicator updates"""
        try:
            # Remove 'type' field and ensure 'event' field is present
            client_event = {k: v for k, v in event.items() if k != 'type'}
            if 'event' not in client_event:
                client_event['event'] = 'typing'
            await self.send_json(client_event)
        except Exception as e:
            logger.error(f"❌ Error sending typing_update: {e}")


class TypingIndicatorConsumer(AsyncJsonWebsocketConsumer):
    """Broadcast typing indicators to the tenant presence group.

    Clients send {type: 'typing', to: '<peer>', status: 'typing'|'idle'} and
    this consumer relays the event to the tenant presence_group so other
    connected sockets can update typing UI.
    """

    async def connect(self):
        # Get session data (use session-based auth like other consumers)
        session = self.scope.get("session", {})
        
        # Check for session-based authentication
        member_id = session.get("member_id")
        user_id = session.get("user_id")
        
        if not member_id and not user_id:
            logger.info("Typing WS rejected: no authenticated session")
            await self.close(code=4001)
            return

        qs = parse_qs(self.scope.get("query_string", b"").decode())
        tenant = qs.get("tenant", [None])[0]
        if not tenant:
            logger.info("Typing WS rejected: tenant missing")
            await self.close(code=4002)
            return

        # Get user identity from session
        self.me = (
            session.get("ident_email")
            or session.get("member_name")
            or session.get("user")
        )

        self.presence_group = f"presence_{tenant}"
        await self.channel_layer.group_add(self.presence_group, self.channel_name)
        await self.accept()
        logger.info(f"✅ Typing WS connected: {self.me} (tenant: {tenant})")

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

        # Use session identity as sender if not provided
        from_user = content.get("from") or self.me
        
        logger.info(f"📝 Typing indicator: {from_user} -> {to_user} ({status})")

        # relay typing indicator to presence group
        await self.channel_layer.group_send(
            self.presence_group,
            {
                "type": "typing.update",
                "event": "typing",
                "from": from_user,
                "to": to_user,
                "status": status,
            },
        )

    async def typing_update(self, event):
        # Forward typing event to client
        await self.send_json(event)

    async def presence_update(self, event):
        """Handle presence updates (online/offline status)"""
        try:
            # Remove 'type' field and add 'event' field for client
            client_event = {k: v for k, v in event.items() if k != 'type'}
            client_event['event'] = 'presence_update'
            await self.send_json(client_event)
        except Exception as e:
            logger.error(f"❌ Error in TypingIndicatorConsumer.presence_update: {e}")

    async def new_message(self, event):
        """Handle new chat messages"""
        try:
            # Remove 'type' field and add 'event' field for client
            client_event = {k: v for k, v in event.items() if k != 'type'}
            client_event['event'] = 'new_message'
            await self.send_json(client_event)
        except Exception as e:
            logger.error(f"❌ Error in TypingIndicatorConsumer.new_message: {e}")

    async def chat_message(self, event):
        """Handle group chat messages"""
        try:
            await self.send_json(event)
        except Exception as e:
            logger.error(f"❌ Error in TypingIndicatorConsumer.chat_message: {e}")
