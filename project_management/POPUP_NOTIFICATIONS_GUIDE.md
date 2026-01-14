# Popup Notification System - User Guide

## Overview
The chat application now includes a **Microsoft Teams-style popup notification system** that displays message notifications in the bottom-right corner of the screen.

## Features

### 🔔 When Notifications Appear
Popup notifications will appear when:
- **You receive a new message** from another user
- **You are logged in** but not currently viewing that specific conversation
- **Someone sends a message** in a group you're not currently viewing

### 🎯 Smart Notification Logic
- **No duplicate notifications**: If you're already viewing a conversation, notifications are suppressed
- **Real-time updates**: Notifications appear instantly via WebSocket
- **Auto-dismiss**: Notifications automatically disappear after 5 seconds
- **Click to respond**: Click any notification to open that conversation immediately

## Notification Design

### Visual Elements
```
┌─────────────────────────────────────────┐
│  [SK]  Shreya Kosabe            [×]     │  ← Header with avatar & close button
│        Hi there! How are you?           │  ← Message preview (max 100 chars)
│        💬 Click to reply                │  ← Footer with action hint
└─────────────────────────────────────────┘
```

### Styling Features
- **Gradient background**: Purple/blue gradient (Microsoft Teams style)
- **Smooth animations**: Slides in from right, hovers with scale effect
- **Sender avatar**: Shows initials in a circular badge
- **Message preview**: First 100 characters of the message
- **Interactive**: Hover effects and click-to-open functionality

## How It Works

### For Direct Messages (DM)
1. User A sends a message to User B
2. If User B is on a **different chat** or page → **Popup appears**
3. If User B is **viewing User A's chat** → **No popup** (message appears inline)

### For Group Messages
1. User A sends a message in "Project Team" group
2. If User B is in a **different group or DM** → **Popup appears**
3. If User B is **viewing "Project Team"** → **No popup** (message appears inline)

### Example Scenarios

#### Scenario 1: User on Different Chat
```
User A (Shreya) → sends message to User B (John)
User B is chatting with User C (Alice)
✅ Popup notification appears: "Shreya Kosabe: Hi John!"
```

#### Scenario 2: User Viewing Same Chat
```
User A (Shreya) → sends message to User B (John)
User B is viewing Shreya's chat
❌ No popup (message appears directly in chat feed)
```

#### Scenario 3: Group Message
```
User A (Shreya) → sends message in "Marketing Team" group
User B is in "Design Team" group chat
✅ Popup notification appears: "Shreya Kosabe (Marketing Team): Let's meet..."
```

## User Interactions

### Click on Notification
- **Opens the conversation** with that user/group
- **Marks messages as read**
- **Dismisses the notification** with smooth animation

### Click Close Button (×)
- **Dismisses only that notification**
- **Doesn't open the conversation**

### Automatic Dismissal
- Notifications **auto-close after 5 seconds**
- **Maximum 3 notifications** displayed at once
- Oldest notification is removed when limit is reached

## Sound Effects

### Notification Sound
- **Pleasant two-tone beep** plays when notification appears
- **Volume**: 50% (moderate, non-intrusive)
- **Fallback**: Uses Web Audio API if audio file not available
- **User-friendly**: Requires user interaction before playing (browser policy)

### Frequency Details
- **First tone**: 800 Hz (0.1 seconds)
- **Second tone**: 1000 Hz (0.15 seconds)
- **Total duration**: ~0.27 seconds

## Technical Details

### CSS Classes
- `.popup-notification-container` - Fixed container (bottom-right)
- `.popup-notification` - Individual notification card
- `.popup-notification-header` - Avatar, sender name, close button
- `.popup-notification-message` - Message preview text
- `.popup-notification-footer` - Action hint
- `.popup-notification.hiding` - Animation state for dismissal

### JavaScript Functions
- `showPopupNotification(senderName, senderEmail, message, groupName)` - Main function
- `playNotificationSound()` - Plays notification sound
- `playBeepSound()` - Fallback Web Audio API sound generator
- `initNotificationSound()` - Initializes audio on first user click

### WebSocket Integration
- Listens to `new_message` event type
- Listens to `chat_message` event (legacy format)
- Checks sender vs current user
- Checks if conversation is currently active
- Triggers notification only for relevant, non-active conversations

## Browser Compatibility
- ✅ Chrome/Edge: Full support
- ✅ Firefox: Full support
- ✅ Safari: Full support (Web Audio API fallback)
- ✅ Mobile browsers: Responsive design (max-width adjusts)

## Customization

### Change Notification Duration
Edit line in JavaScript:
```javascript
setTimeout(() => { /* ... */ }, 5000); // Change 5000 to desired ms
```

### Change Maximum Notifications
Edit line in JavaScript:
```javascript
if (notifications.length > 3) { // Change 3 to desired max
```

### Change Colors
Edit CSS variables:
```css
.popup-notification {
    background: linear-gradient(135deg, #5B6CD6 0%, #7B83EB 100%);
    /* Change gradient colors here */
}
```

### Change Position
Edit CSS:
```css
.popup-notification-container {
    bottom: 24px;  /* Distance from bottom */
    right: 24px;   /* Distance from right */
}
```

## Troubleshooting

### Notifications Not Appearing
1. **Check WebSocket connection**: Open browser console, look for WebSocket errors
2. **Verify tenant ID**: Must be valid (not "None" or empty)
3. **Check user authentication**: Must be logged in with valid session

### Sound Not Playing
1. **Click anywhere on page first**: Browsers require user interaction
2. **Check browser sound settings**: Ensure not muted
3. **Fallback active**: Web Audio API beep should work even without audio file

### Notifications Appearing When Viewing Chat
1. **Check `currentMode` variable**: Should be 'dm' or 'group'
2. **Check `selectedPeer`**: Should match sender's email/ID
3. **Review console logs**: Look for "Suppressing notification" messages

## Testing Checklist

- [ ] Open chat with User A
- [ ] Have User B send message to current user
- [ ] Notification should appear (with sound)
- [ ] Click notification to open User B's chat
- [ ] Have User B send another message
- [ ] No notification should appear (already viewing chat)
- [ ] Switch to User C's chat
- [ ] Have User B send message again
- [ ] Notification should appear
- [ ] Test with group messages
- [ ] Test close button
- [ ] Test auto-dismiss after 5 seconds
- [ ] Test multiple notifications (max 3)

## Future Enhancements
- [ ] Custom notification sound upload
- [ ] Notification settings panel (enable/disable, sound, duration)
- [ ] Browser desktop notifications (requires permission)
- [ ] Notification history/log
- [ ] Do Not Disturb mode
- [ ] Different colors for DM vs Group notifications
- [ ] Notification priority levels
- [ ] Snooze functionality

---

**Last Updated**: January 14, 2026
**Version**: 1.0
**Author**: GitHub Copilot
