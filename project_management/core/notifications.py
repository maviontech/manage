# core/notifications.py
"""
Notification utility functions for sending real-time notifications to users.
"""
import logging
from datetime import datetime
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from .db_helpers import get_tenant_conn, exec_sql

logger = logging.getLogger('notifications')


class NotificationManager:
    """Manages sending and storing notifications."""

    @staticmethod
    def send_notification(tenant_id, user_id, title, message, notification_type='info', link=None, created_by_id=None):
        """
        Send a real-time notification to a specific user and save to database.
        
        Args:
            tenant_id (str): Tenant ID
            user_id (int): Target user/member ID
            title (str): Notification title
            message (str): Notification message
            notification_type (str): Type of notification (info, success, warning, error, task, project, team)
            link (str): Optional URL link for the notification
            created_by_id (int): ID of user who triggered the notification
            
        Returns:
            dict: Notification data with ID
        """
        try:
            # Get database connection
            conn = get_tenant_conn(tenant_id=tenant_id)
            if not conn:
                logger.error(f"Failed to get tenant connection for tenant: {tenant_id}")
                return None

            # Prepare notification data
            now = datetime.now()
            created_at_str = now.strftime('%Y-%m-%d %H:%M:%S')

            # Save notification to database
            result = exec_sql(
                conn,
                """
                INSERT INTO notifications (user_id, title, message, type, link, is_read, created_at)
                VALUES (%s, %s, %s, %s, %s, 0, %s)
                """,
                [user_id, title, message, notification_type, link, now],
                fetch=False
            )

            # Get the notification ID
            notification_id_result = exec_sql(conn, "SELECT LAST_INSERT_ID() as id", [])
            notification_id = notification_id_result[0]['id'] if notification_id_result else None

            logger.info(f"Notification saved to DB: ID={notification_id}, user_id={user_id}, title={title}")

            # Broadcast notification via WebSocket
            channel_layer = get_channel_layer()
            if channel_layer and notification_id:
                # User-specific notification group
                group_name = f'user_notifications_{tenant_id}_{user_id}'
                
                notification_data = {
                    'type': 'system.notification',  # Maps to system_notification method in consumer
                    'notification_id': notification_id,
                    'notification_type': notification_type,
                    'title': title,
                    'message': message,
                    'link': link,
                    'created_at': created_at_str,
                }

                # Send to WebSocket group
                async_to_sync(channel_layer.group_send)(group_name, notification_data)
                logger.info(f"Notification broadcast to WebSocket group: {group_name}")

            return {
                'id': notification_id,
                'user_id': user_id,
                'title': title,
                'message': message,
                'type': notification_type,
                'link': link,
                'created_at': created_at_str,
            }

        except Exception as e:
            logger.error(f"Error sending notification: {e}", exc_info=True)
            return None

    @staticmethod
    def send_bulk_notification(tenant_id, user_ids, title, message, notification_type='info', link=None, created_by_id=None):
        """
        Send notification to multiple users.
        
        Args:
            tenant_id (str): Tenant ID
            user_ids (list): List of target user/member IDs
            title (str): Notification title
            message (str): Notification message
            notification_type (str): Type of notification
            link (str): Optional URL link
            created_by_id (int): ID of user who triggered the notification
            
        Returns:
            list: List of notification data
        """
        results = []
        for user_id in user_ids:
            result = NotificationManager.send_notification(
                tenant_id=tenant_id,
                user_id=user_id,
                title=title,
                message=message,
                notification_type=notification_type,
                link=link,
                created_by_id=created_by_id
            )
            if result:
                results.append(result)
        
        return results

    @staticmethod
    def mark_as_read(tenant_id, notification_id):
        """
        Mark a notification as read.
        
        Args:
            tenant_id (str): Tenant ID
            notification_id (int): Notification ID
            
        Returns:
            bool: Success status
        """
        try:
            conn = get_tenant_conn(tenant_id=tenant_id)
            if not conn:
                return False

            exec_sql(
                conn,
                "UPDATE notifications SET is_read = 1 WHERE id = %s",
                [notification_id],
                fetch=False
            )
            return True
        except Exception as e:
            logger.error(f"Error marking notification as read: {e}")
            return False

    @staticmethod
    def mark_all_as_read(tenant_id, user_id):
        """
        Mark all notifications as read for a user.
        
        Args:
            tenant_id (str): Tenant ID
            user_id (int): User ID
            
        Returns:
            bool: Success status
        """
        try:
            conn = get_tenant_conn(tenant_id=tenant_id)
            if not conn:
                return False

            exec_sql(
                conn,
                "UPDATE notifications SET is_read = 1 WHERE user_id = %s AND is_read = 0",
                [user_id],
                fetch=False
            )
            return True
        except Exception as e:
            logger.error(f"Error marking all notifications as read: {e}")
            return False

    @staticmethod
    def get_user_notifications(tenant_id, user_id, limit=50, unread_only=False):
        """
        Get notifications for a user.
        
        Args:
            tenant_id (str): Tenant ID
            user_id (int): User ID
            limit (int): Maximum number of notifications to return
            unread_only (bool): If True, only return unread notifications
            
        Returns:
            list: List of notification dicts
        """
        try:
            conn = get_tenant_conn(tenant_id=tenant_id)
            if not conn:
                return []

            query = """
                SELECT id, user_id, title, message, type, is_read, link, created_at
                FROM notifications
                WHERE user_id = %s
            """
            params = [user_id]

            if unread_only:
                query += " AND is_read = 0"

            query += " ORDER BY created_at DESC LIMIT %s"
            params.append(limit)

            notifications = exec_sql(conn, query, params)
            
            # Convert datetime objects to strings for JSON serialization
            for notif in notifications:
                if 'created_at' in notif and notif['created_at']:
                    notif['created_at'] = notif['created_at'].strftime('%Y-%m-%d %H:%M:%S')

            return notifications
        except Exception as e:
            logger.error(f"Error getting user notifications: {e}")
            return []

    @staticmethod
    def get_unread_count(tenant_id, user_id):
        """
        Get count of unread notifications for a user.
        
        Args:
            tenant_id (str): Tenant ID
            user_id (int): User ID
            
        Returns:
            int: Count of unread notifications
        """
        try:
            conn = get_tenant_conn(tenant_id=tenant_id)
            if not conn:
                return 0

            result = exec_sql(
                conn,
                "SELECT COUNT(*) as count FROM notifications WHERE user_id = %s AND is_read = 0",
                [user_id]
            )
            return result[0]['count'] if result else 0
        except Exception as e:
            logger.error(f"Error getting unread count: {e}")
            return 0

    @staticmethod
    def delete_notification(tenant_id, notification_id):
        """
        Delete a notification.
        
        Args:
            tenant_id (str): Tenant ID
            notification_id (int): Notification ID
            
        Returns:
            bool: Success status
        """
        try:
            conn = get_tenant_conn(tenant_id=tenant_id)
            if not conn:
                return False

            exec_sql(
                conn,
                "DELETE FROM notifications WHERE id = %s",
                [notification_id],
                fetch=False
            )
            return True
        except Exception as e:
            logger.error(f"Error deleting notification: {e}")
            return False
