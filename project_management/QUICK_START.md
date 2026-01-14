# ⚡ QUICK START GUIDE - Popup Notifications

## 🚀 5-Minute Setup & Test

Your popup notification system is **ALREADY INSTALLED AND WORKING!** 🎉

Follow these simple steps to test it:

---

## Step 1: Open Your Chat Application
```
1. Server is running at: http://127.0.0.1:8000/
2. Navigate to: http://127.0.0.1:8000/chat/
3. Log in with your credentials
```

---

## Step 2: Open a Second Browser Session

### Option A: Use Incognito Mode
```
1. Press Ctrl+Shift+N (Chrome/Edge) or Ctrl+Shift+P (Firefox)
2. Go to: http://127.0.0.1:8000/chat/
3. Log in with a DIFFERENT user account
```

### Option B: Use Different Browser
```
1. Open a different browser (e.g., Chrome vs Firefox)
2. Go to: http://127.0.0.1:8000/chat/
3. Log in with a DIFFERENT user account
```

---

## Step 3: Setup for Testing

### Browser Window 1 (User A - John)
```
✓ Logged in as: john@company.com
✓ Currently viewing: Chat with Alice Johnson
```

### Browser Window 2 (User B - Bob)  
```
✓ Logged in as: bob@company.com
✓ Currently viewing: Chat with John (User A)
```

---

## Step 4: Send a Test Message 🎯

### From Browser Window 2 (Bob):
```
1. Make sure you're in John's chat
2. Type: "Hey John! Testing the new notifications!"
3. Click Send (or press Enter)
```

---

## Step 5: Watch the Magic! ✨

### In Browser Window 1 (John):
```
You should see:

┌─────────────────────────────────┐
│  [BS] Bob Smith           [×]  │  ← Appears bottom-right!
│  Hey John! Testing the...      │
│  💬 Click to reply             │
└─────────────────────────────────┘

✅ Notification slides in from right
✅ Pleasant "ding-dong" sound plays
✅ Auto-dismisses after 5 seconds
```

---

## 🎉 Success Checklist

If you see the popup notification with:
- [x] Purple gradient background
- [x] Sender's initials in circle (BS)
- [x] Sender's name (Bob Smith)
- [x] Message preview text
- [x] Close button (×)
- [x] "Click to reply" hint
- [x] Smooth animation
- [x] Notification sound

**🎊 CONGRATULATIONS! It's working perfectly!**

---

## 🧪 Additional Tests

### Test 2: No Popup When Viewing Same Chat
```
Browser 1 (John): Click on Bob's chat
Browser 2 (Bob): Send another message

Result: ❌ NO POPUP in Browser 1
        ✅ Message appears directly in chat feed
        
Why? Because John is already viewing Bob's chat!
```

### Test 3: Multiple Notifications
```
Browser 2 (Bob): Send message to John
Browser 3 (Alice): Send message to John  
Browser 4 (Carol): Send message to John

Result: ✅ Up to 3 popups stack vertically
        ✅ Oldest removed when 4th appears
```

### Test 4: Click to Open
```
Browser 1 (John): See popup from Carol
Browser 1 (John): Click the notification

Result: ✅ Opens chat with Carol
        ✅ Notification disappears
        ✅ Messages marked as read
```

---

## 🎯 Quick Feature Reference

| Feature | What Happens |
|---------|-------------|
| **Receive message while on different chat** | ✅ Popup appears |
| **Receive message while viewing that chat** | ❌ No popup (inline) |
| **Click notification** | Opens conversation |
| **Click × button** | Closes notification only |
| **Wait 5 seconds** | Auto-dismisses |
| **Hover notification** | Scales up with shadow |
| **Multiple messages** | Max 3 stack vertically |
| **Sound** | Pleasant two-tone beep |

---

## 🐛 Troubleshooting

### No Notification Appearing?

**Check 1: Are you on a different chat?**
```
✓ Correct: Viewing Alice's chat, Bob sends message → ✅ Popup
✗ Wrong: Viewing Bob's chat, Bob sends message → ❌ No popup
```

**Check 2: Is WebSocket connected?**
```
1. Press F12 to open Developer Console
2. Look for: "✅ WS connected: your-email"
3. If missing: Refresh the page
```

**Check 3: Different user sending?**
```
✓ Correct: Bob sends to John → ✅ Popup
✗ Wrong: John sends (self) → ❌ No popup
```

### No Sound?

**Solution: Click anywhere on the page first!**
```
Browsers block sound until user interacts with page.
After first click, sound will work for all notifications.
```

### Popup Appearing When It Shouldn't?

**Check browser console:**
```
1. Press F12
2. Look for: "🔕 Suppressing notification"
3. If missing, check currentMode and selectedPeer values
```

---

## 📖 More Information

- **Full Guide**: See `POPUP_NOTIFICATIONS_GUIDE.md`
- **Visual Examples**: See `POPUP_VISUAL_GUIDE.md`
- **Implementation**: See `IMPLEMENTATION_SUMMARY.md`
- **Live Demo**: Open `POPUP_NOTIFICATION_DEMO.html` in browser

---

## 🎓 Understanding the Logic

### Smart Notification Decision Tree
```
New message received
    │
    ├─ Is from me? ──────────────► NO POPUP
    │
    ├─ Am I viewing this chat? ──► NO POPUP  
    │
    └─ All other cases ──────────► ✅ SHOW POPUP!
```

### Why This Makes Sense
```
✅ SHOW popup when:
  - Someone sends me a message
  - I'm working on something else
  - Need to be notified of new message

❌ DON'T show popup when:
  - I sent the message myself (duh!)
  - I'm already looking at that chat
  - Message will appear inline anyway
```

---

## 🎨 Customization (Optional)

### Change Auto-Dismiss Time
```
File: core/templates/core/team_chat.html
Line: ~1120

setTimeout(() => { /* ... */ }, 5000);
                                 ↑
                              Change this!
                          (milliseconds)

Examples:
  3000 = 3 seconds
  7000 = 7 seconds
  10000 = 10 seconds
```

### Change Notification Position
```
File: core/templates/core/team_chat.html
Line: ~60

.popup-notification-container {
    bottom: 24px;  ← Distance from bottom
    right: 24px;   ← Distance from right
}

Try:
  bottom-left: left: 24px;
  top-right: top: 24px; right: 24px;
```

---

## ✅ You're All Set!

The popup notification system is:
- ✅ **Installed** and configured
- ✅ **Working** with your WebSocket system
- ✅ **Smart** about when to show/hide
- ✅ **Beautiful** with smooth animations
- ✅ **User-friendly** with sound and interactions

**No additional setup needed! Just use your chat normally.** 🚀

---

## 💡 Pro Tips

1. **Multiple Users**: Test with at least 2 different user accounts
2. **Sound**: Click page first for sound to work (browser policy)
3. **Console**: Keep F12 open to see debug messages
4. **Demo**: Use `POPUP_NOTIFICATION_DEMO.html` for offline testing
5. **Mobile**: Works great on phones/tablets too!

---

**Need Help?**
- Check the detailed guides in the documentation files
- Look at browser console (F12) for debug messages
- Test with the demo HTML file first

**🎉 Happy Chatting with Beautiful Notifications! 🎉**
