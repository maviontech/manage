// core/static/core/js/notifications.js
/**
 * Real-Time Notification System
 * Handles WebSocket connections, desktop notifications, sound alerts, and UI updates
 */

(function() {
    'use strict';

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
        console.log('Initializing notification system...');
        
        // Request desktop notification permission
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
    }

    function requestDesktopNotificationPermission() {
        if (!("Notification" in window)) {
            console.warn("This browser does not support desktop notifications");
            return;
        }
        
        if (Notification.permission === "default") {
            Notification.requestPermission().then(permission => {
                if (permission === "granted") {
                    console.log("Desktop notification permission granted");
                } else {
                    console.log("Desktop notification permission denied");
                }
            });
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
        console.log('🔔 System notification:', data);
        
        // Play notification sound
        playNotificationSound();
        
        // Show desktop notification
        showDesktopNotification(data.title, data.message, data.link);
        
        // Animate bell icon
        animateBellIcon();
        
        // Update badge count
        updateNotificationCount();
        
        // Show toast notification
        showToastNotification(data);
    }

    function handleChatMessage(data) {
        // Only increment badge if not on chat page
        if (!window.location.pathname.startsWith('/chat')) {
            const badge = document.getElementById('notif-badge');
            if (badge) {
                let count = parseInt(badge.textContent || '0') || 0;
                count += 1;
                setBadgeCount(count);
            }
            
            // Play sound for chat messages too
            playNotificationSound();
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
        if (!CONFIG.DESKTOP_NOTIFICATIONS_ENABLED || !document.hidden) {
            return; // Only show if tab is not active
        }
        
        if (Notification.permission !== "granted") {
            return;
        }
        
        const notification = new Notification(title || 'New Notification', {
            body: message || 'You have a new update',
            icon: '/static/core/images/icon.png',
            badge: '/static/core/images/badge.png',
            tag: 'notification-' + Date.now(),
        });
        
        notification.onclick = function() {
            window.focus();
            if (link && link !== 'null' && link !== '') {
                window.location.href = link;
            }
            notification.close();
        };
        
        // Auto-close after duration
        setTimeout(() => notification.close(), CONFIG.NOTIFICATION_DURATION);
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
        // Create toast element
        const toast = document.createElement('div');
        toast.className = 'notification-toast';
        toast.innerHTML = `
            <div class="notification-toast-icon ${getNotifTypeClass(data.notification_type)}">
                <i class="${getNotifIconClass(data.notification_type)}"></i>
            </div>
            <div class="notification-toast-content">
                <div class="notification-toast-title">${escapeHtml(data.title || 'Notification')}</div>
                <div class="notification-toast-message">${escapeHtml(data.message || '')}</div>
            </div>
            <button class="notification-toast-close" onclick="this.parentElement.remove()">
                <i class="fa fa-times"></i>
            </button>
        `;
        
        // Add to page
        document.body.appendChild(toast);
        
        // Animate in
        setTimeout(() => toast.classList.add('show'), 10);
        
        // Auto-remove after duration
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, CONFIG.NOTIFICATION_DURATION);
        
        // Click to open link
        if (data.link) {
            toast.style.cursor = 'pointer';
            toast.addEventListener('click', function(e) {
                if (!e.target.classList.contains('notification-toast-close')) {
                    window.location.href = data.link;
                }
            });
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
