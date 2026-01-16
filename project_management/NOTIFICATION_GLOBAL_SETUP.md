# Global Notification System - Setup Complete ✅

## What Was Changed

Your notification system now works **globally across all pages**, not just the chat page!

### Changes Made:

1. **Added Tenant ID to Body Tag** ([base.html](core/templates/core/base.html#L180))
   ```html
   <body data-tenant-id="{{ request.session.tenant_id|default:'' }}">
   ```
   This allows the notification JavaScript to access the tenant ID on every page.

2. **Included Notification CSS Globally** ([base.html](core/templates/core/base.html#L110))
   ```html
   <link rel="stylesheet" href="{% static 'core/css/notifications.css' %}">
   ```
   This loads the toast notification styles on all pages.

3. **Included Notification JavaScript Globally** ([base.html](core/templates/core/base.html#L552))
   ```html
   <script src="{% static 'core/js/notifications.js' %}"></script>
   ```
   This initializes the WebSocket connection and notification handlers on all pages.

## How It Works

### Architecture:

```
┌─────────────────────────────────────────────────────────────┐
│                      Any Page/Window                         │
│  (Dashboard, Projects, Tasks, Teams, etc.)                  │
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  notifications.js (loaded globally)                 │    │
│  │  • Connects to WebSocket on page load               │    │
│  │  • Listens for system_notification events           │    │
│  │  • Shows desktop notifications when tab inactive    │    │
│  │  • Shows toast popups on current page               │    │
│  │  • Plays notification sound                         │    │
│  │  • Updates bell icon badge count                    │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                            ↕ WebSocket
┌─────────────────────────────────────────────────────────────┐
│              NotificationConsumer (Backend)                  │
│  • Connects user to user_notifications_{tenant}_{user}      │
│  • Receives system_notification events                      │
│  • Forwards to connected clients                            │
└─────────────────────────────────────────────────────────────┘
```

### Notification Types:

The system supports these notification types with different colors/icons:
- **info** - Blue (default)
- **success** - Green  
- **warning** - Yellow
- **error** - Red
- **task** - Purple
- **project** - Blue
- **team** - Pink

## Testing Your Notifications

### Method 1: Using Python Code

You can send a test notification from Django shell or any view:

```python
from core.notifications import NotificationManager

# Send notification to a specific user
NotificationManager.send_notification(
    tenant_id='your_tenant_id',      # Get from request.session['tenant_id']
    user_id=123,                      # Target user's member_id
    title='Test Notification',
    message='This is a test message that appears on all pages!',
    notification_type='success',      # info, success, warning, error, task, project, team
    link='/tasks/',                   # Optional: where to redirect on click
    created_by_id=456                 # Optional: who sent the notification
)
```

### Method 2: Using Django Shell

```bash
python manage.py shell
```

Then run:
```python
from core.notifications import NotificationManager

# Replace with your actual tenant_id and member_id
NotificationManager.send_notification(
    tenant_id='your_tenant_id',
    user_id=1,
    title='🎉 Global Notifications Working!',
    message='You can now receive notifications on ANY page!',
    notification_type='success'
)
```

### Method 3: Creating a Test View

Add this to your `core/views.py`:

```python
from django.http import JsonResponse
from core.notifications import NotificationManager

def test_send_notification(request):
    """Test endpoint to send notification to current user"""
    tenant_id = request.session.get('tenant_id')
    member_id = request.session.get('member_id')
    
    if not tenant_id or not member_id:
        return JsonResponse({'error': 'Not logged in'}, status=400)
    
    result = NotificationManager.send_notification(
        tenant_id=tenant_id,
        user_id=member_id,
        title='Test Notification',
        message='This notification appears on all pages! You are currently on: ' + request.path,
        notification_type='info',
        link='/notifications/'
    )
    
    return JsonResponse({'success': True, 'notification': result})
```

Add to `core/urls.py`:
```python
path('test-notification/', views.test_send_notification, name='test_notification'),
```

Then visit: `http://localhost:8000/test-notification/` while logged in.

## Features

### ✅ What You Get:

1. **Desktop Notifications** - When user is on another tab/window
2. **Toast Popups** - Animated notifications on current page
3. **Sound Alerts** - Optional notification sound (gracefully disabled if file missing)
4. **Bell Icon Badge** - Real-time unread count in header
5. **Click to Navigate** - Notifications link to relevant pages
6. **Auto-dismiss** - Notifications auto-close after 10 seconds
7. **Works Everywhere** - Dashboard, Projects, Tasks, Teams, any page!

### Desktop Notification Behavior:

- **When Tab is Active**: Shows toast popup on the page
- **When Tab is Inactive**: Shows desktop notification (if permission granted)
- **Click on Desktop Notification**: Brings window to focus and navigates to link

### Browser Permission:

The first time a user visits any page, they'll see a browser prompt asking for notification permission. This is required for desktop notifications.

## Real-World Examples

### Example 1: Task Assignment
```python
# When a task is assigned to a user
NotificationManager.send_notification(
    tenant_id=tenant_id,
    user_id=assigned_user_id,
    title='New Task Assigned',
    message=f'{assigner_name} assigned you: {task_title}',
    notification_type='task',
    link=f'/tasks/edit/{task_id}/'
)
```

### Example 2: Project Update
```python
# When a project is updated
NotificationManager.send_notification(
    tenant_id=tenant_id,
    user_id=team_member_id,
    title='Project Updated',
    message=f'{updater_name} updated project: {project_name}',
    notification_type='project',
    link=f'/projects/{project_id}/'
)
```

### Example 3: Team Mention
```python
# When someone is mentioned in a comment
NotificationManager.send_notification(
    tenant_id=tenant_id,
    user_id=mentioned_user_id,
    title='You were mentioned',
    message=f'{commenter_name} mentioned you in a comment',
    notification_type='team',
    link=f'/tasks/{task_id}/#comment-{comment_id}'
)
```

## Chat Integration

Your chat messages already work with notifications! The system handles:
- New direct messages
- New group messages
- Presence updates (online/offline status)

These are automatically routed through the same WebSocket system and show notifications when you're on other pages.

## Troubleshooting

### No Notifications Appearing?

1. **Check Browser Console** (F12):
   - Should see: `✅ Notification WebSocket connected`
   - If not, check tenant_id is in session

2. **Check Tenant ID**:
   - Open browser console and run: `document.body.getAttribute('data-tenant-id')`
   - Should return your tenant ID, not empty string

3. **Check User Authentication**:
   - Notifications only work when logged in
   - Check: `request.session.get('member_id')` exists

4. **Check WebSocket Connection**:
   - Look for WebSocket errors in browser console
   - Check ASGI server is running (not just WSGI)

### Desktop Notifications Not Showing?

1. **Check Browser Permission**:
   - Look for notification icon in browser address bar
   - Allow notifications for your site

2. **Check Tab Focus**:
   - Desktop notifications only show when tab is inactive
   - Switch to another tab, then send notification

### Sound Not Playing?

This is expected! The sound file is optional:
- Place `notification.mp3` in `core/static/core/sounds/`
- Or notifications will work silently
- Check `core/static/core/sounds/README.txt` for sound sources

## Configuration

You can customize the notification behavior in `core/static/core/js/notifications.js`:

```javascript
const CONFIG = {
    WS_RECONNECT_DELAY: 3000,              // Reconnect after 3 seconds
    NOTIFICATION_DURATION: 10000,          // Show for 10 seconds
    SOUND_ENABLED: true,                   // Play sound (if file exists)
    DESKTOP_NOTIFICATIONS_ENABLED: true,   // Show desktop notifications
    MAX_PREVIEW_NOTIFICATIONS: 5,          // Show 5 in dropdown
};
```

## What's Next?

Your notification system is now fully functional! You can:

1. ✅ Send notifications from any Django view
2. ✅ Users receive them on ANY page they're viewing
3. ✅ Works just like Microsoft Teams notifications
4. ✅ Desktop notifications when user is away
5. ✅ Toast popups when user is active

Start integrating notifications into your workflow:
- Task assignments
- Project updates
- Team mentions
- Status changes
- Deadline reminders
- And more!

---

## Quick Start Test

**Want to test it NOW?** Run this in Django shell:

```bash
python manage.py shell
```

```python
# Get your tenant and user IDs from session/database
from core.notifications import NotificationManager

NotificationManager.send_notification(
    tenant_id='your_tenant',  # Replace with actual tenant_id
    user_id=1,                # Replace with your member_id
    title='🎉 Success!',
    message='Global notifications are working perfectly!',
    notification_type='success'
)
```

Make sure you're logged in and have a page open in your browser. You'll see the notification appear instantly! 🚀
