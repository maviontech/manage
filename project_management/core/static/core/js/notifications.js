// core/static/core/js/notifications.js
/**
 * Real-Time Notification System
 * Handles WebSocket connections, desktop notifications, sound alerts, and UI updates
 */

(function() {
    'use strict';

    // Prevent multiple initializations
    if (window.NotificationSystemInitialized) {
        console.warn('⚠️ Notification system already initialized, skipping duplicate initialization');
        return;
    }
    window.NotificationSystemInitialized = true;

    // Configuration
    const CONFIG = {
        WS_RECONNECT_DELAY: 3000,
        NOTIFICATION_DURATION: 10000,
        SOUND_ENABLED: true,
        DESKTOP_NOTIFICATIONS_ENABLED: true,
        MAX_PREVIEW_NOTIFICATIONS: 5,
    };

    // State
    let notificationWS = null;
    let notificationsDropdownOpen = false;
    let userInteracted = false;
    let notificationSound = null;

    // Initialize on DOM ready
    document.addEventListener('DOMContentLoaded', function() {
        initNotificationSystem();
    });

    function initNotificationSystem() {
        console.log('🚀 Initializing notification system...');
        
        // Request desktop notification permission FIRST (most important)
        requestDesktopNotificationPermission();
        
        // Track user interaction for sound playback
        trackUserInteraction();
        
        // Initialize notification sound
        initNotificationSound();
        
        // Setup WebSocket connection
        setupNotificationWebSocket();
        
        // Load initial notification count
        updateNotificationCount();
        
        // Setup dropdown close handler
        setupDropdownHandlers();
        
        // Auto-refresh count every 30 seconds (backup)
        setInterval(updateNotificationCount, 30000);
        
        console.log('✅ Notification system initialized');
    }

    function requestDesktopNotificationPermission() {
        if (!("Notification" in window)) {
            console.warn("⚠️ This browser does not support desktop notifications");
            return;
        }
        
        console.log('📋 Current notification permission:', Notification.permission);
        
        if (Notification.permission === "default") {
            console.log("🔔 Requesting desktop notification permission...");
            Notification.requestPermission().then(permission => {
                if (permission === "granted") {
                    console.log("✅ Desktop notification permission GRANTED! You'll get notifications everywhere!");
                    // Show a welcome notification to confirm it works
                    try {
                        const testNotification = new Notification('🎉 Notifications Enabled!', {
                            body: 'You will now receive notifications even when working on other apps or websites!',
                            icon: window.location.origin + '/static/core/images/icon.png',
                            badge: window.location.origin + '/static/core/images/badge.png',
                            tag: 'welcome-notification',
                            requireInteraction: false,
                        });
                        
                        testNotification.onclick = function() {
                            window.focus();
                            this.close();
                        };
                        
                        setTimeout(() => testNotification.close(), 8000);
                    } catch (e) {
                        console.log("Test notification error:", e);
                    }
                } else {
                    console.log("❌ Desktop notification permission DENIED");
                    alert("⚠️ Desktop notifications are blocked. Please enable them in your browser settings to receive notifications when working on other apps.");
                }
            }).catch(err => {
                console.error("Error requesting notification permission:", err);
            });
        } else if (Notification.permission === "granted") {
            console.log("✅ Desktop notifications already enabled - you're all set!");
        } else if (Notification.permission === "denied") {
            console.warn("❌ Desktop notifications are BLOCKED. Please enable them in your browser settings.");
        }
    }

    function trackUserInteraction() {
        document.addEventListener('click', function() { userInteracted = true; }, { once: true });
        document.addEventListener('keydown', function() { userInteracted = true; }, { once: true });
    }

    function initNotificationSound() {
        // Create audio element for notification sound
        notificationSound = new Audio('/static/core/sounds/notification.mp3');
        notificationSound.volume = 0.5;
        notificationSound.preload = 'auto';
        
        // Handle sound loading errors gracefully
        notificationSound.addEventListener('error', function() {
            console.warn('Notification sound failed to load');
            CONFIG.SOUND_ENABLED = false;
        });
    }

    function setupNotificationWebSocket() {
        const TENANT_ID = document.body.getAttribute('data-tenant-id') || '';
        if (!TENANT_ID) {
            console.warn('No tenant ID found, WebSocket connection skipped');
            return;
        }

        const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const wsUrl = `${scheme}://${window.location.host}/ws/notifications/?tenant=${encodeURIComponent(TENANT_ID)}`;
        
        console.log('Connecting to notification WebSocket:', wsUrl);
        
        try {
            notificationWS = new WebSocket(wsUrl);
            
            notificationWS.onopen = function() {
                console.log('✅ Notification WebSocket connected');
                updateNotificationCount();
            };
            
            notificationWS.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);
                    console.log('📩 Notification received:', data);
                    handleWebSocketMessage(data);
                } catch (e) {
                    console.error('Failed to parse WebSocket message:', e);
                }
            };
            
            notificationWS.onerror = function(error) {
                console.error('❌ Notification WebSocket error:', error);
            };
            
            notificationWS.onclose = function() {
                console.warn('🔌 Notification WebSocket closed, reconnecting...');
                setTimeout(setupNotificationWebSocket, CONFIG.WS_RECONNECT_DELAY);
            };
        } catch (e) {
            console.error('Failed to create WebSocket:', e);
        }
    }

    function handleWebSocketMessage(data) {
        const eventType = data.event || data.type;
        
        switch (eventType) {
            case 'system_notification':
                handleSystemNotification(data);
                break;
            case 'new_message':
            case 'new_group_message':
                handleChatMessage(data);
                break;
            case 'presence_update':
                handlePresenceUpdate(data);
                break;
            default:
                console.log('Unknown event type:', eventType);
        }
    }

    function handleSystemNotification(data) {
        console.log('🔔 System notification received:', data);
        
        try {
            // 1. Always show desktop notification (works even on desktop/other apps)
            const notifTitle = data.title || '🔔 New Notification';
            const notifMessage = data.message || 'You have a new update';
            const notifLink = data.link || '/notifications/';
            
            // Desktop notification - this will show even if you're on desktop or other apps!
            showDesktopNotification(notifTitle, notifMessage, notifLink);
            
            // 2. Play notification sound (only if user has interacted)
            playNotificationSound();
            
            // 3. Animate bell icon
            animateBellIcon();
            
            // 4. Update badge count
            updateNotificationCount();
            
            // 5. Show in-page popup notification (only if user is on the website)
            showToastNotification(data);
            
            console.log('✅ All notification handlers triggered');
        } catch (error) {
            console.error('❌ Error in handleSystemNotification:', error);
        }
    }

    function handleChatMessage(data) {
        try {
            const senderName = data.from || 'Someone';
            const message = data.message || data.text || 'New message';
            
            console.log('💬 Chat message received:', senderName, '-', message);
            
            // 1. Always show desktop notification (works even when on desktop/other apps)
            showDesktopNotification(
                `💬 ${senderName}`,
                message,
                '/chat/team/'
            );
            
            // 2. Show in-page popup notification (only if not on chat page)
            if (!window.location.pathname.startsWith('/chat')) {
                showChatPopupNotification(data);
            }
            
            // 3. Update badge count
            const badge = document.getElementById('notif-badge');
            if (badge) {
                let count = parseInt(badge.textContent || '0') || 0;
                count += 1;
                setBadgeCount(count);
            }
            
            // 4. Play sound for chat messages
            playNotificationSound();
            
            console.log('✅ Chat notification handlers triggered');
        } catch (error) {
            console.error('❌ Error in handleChatMessage:', error);
        }
    }

    function handlePresenceUpdate(data) {
        // Update online status indicators in chat
        updateOnlineStatus(data.user_id, data.status);
    }

    function playNotificationSound() {
        if (!CONFIG.SOUND_ENABLED || !userInteracted || !notificationSound) {
            return;
        }
        
        notificationSound.play().catch(error => {
            console.warn('Could not play notification sound:', error.message);
        });
    }

    function showDesktopNotification(title, message, link) {
        if (!CONFIG.DESKTOP_NOTIFICATIONS_ENABLED) {
            console.log("Desktop notifications disabled in config");
            return;
        }
        
        // Check if browser supports notifications
        if (!("Notification" in window)) {
            console.warn("This browser doesn't support desktop notifications");
            return;
        }
        
        // Check permission status
        if (Notification.permission === "denied") {
            console.warn("❌ Desktop notifications are BLOCKED. Please enable in browser settings.");
            return;
        }
        
        if (Notification.permission !== "granted") {
            console.log("🔔 Requesting notification permission...");
            Notification.requestPermission().then(permission => {
                if (permission === "granted") {
                    console.log("✅ Permission granted! Showing notification now...");
                    createDesktopNotification(title, message, link);
                }
            });
            return;
        }
        
        // Permission is granted, show notification
        createDesktopNotification(title, message, link);
    }
    
    function createDesktopNotification(title, message, link) {
        try {
            console.log("🔔 Creating desktop notification:", title);
            
            // Create the notification (icon and badge removed to avoid 404 errors)
            const notification = new Notification(title || '🔔 New Notification', {
                body: message || 'You have a new update',
                tag: 'notification-' + Date.now(),
                requireInteraction: false, // Auto-dismiss after a while
                // These make it more prominent
                silent: false, // Use system sound
                timestamp: Date.now(),
            });
            
            // Handle notification click - focus window and navigate
            notification.onclick = function(event) {
                event.preventDefault(); // Prevent default browser behavior
                window.focus(); // Focus the browser window
                
                if (link && link !== 'null' && link !== '' && link !== 'undefined') {
                    window.location.href = link;
                }
                
                notification.close();
            };
            
            // Handle notification errors
            notification.onerror = function(error) {
                console.error("Notification error:", error);
            };
            
            // Auto-close after 10 seconds
            setTimeout(() => {
                try {
                    notification.close();
                } catch (e) {
                    // Notification might already be closed by user
                }
            }, CONFIG.NOTIFICATION_DURATION);
            
            console.log("✅ Desktop notification created successfully!");
            
        } catch (error) {
            console.error("❌ Failed to create desktop notification:", error);
        }
    }

    function animateBellIcon() {
        const bellBtn = document.getElementById('notifications');
        if (!bellBtn) return;
        
        // Add shake animation class
        bellBtn.classList.add('notification-bell-shake');
        
        // Add glow effect
        bellBtn.style.animation = 'notification-glow 1.5s ease-in-out';
        
        // Remove after animation
        setTimeout(() => {
            bellBtn.classList.remove('notification-bell-shake');
            bellBtn.style.animation = '';
        }, 1500);
    }

    function showToastNotification(data) {
        // Get popup notification container
        const container = document.getElementById('popup-notification-container');
        if (!container) {
            console.warn('Popup notification container not found');
            return;
        }
        
        // Get initials for avatar
        const getInitials = (name) => {
            if (!name) return '??';
            return name.split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase();
        };
        
        const initials = getInitials(data.title || 'Notification');
        
        // Create popup notification element
        const notification = document.createElement('div');
        notification.className = 'popup-notification';
        
        const messagePreview = (data.message || '').length > 100 
            ? (data.message || '').substring(0, 100) + '...' 
            : (data.message || '');
        
        notification.innerHTML = `
            <div class="popup-notification-header">
                <div class="popup-notification-avatar">${initials}</div>
                <div class="popup-notification-sender">${escapeHtml(data.title || 'Notification')}</div>
                <button class="popup-notification-close" onclick="event.stopPropagation(); this.closest('.popup-notification').remove();">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            <div class="popup-notification-message">${escapeHtml(messagePreview)}</div>
            <div class="popup-notification-footer">
                <i class="fas fa-bell"></i>
                <span>Just now</span>
            </div>
        `;
        
        // Click handler to open link
        if (data.link && data.link !== 'null' && data.link !== '') {
            notification.style.cursor = 'pointer';
            notification.addEventListener('click', function(e) {
                if (e.target.closest('.popup-notification-close')) return;
                window.location.href = data.link;
            });
        }
        
        // Add to container
        container.appendChild(notification);
        
        // Auto-remove after duration
        setTimeout(() => {
            if (notification.parentElement) {
                notification.classList.add('hiding');
                setTimeout(() => notification.remove(), 300);
            }
        }, CONFIG.NOTIFICATION_DURATION);
        
        // Limit to 3 notifications at a time
        const notifications = container.querySelectorAll('.popup-notification');
        if (notifications.length > 3) {
            const oldest = notifications[0];
            oldest.classList.add('hiding');
            setTimeout(() => oldest.remove(), 300);
        }
    }

    function showChatPopupNotification(data) {
        // Get popup notification container
        const container = document.getElementById('popup-notification-container');
        if (!container) {
            console.warn('Popup notification container not found');
            return;
        }
        
        // Get initials for avatar
        const getInitials = (name) => {
            if (!name) return '??';
            return name.split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase();
        };
        
        const senderName = data.from || 'Someone';
        const initials = getInitials(senderName);
        const message = data.message || data.text || '';
        const messagePreview = message.length > 100 ? message.substring(0, 100) + '...' : message;
        
        // Create popup notification element
        const notification = document.createElement('div');
        notification.className = 'popup-notification';
        
        notification.innerHTML = `
            <div class="popup-notification-header">
                <div class="popup-notification-avatar">${initials}</div>
                <div class="popup-notification-sender">${escapeHtml(senderName)}</div>
                <button class="popup-notification-close" onclick="event.stopPropagation(); this.closest('.popup-notification').remove();">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            <div class="popup-notification-message">${escapeHtml(messagePreview)}</div>
            <div class="popup-notification-footer">
                <i class="fas fa-comment-dots"></i>
                <span>New message</span>
            </div>
        `;
        
        // Click handler to open chat
        notification.style.cursor = 'pointer';
        notification.addEventListener('click', function(e) {
            if (e.target.closest('.popup-notification-close')) return;
            // Redirect to chat page
            window.location.href = '/chat/team/';
        });
        
        // Add to container
        container.appendChild(notification);
        
        // Auto-remove after 5 seconds (shorter for chat messages)
        setTimeout(() => {
            if (notification.parentElement) {
                notification.classList.add('hiding');
                setTimeout(() => notification.remove(), 300);
            }
        }, 5000);
        
        // Limit to 3 notifications at a time
        const notifications = container.querySelectorAll('.popup-notification');
        if (notifications.length > 3) {
            const oldest = notifications[0];
            oldest.classList.add('hiding');
            setTimeout(() => oldest.remove(), 300);
        }
    }

    function updateNotificationCount() {
        fetch('/api/notifications/unread-count')
            .then(res => res.json())
            .then(data => {
                setBadgeCount(data.count || 0);
            })
            .catch(error => console.error('Error fetching notification count:', error));
    }

    function setBadgeCount(count) {
        const badge = document.getElementById('notif-badge');
        if (!badge) return;
        
        if (count > 0) {
            badge.textContent = count > 99 ? '99+' : count;
            badge.classList.remove('hidden');
            badge.style.display = 'block';
        } else {
            badge.classList.add('hidden');
            badge.style.display = 'none';
        }
    }

    function setupDropdownHandlers() {
        // Close dropdown when clicking outside
        document.addEventListener('click', function(e) {
            const dropdown = document.getElementById('notifications-dropdown');
            const notifBtn = document.getElementById('notifications');
            if (dropdown && !dropdown.contains(e.target) && !notifBtn.contains(e.target)) {
                dropdown.style.display = 'none';
                notificationsDropdownOpen = false;
            }
        });
    }

    window.toggleNotificationsDropdown = function() {
        const dropdown = document.getElementById('notifications-dropdown');
        if (!dropdown) return;
        
        notificationsDropdownOpen = !notificationsDropdownOpen;
        
        if (notificationsDropdownOpen) {
            dropdown.style.display = 'block';
            loadNotificationsPreview();
        } else {
            dropdown.style.display = 'none';
        }
    };

    function loadNotificationsPreview() {
        const container = document.getElementById('notifications-list');
        if (!container) return;
        
        container.innerHTML = '<div style="text-align:center;padding:40px 20px;color:#9ca3af;"><i class="fa fa-spinner fa-spin" style="font-size:24px;"></i><p style="margin-top:12px;font-size:14px;">Loading...</p></div>';
        
        fetch('/api/notifications/list')
            .then(res => res.json())
            .then(data => {
                if (data.error) {
                    container.innerHTML = '<div style="padding:20px;text-align:center;color:#ef4444;">Error loading notifications</div>';
                    return;
                }
                
                const notifications = (data.notifications || []).slice(0, CONFIG.MAX_PREVIEW_NOTIFICATIONS);
                
                if (notifications.length === 0) {
                    container.innerHTML = `
                        <div style="text-align:center;padding:40px 20px;color:#9ca3af;">
                            <i class="fa fa-bell-slash" style="font-size:32px;color:#d1d5db;"></i>
                            <p style="margin-top:12px;font-size:14px;font-weight:600;">No notifications</p>
                            <p style="font-size:12px;margin-top:4px;">You're all caught up!</p>
                        </div>
                    `;
                    return;
                }
                
                let html = '';
                notifications.forEach(notif => {
                    const iconClass = getNotifIconClass(notif.type);
                    const iconBg = getNotifIconBg(notif.type);
                    const timeAgo = getNotifTimeAgo(notif.created_at);
                    const unreadDot = !notif.is_read ? '<div style="width:8px;height:8px;background:#3b82f6;border-radius:50%;margin-left:8px;"></div>' : '';
                    
                    html += `
                        <div onclick="handleNotifClick(${notif.id}, '${notif.link || ''}')" style="padding:12px 16px;border-bottom:1px solid #f3f4f6;cursor:pointer;transition:background 0.2s;${!notif.is_read ? 'background:#eff6ff;' : ''}" onmouseover="this.style.background='#f9fafb'" onmouseout="this.style.background='${!notif.is_read ? '#eff6ff' : 'white'}'">
                            <div style="display:flex;gap:12px;align-items:start;">
                                <div style="width:36px;height:36px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0;${iconBg}">
                                    <i class="${iconClass}"></i>
                                </div>
                                <div style="flex:1;min-width:0;">
                                    <div style="display:flex;align-items:center;">
                                        <div style="font-size:14px;font-weight:600;color:#1f2937;flex:1;">${escapeHtml(notif.title)}</div>
                                        ${unreadDot}
                                    </div>
                                    <div style="font-size:13px;color:#6b7280;margin-top:2px;line-height:1.4;">${escapeHtml(notif.message)}</div>
                                    <div style="font-size:11px;color:#9ca3af;margin-top:4px;"><i class="fa fa-clock"></i> ${timeAgo}</div>
                                </div>
                            </div>
                        </div>
                    `;
                });
                
                container.innerHTML = html;
            })
            .catch(error => {
                console.error('Error:', error);
                container.innerHTML = '<div style="padding:20px;text-align:center;color:#ef4444;">Failed to load notifications</div>';
            });
    }

    window.handleNotifClick = function(id, link) {
        // Get CSRF token
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || 
                          document.cookie.match('(^|;)\\s*csrftoken\\s*=\\s*([^;]+)')?.[2] || '';
        
        // Mark as read
        fetch('/api/notifications/mark-read', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ id: id })
        })
        .then(() => {
            updateNotificationCount();
            if (link && link !== 'null' && link !== '') {
                window.location.href = link;
            } else {
                window.location.href = '/notifications/';
            }
        })
        .catch(error => console.error('Error:', error));
    };

    // Utility functions
    function getNotifIconClass(type) {
        const icons = {
            'info': 'fa fa-info-circle',
            'success': 'fa fa-check-circle',
            'warning': 'fa fa-exclamation-triangle',
            'error': 'fa fa-times-circle',
            'task': 'fa fa-tasks',
            'project': 'fa fa-folder',
            'team': 'fa fa-users'
        };
        return icons[type] || 'fa fa-bell';
    }

    function getNotifIconBg(type) {
        const colors = {
            'info': 'background:#dbeafe;color:#1e40af;',
            'success': 'background:#d1fae5;color:#065f46;',
            'warning': 'background:#fef3c7;color:#92400e;',
            'error': 'background:#fee2e2;color:#991b1b;',
            'task': 'background:#e0e7ff;color:#4338ca;',
            'project': 'background:#dbeafe;color:#1e40af;',
            'team': 'background:#fce7f3;color:#9f1239;'
        };
        return colors[type] || 'background:#f3f4f6;color:#6b7280;';
    }

    function getNotifTypeClass(type) {
        return `notif-type-${type || 'info'}`;
    }

    function getNotifTimeAgo(dateString) {
        const date = new Date(dateString);
        const now = new Date();
        const seconds = Math.floor((now - date) / 1000);
        
        if (seconds < 60) return 'Just now';
        if (seconds < 3600) return Math.floor(seconds / 60) + 'm ago';
        if (seconds < 86400) return Math.floor(seconds / 3600) + 'h ago';
        if (seconds < 604800) return Math.floor(seconds / 86400) + 'd ago';
        
        return date.toLocaleDateString();
    }

    function updateOnlineStatus(userId, status) {
        // Update online/offline indicators in chat member list
        const memberElements = document.querySelectorAll(`[data-member-id="${userId}"]`);
        memberElements.forEach(el => {
            const statusIndicator = el.querySelector('.online-status');
            if (statusIndicator) {
                if (status === 'online') {
                    statusIndicator.classList.add('online');
                    statusIndicator.classList.remove('offline');
                } else {
                    statusIndicator.classList.add('offline');
                    statusIndicator.classList.remove('online');
                }
            }
        });
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Export for debugging
    window.NotificationSystem = {
        updateCount: updateNotificationCount,
        reconnect: setupNotificationWebSocket,
        playSound: playNotificationSound,
    };

})();
