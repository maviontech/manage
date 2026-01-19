# Desktop Notifications Setup & Troubleshooting Guide

## ✅ What Was Fixed

Your notification system has been enhanced to show **desktop notifications** that appear even when you're working on other applications or websites. This matches the ATS notification system behavior.

### Key Improvements Made:

1. **Desktop Notifications Always Show** - Notifications now appear regardless of which window or app is active
2. **Better Permission Handling** - Improved permission request flow with clear status messages
3. **Full URL Icons** - Fixed icon paths to use absolute URLs for better reliability
4. **Enhanced Logging** - Better console logging to track notification delivery
5. **Test Page** - New test page to verify notifications are working

---

## 🧪 How to Test Desktop Notifications

### Step 1: Access the Test Page

1. Login to your application
2. Go to: `http://your-domain/notifications/test/`
3. You'll see a test page with multiple buttons

### Step 2: Grant Permission

1. Click the **"Request Permission Again"** button
2. Your browser will show a popup asking for notification permission
3. Click **"Allow"** or **"Enable"**
4. You should see a test notification appear immediately

### Step 3: Test While on Desktop

1. Click any test button (e.g., "Send Test Notification")
2. **Immediately** switch to another application (Word, Email, etc.)
3. Within 1-2 seconds, you should see the notification appear on your desktop!

### Step 4: Test Real Notifications

1. Open your application in one browser tab
2. Have another user send you a message or assign you a task
3. Switch to another application (email, Excel, etc.)
4. You should receive a desktop notification!

---

## 🔧 How Desktop Notifications Work

### Notification Flow:

```
New Event (Task/Message) 
    ↓
WebSocket receives notification
    ↓
JavaScript checks permission
    ↓
Creates Notification object
    ↓
Browser shows notification on desktop
    ↓
User clicks → Opens relevant page
```

### When Notifications Appear:

- ✅ When browser tab is open but you're on another app
- ✅ When browser tab is minimized
- ✅ When browser tab is in background
- ✅ When you're working in Word, Excel, etc.
- ✅ Even when you're on a different website!

### What Triggers Notifications:

1. **Task Assignment** - When someone assigns you a task
2. **Chat Messages** - When someone sends you a message
3. **System Notifications** - When you receive system alerts
4. **Any notification event** - All real-time events

---

## 🚨 Troubleshooting

### Problem: "Permission not granted" message

**Solution:**
1. Click the lock icon in your browser address bar
2. Find "Notifications" in the permissions list
3. Change to "Allow"
4. Refresh the page

**Browser-specific:**
- **Chrome:** Settings → Privacy and security → Site settings → Notifications → Allow
- **Firefox:** about:preferences#privacy → Permissions → Notifications → Settings
- **Edge:** Settings → Cookies and site permissions → Notifications → Allow

---

### Problem: Permission granted but no notifications appear

**Check Windows Notification Settings:**

1. Open **Windows Settings** (Win + I)
2. Go to **System** → **Notifications**
3. Make sure notifications are **ON**
4. Scroll down and ensure your **browser** is allowed to show notifications
5. Check if **Focus Assist** is OFF (it blocks all notifications)

**Turn off Focus Assist:**
- Click the notification icon in system tray
- Click "Focus Assist"
- Select "Off"

---

### Problem: Notifications work on website but not on desktop

**This means your browser tab is likely closed.** Desktop notifications only work when:
- The browser is running (can be minimized)
- At least one tab with your application is open
- WebSocket connection is active

**Solution:**
- Keep at least one tab open with your application
- The tab can be minimized or in the background
- Don't close the browser completely

---

### Problem: Notifications appear but no sound

**Sound requires user interaction first:**
- Click anywhere on the page once
- Then sounds will play for future notifications
- This is a browser security requirement

---

### Problem: Too many notifications

**Adjust notification settings:**
1. Notifications auto-dismiss after 10 seconds
2. Only the last 5 notifications are kept in the panel
3. You can close notifications by clicking the X button

---

## 🎯 Best Practices

### For Users:

1. **Keep one browser tab open** with the application (can be minimized)
2. **Allow notifications** when prompted
3. **Check Focus Assist** is off on Windows
4. **Test regularly** using the test page: `/notifications/test/`

### For Developers:

1. **Check browser console** for notification errors
2. **Verify WebSocket connection** is active
3. **Test icon paths** are accessible
4. **Monitor permission status** in console logs

---

## 📝 Code Changes Made

### 1. Enhanced Permission Request (`notifications.js`)

```javascript
// Now shows more detailed status and test notification
function requestDesktopNotificationPermission() {
    // Better logging and user feedback
    // Shows test notification on success
    // Clear error messages on failure
}
```

### 2. Improved Notification Creation

```javascript
// Now uses full URL for icons (more reliable)
function createDesktopNotification(title, message, link) {
    const notification = new Notification(title, {
        body: message,
        icon: window.location.origin + '/static/core/images/icon.png',
        // ... more options
    });
}
```

### 3. Removed `document.hidden` Check

**Before:**
```javascript
// Only showed notification when tab was hidden
if (document.hidden && Notification.permission === "granted") {
    showDesktopNotification();
}
```

**After:**
```javascript
// Always shows notification (even when tab is visible)
showDesktopNotification();
```

This is the key change! Now notifications appear **everywhere**.

---

## 🔍 Debugging Tips

### Check Console Logs

Open browser console (F12) and look for:

```
✅ Desktop notifications already enabled - you're all set!
🔔 Creating desktop notification: Task Assigned
✅ Desktop notification created successfully!
```

### Check Permission Status

In browser console, run:
```javascript
console.log('Permission:', Notification.permission);
```

Should show: `"granted"`

### Test Notification Manually

In browser console, run:
```javascript
new Notification('Test', {body: 'Testing notification'});
```

If this works, your setup is correct!

---

## 📱 Mobile Support

**Desktop notifications are NOT supported on mobile devices.**

On mobile:
- In-app popup notifications still work
- Badge counts still update
- Sounds may play (if user interacted)
- But native desktop notifications won't appear

This is a browser limitation, not a code issue.

---

## 🆘 Still Having Issues?

### Check This Checklist:

- [ ] Browser supports notifications (Chrome, Firefox, Edge)
- [ ] Permission is "granted" (not "default" or "denied")
- [ ] Browser tab is open (can be minimized)
- [ ] WebSocket is connected (check console)
- [ ] Windows notifications are enabled
- [ ] Focus Assist is OFF
- [ ] Browser has internet connection
- [ ] Icons exist at specified paths

### Get More Help:

1. Visit the test page: `/notifications/test/`
2. Check the console log output
3. Try with different browsers
4. Restart your browser
5. Clear browser cache and try again

---

## 📊 Feature Comparison: ATS vs Your System

| Feature | ATS | Your System |
|---------|-----|-------------|
| Desktop Notifications | ✅ | ✅ |
| Sound Alerts | ✅ | ✅ |
| In-app Popups | ✅ | ✅ |
| Badge Counts | ✅ | ✅ |
| WebSocket Real-time | ✅ | ✅ |
| Click to Open | ✅ | ✅ |
| Auto-dismiss | ✅ | ✅ |
| Permission Request | ✅ | ✅ Enhanced |
| Test Page | ❌ | ✅ New! |

Your system now has **all the features** of the ATS notification system, plus a test page!

---

## 🎉 Success Criteria

You'll know it's working when:

1. ✅ You see desktop notifications while working in Word/Excel
2. ✅ Notifications appear in Windows Action Center
3. ✅ Clicking notification opens your application
4. ✅ Sound plays for new notifications
5. ✅ Badge count updates in real-time

**That's it! Your notification system now works exactly like ATS.** 🚀
