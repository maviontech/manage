// core/static/core/js/team_chat.js
        // Variables are passed from the HTML template as global constants:
        // TENANT_ID, CURRENT_USER, CURRENT_USER_NAME, CURRENT_MEMBER_ID, INITIAL_PEER
        
        console.log('Team chat script loaded');
        
        // Format display name: ensure first-name then surname for two-part names
        function formatDisplayName(name) {
            if (!name) return '';
            const parts = name.trim().split(/\s+/);
            if (parts.length === 2) {
                return parts[1] + ' ' + parts[0];
            }
            // if comma-separated like "Last, First"
            if (parts.length === 1 && name.indexOf(',') !== -1) {
                const p = name.split(',').map(s => s.trim());
                if (p.length === 2) return p[1] + ' ' + p[0];
            }
            return name;
        }
        // Set channel name from current user's email: take domain part after '@' (before first dot)
        (function(){
            try {
                const el = document.getElementById('channel-name');
                if (!el || !CURRENT_USER) return;
                const m = String(CURRENT_USER).match(/@([^\.\s]+)/);
                if (m && m[1]) el.textContent = m[1];
            } catch(e) { /* silent */ }
        })();
        const DISPLAY_CURRENT_USER_NAME = formatDisplayName(CURRENT_USER_NAME);

        let selectedPeer = null;
        let selectedPeerEmail = null;
        let selectedPeerName = '';
        let users = [];
        let members = [];
        let groups = [];
        let ws = null;
        let typingWS = null; // WebSocket for typing indicators
        let pollInterval = null;
        let lastMessageDate = 0;
        let typingTimeout = null;
        let remoteTypingTimeout = null; // Timeout for remote typing indicator
        // track appended messages to avoid re-rendering the feed (prevents blinking)
        let existingMessageIds = new Set();

        // Utility: normalize ID
        function normId(v) {
            return (v || '').toString().trim().toLowerCase();
        }

        // Get initials from name
        function getInitials(name) {
            return (name || '').split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase() || '??';
        }

        // Popup notification system
        const popupNotificationContainer = document.getElementById('popup-notification-container');
        let notificationQueue = [];
        let notificationSound = null;

        // Initialize notification sound
        function initNotificationSound() {
            try {
                // Try to load the audio file first
                notificationSound = new Audio('/static/core/sounds/notification.mp3');
                notificationSound.volume = 0.5;
                notificationSound.addEventListener('error', () => {
                    console.log('Audio file not found, will use Web Audio API');
                    notificationSound = null;
                });
            } catch (e) {
                console.log('Notification sound not available, will use Web Audio API');
            }
        }

        // Play notification sound
        function playNotificationSound() {
            if (notificationSound) {
                notificationSound.play().catch(e => {
                    console.log('Sound play failed:', e);
                    playBeepSound();
                });
            } else {
                playBeepSound();
            }
        }

        // Fallback: Generate a pleasant notification beep using Web Audio API
        function playBeepSound() {
            try {
                const audioContext = new (window.AudioContext || window.webkitAudioContext)();
                
                // Create a gentle two-tone notification sound
                const playTone = (frequency, startTime, duration) => {
                    const oscillator = audioContext.createOscillator();
                    const gainNode = audioContext.createGain();
                    
                    oscillator.connect(gainNode);
                    gainNode.connect(audioContext.destination);
                    
                    oscillator.frequency.value = frequency;
                    oscillator.type = 'sine';
                    
                    gainNode.gain.setValueAtTime(0, startTime);
                    gainNode.gain.linearRampToValueAtTime(0.2, startTime + 0.01);
                    gainNode.gain.linearRampToValueAtTime(0, startTime + duration);
                    
                    oscillator.start(startTime);
                    oscillator.stop(startTime + duration);
                };
                
                const now = audioContext.currentTime;
                playTone(800, now, 0.1);      // First tone
                playTone(1000, now + 0.12, 0.15); // Second tone (slightly higher)
            } catch (e) {
                console.log('Web Audio API not available:', e);
            }
        }

        // Show popup notification
        function showPopupNotification(senderName, senderEmail, message, groupName = null, groupId = null) {
            // For Direct Messages: Don't show if user is currently viewing this DM conversation
            const normalizedSenderEmail = normId(senderEmail);
            const normalizedCurrentPeer = normId(selectedPeerEmail || selectedPeer);
            
            if (!groupName && currentMode === 'dm' && normalizedSenderEmail === normalizedCurrentPeer) {
                console.log('🔕 Suppressing DM notification - user is viewing this conversation');
                return;
            }
            
            // For Group Messages: ALWAYS show to ALL group members (except sender)
            // Everyone in the group should see the notification, even if viewing the group
            if (groupName && groupId) {
                console.log('🔔 Showing group notification to all members:', { senderName, groupName, message });
            }

            console.log('🔔 Showing popup notification:', { senderName, senderEmail, message, groupName });

            // Get initials for avatar
            const initials = getInitials(senderName);
            
            // Create notification element
            const notification = document.createElement('div');
            notification.className = 'popup-notification';
            
            const messagePreview = message.length > 100 ? message.substring(0, 100) + '...' : message;
            const displayName = groupName ? `${senderName} (${groupName})` : senderName;
            
            notification.innerHTML = `
                <div class="popup-notification-header">
                    <div class="popup-notification-avatar">${initials}</div>
                    <div class="popup-notification-sender">${escapeHtml(displayName)}</div>
                    <button class="popup-notification-close" onclick="event.stopPropagation(); this.closest('.popup-notification').remove();">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                <div class="popup-notification-message">${escapeHtml(messagePreview)}</div>
                <div class="popup-notification-footer">
                    <i class="fas fa-comment-dots"></i>
                    <span>Click to reply</span>
                </div>
            `;
            
            // Click handler to open conversation
            notification.addEventListener('click', (e) => {
                if (e.target.closest('.popup-notification-close')) return;
                
                // Find and select the peer
                const member = members.find(m => normId(m.email) === normId(senderEmail));
                if (member) {
                    const memberId = member.id || senderEmail;
                    selectPeer(memberId, senderName, senderEmail);
                }
                
                // Remove notification
                notification.classList.add('hiding');
                setTimeout(() => notification.remove(), 300);
            });
            
            // Add to container
            popupNotificationContainer.appendChild(notification);
            
            // Play sound
            playNotificationSound();
            
            // Auto-remove after 5 seconds
            setTimeout(() => {
                if (notification.parentElement) {
                    notification.classList.add('hiding');
                    setTimeout(() => notification.remove(), 300);
                }
            }, 5000);
            
            // Limit to 3 notifications at a time
            const notifications = popupNotificationContainer.querySelectorAll('.popup-notification');
            if (notifications.length > 3) {
                const oldest = notifications[0];
                oldest.classList.add('hiding');
                setTimeout(() => oldest.remove(), 300);
            }
        }

        // Initialize sound on user interaction
        document.addEventListener('click', () => {
            if (!notificationSound) {
                initNotificationSound();
            }
        }, { once: true });

        // Get CSRF token
        function getCookie(name) {
            const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
            return v ? v.pop() : '';
        }

        // Load members into sidebar
        async function loadMembers() {
            const dmList = document.getElementById('dm-list');
            try {
                const res = await fetch('/chat/members/', { credentials: 'same-origin' });
                if (!res.ok) throw new Error('Failed to load');
                const data = await res.json();
                members = data.members || [];
                
                document.getElementById('total-members').textContent = members.length;
                dmList.innerHTML = '';
                console.log('Members:', members);
                members.forEach(m => {
                    const memberId = (m.id !== undefined && m.id !== null) ? m.id.toString() : normId(m.email);
                    const rawName = (m.name || '').replace(/<[^>]+>/g, '').trim() || memberId;
                    const memberEmail = (m.email || '').trim().toLowerCase();
                    const memberName = formatDisplayName(rawName);
                    const isSelf = !!m.is_self;

                    const div = document.createElement('div');
                    div.className = 'dm-item' + (isSelf ? '' : '');
                    // use numeric member id for data-id and URL
                    div.dataset.id = memberId;
                    // expose member email for presence indicator toggling
                    div.dataset.userEmail = memberEmail;
                    div.dataset.name = memberName;
                    div.dataset.self = isSelf ? 'true' : 'false';

                    const initials = getInitials(memberName.split('<')[0].trim());

                    div.innerHTML = `
                        <div class="dm-user" data-user-email="${memberEmail}">
                            <span class="user-pic-sm" data-user-email="${memberEmail}">
                                ${initials}
                                <span class="presence-indicator ${isSelf ? 'online' : ''}"></span>
                            </span>
                            <span class="dm-name">${memberName.split('<')[0].trim() || memberId}</span>
                        </div>
                        <span class="badge" style="display:none;" data-unread-for="${memberId}">0</span>
                    `;

                    if (!isSelf) {
                        div.addEventListener('click', () => selectPeer(memberId, memberName, memberEmail));
                    } else {
                        div.style.opacity = '0.6';
                        div.style.cursor = 'default';
                    }

                    dmList.appendChild(div);
                });

                    // If page was opened via /chat/dm/<email>/, auto-select that peer
                    try {
                        if (INITIAL_PEER) {
                            const el = document.querySelector(`.dm-item[data-id="${INITIAL_PEER}"]`);
                            if (el) {
                                const name = el.dataset.name || el.querySelector('.dm-name') && el.querySelector('.dm-name').textContent;
                                const email = el.dataset.userEmail || '';
                                selectPeer(INITIAL_PEER, name, email);
                            }
                        }
                    } catch (e) { console.warn('auto-select initial peer failed', e); }

                refreshUnreadCounts();
            } catch (e) {
                console.error('loadMembers error', e);
                dmList.innerHTML = '<div style="padding:16px;color:#ff6b6b;">Error loading members</div>';
            }
        }

        // Select peer to chat with
        function selectPeer(peerId, peerName, peerEmail) {
            currentMode = 'dm';
            selectedGroup = null;
            selectedPeer = (peerId || '').trim().toLowerCase();
            selectedPeerEmail = (peerEmail || '').trim().toLowerCase();
            selectedPeerName = (peerName || '').split('<')[0].trim() || selectedPeer;

            // Update sidebar active state
            document.querySelectorAll('.dm-item').forEach(el => el.classList.remove('active'));
            const dmItem = document.querySelector(`.dm-item[data-id="${selectedPeer}"]`);
            if (dmItem) dmItem.classList.add('active');

            // Update header
            const headerTitle = document.getElementById('chat-header-title');
            headerTitle.innerHTML = `<span style="margin-right: 5px;">@</span> ${selectedPeerName}`;

            // Update browser URL (without reload)
            if (window.history && window.history.pushState) {
                const url = `/chat/peer/${encodeURIComponent(selectedPeer)}/`;
                window.history.pushState({peer: selectedPeer}, '', url);
            }

            // Show input
            document.getElementById('input-container').style.display = 'block';

            // Load messages
            loadHistory();
            initWebSocket();

            // Mark existing messages as read when opening conversation
            markRead(selectedPeer);
            const badge = document.querySelector(`[data-unread-for="${selectedPeer}"]`);
            if (badge) badge.style.display = 'none';
        }

        // Load chat history
        async function loadHistory() {
            const feed = document.getElementById('messages-feed');
            feed.innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Loading messages...</div>';

            try {
                const res = await fetch(`/chat/history/?peer=${encodeURIComponent(selectedPeer)}`, { credentials: 'same-origin' });
                if (!res.ok) throw new Error('Failed to load');
                const data = await res.json();
                
                // reset tracking for this conversation (initial load)
                existingMessageIds = new Set();
                feed.innerHTML = '';
                const msgs = (data.messages || []).sort((a, b) => new Date(a.created_at) - new Date(b.created_at));

                if (!msgs.length) {
                    feed.innerHTML = `
                        <div class="no-messages">
                            <i class="far fa-comment-dots"></i>
                            <p>No messages yet. Say hello!</p>
                        </div>
                    `;
                } else {
                    msgs.forEach(m => appendMessage(m));
                }
                feed.scrollTop = feed.scrollHeight;
            } catch (e) {
                console.error('loadHistory error', e);
                feed.innerHTML = '<div class="no-messages"><i class="fas fa-exclamation-triangle"></i><p>Error loading messages</p></div>';
            }
        }

        // Append a message to the feed
        // Find member name by id/email
        function getMemberNameById(id) {
            if (!id) return id;
            const norm = normId(id);
            for (const m of members) {
                if (normId(m.id) === norm) return m.name || m.id;
                if (normId(m.email) === norm) return m.name || m.email;
            }
            return id;
        }

        function appendMessage(m) {
            // Check for duplicates before appending
            if (m.id && existingMessageIds.has(String(m.id))) {
                console.log('⏭️ Skipping duplicate message with id:', m.id);
                return;
            }
            if (m.cid && existingMessageIds.has(String(m.cid))) {
                console.log('⏭️ Skipping duplicate message with cid:', m.cid);
                return;
            }
            
            const feed = document.getElementById('messages-feed');
            const sender = normId(m.sender || m.from);
            // console.log('appendMessage:', {CURRENT_USER, sender, m});
            const isMe = sender === normId(CURRENT_USER);
            const senderName = isMe ? DISPLAY_CURRENT_USER_NAME : getMemberNameById(sender);
            const initials = getInitials(senderName);

            let timeStr = '';
            if (m.created_at) {
                const d = new Date(m.created_at);
                const pad = n => n < 10 ? '0' + n : n;
                const now = new Date();
                if (d.toDateString() === now.toDateString()) {
                    timeStr = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
                } else {
                    timeStr = `${pad(d.getDate())}/${pad(d.getMonth()+1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
                }
            }

            const msgEl = document.createElement('div');
            msgEl.className = 'message-group';
            if (isMe) msgEl.classList.add('sent-message');
            msgEl.innerHTML = `
                <div class="avatar">${initials}</div>
                <div class="message-content">
                    <div class="message-header">
                        <span class="username">${senderName}</span>
                        <span class="timestamp">${timeStr}</span>
                    </div>
                    <div class="text">${escapeHtml(m.text || '')}</div>
                </div>
            `;
            // insert date separator when day changes
            try {
                if (m.created_at) {
                    const d = new Date(m.created_at);
                    const day = d.toDateString();
                    if (lastMessageDate !== day) {
                        lastMessageDate = day;
                        const sep = document.createElement('div');
                        sep.className = 'date-sep';
                        sep.textContent = d.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });
                        feed.appendChild(sep);
                    }
                }
            } catch (err) { /* ignore date errors */ }

            msgEl.classList.add('msg-enter');
            // annotate avatar with sender email so presence indicator can be toggled
            try{
                const avatarEl = msgEl.querySelector('.avatar');
                if(avatarEl) avatarEl.dataset.userEmail = sender;
            }catch(e){}
            // attach message id and cid for later read-receipt updates and optimistic matching
            if (m.id) {
                try { msgEl.dataset.messageId = String(m.id); } catch(e){}
            }
            if (m.cid) {
                try { msgEl.dataset.cid = String(m.cid); } catch(e){}
            }
            // add status icon for sent messages (single check = sent, double check = read)
            if (isMe) {
                const status = document.createElement('span');
                status.className = 'msg-status';
                const icon = document.createElement('i');
                // default: single check (sent)
                icon.className = 'fas fa-check';
                status.appendChild(icon);
                // if server indicates already read, switch to double-check look
                if (m.is_read === 1 || m.is_read === true || String(m.is_read) === '1') {
                    status.classList.add('read');
                    icon.className = 'fas fa-check-double';
                }
                // attach after message-content
                try { msgEl.querySelector('.message-content').appendChild(status); } catch(e){}
            }
            feed.appendChild(msgEl);
            // smooth scroll into view
            try { feed.scroll({ top: feed.scrollHeight, behavior: 'smooth' }); } catch (e) { feed.scrollTop = feed.scrollHeight; }
            // record message identifiers so polling doesn't duplicate
            try {
                if (m.id) existingMessageIds.add(String(m.id));
                if (m.cid) existingMessageIds.add(String(m.cid));
            } catch (e) { /* ignore */ }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // WebSocket for real-time
        function initWebSocket() {
            if (ws) {
                try { ws.close(); } catch (e) {}
                ws = null;
            }
            console.log('initWebSocket called', {TENANT_ID, selectedPeer, selectedGroup, currentMode});
            
            // Validate tenant ID before attempting connection
            if (!TENANT_ID || TENANT_ID === 'None' || TENANT_ID === 'null' || TENANT_ID === 'undefined') {
                console.error('Cannot initialize WebSocket: Invalid tenant ID');
                showToast('Unable to connect to chat. Missing tenant information.');
                startPolling(); // Fall back to polling
                return;
            }
            
            if (!selectedPeer && !selectedGroup) return;
            
            // Initialize typing indicator WebSocket if not already connected
            initTypingWebSocket();
            
            // Build querystring for websocket: support peer (DM) or group
            let qs = `?tenant=${encodeURIComponent(TENANT_ID)}`;
            if (currentMode === 'group' && selectedGroup) {
                qs += `&group=${encodeURIComponent(selectedGroup)}`;
            } else if (selectedPeer) {
                qs += `&peer=${encodeURIComponent(selectedPeer)}`;
            }
            const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
            const url = `${scheme}://${window.location.host}/ws/chat/${qs}`;
            
            try {
                ws = new WebSocket(url);
                console.log('Initializing WebSocket...', ws);
                ws.onopen = () => console.log('WebSocket connected');
                ws.onmessage = (ev) => {
                    let msg;
                    console.log('📨 WebSocket raw message:', ev.data);
                    try { msg = JSON.parse(ev.data); } catch (e) { return; }
                    
                    console.log('📨 WebSocket parsed message:', msg);
                    console.log('📨 Message type/event:', msg.type, msg.event);

                    
                    // Handle new_message events from ChatConsumer
                    if (msg.type === 'new_message') {
                        // Consumer sends: {type: 'new_message', message: text, from: sender, to: receiver, created_at: timestamp}
                        const senderEmail = (msg.from || '').toLowerCase();
                        const toEmail = (msg.to || '').toLowerCase();
                        const messageText = msg.message || '';
                        const timestamp = msg.created_at;
                        
                        console.log('💬 New message:', { senderEmail, toEmail, messageText, currentMode, selectedPeer });
                        
                        // Check if this message is from someone else (not current user)
                        const myEmail = normId(CURRENT_USER);
                        const myMemberId = normId(CURRENT_MEMBER_ID);
                        const normalizedSender = normId(senderEmail);
                        const isFromOther = (normalizedSender !== myEmail && normalizedSender !== myMemberId);
                        
                        // Show popup notification for incoming DM messages from others
                        if (isFromOther && messageText) {
                            const senderMember = members.find(m => normId(m.email) === normalizedSender);
                            const senderName = senderMember ? formatDisplayName((senderMember.name || '').replace(/<[^>]+>/g, '').trim() || senderEmail) : senderEmail;
                            // DM notification - only show if not viewing this conversation
                            showPopupNotification(senderName, senderEmail, messageText, null, null);
                        }
                        
                        // For DM: only show if this message is relevant to current conversation
                        if (currentMode === 'dm' && selectedPeer) {
                            const myEmail = normId(CURRENT_USER);
                            const myMemberId = normId(CURRENT_MEMBER_ID);
                            const peerEmailNorm = normId(selectedPeerEmail || selectedPeer);
                            const peerIdNorm = normId(selectedPeer);
                            const normalizedSender = normId(senderEmail);
                            const normalizedTo = normId(toEmail);
                            
                            // Show message if: (from peer to me) OR (from me to peer)
                            // Compare both email and ID since WebSocket might send either
                            const fromPeer = (normalizedSender === peerEmailNorm || normalizedSender === peerIdNorm);
                            const toMe = (normalizedTo === myEmail || normalizedTo === myMemberId);
                            const fromMe = (normalizedSender === myEmail || normalizedSender === myMemberId);
                            const toPeer = (normalizedTo === peerEmailNorm || normalizedTo === peerIdNorm);
                            
                            const isRelevant = (fromPeer && toMe) || (fromMe && toPeer);
                            
                            console.log('🔍 DM relevance check:', { normalizedSender, normalizedTo, myEmail, myMemberId, peerEmailNorm, peerIdNorm, fromPeer, toMe, fromMe, toPeer, isRelevant });
                            
                            if (isRelevant) {
                                // Check if this message was already added optimistically
                                const cid = msg.cid;
                                if (cid) {
                                    const existing = document.querySelector(`[data-cid="${cid}"]`);
                                    if (existing) {
                                        console.log('✅ Matched optimistic message with CID:', cid);
                                        // Update the optimistic message with server confirmation
                                        try {
                                            const statusIcon = existing.querySelector('.msg-status i');
                                            if (statusIcon) {
                                                statusIcon.className = 'fas fa-check-double';
                                                existing.querySelector('.msg-status').classList.add('delivered');
                                            }
                                        } catch (e) { /* ignore */ }
                                        return; // Don't append duplicate
                                    }
                                }
                                
                                const incoming = {
                                    sender: senderEmail,
                                    sender_name: senderEmail.split('@')[0],
                                    text: messageText,
                                    created_at: timestamp,
                                    from: senderEmail,
                                    id: msg.id,  // Store message ID for read receipts
                                    cid: cid
                                };
                                appendMessage(incoming);
                                
                                // Immediately mark as read if sender is the peer (recipient is viewing the chat)
                                // This will turn the sender's check marks blue instantly
                                if (normalizedSender === peerEmailNorm || normalizedSender === peerIdNorm) {
                                    console.log('🔵 Auto-marking message as read (recipient is viewing chat)');
                                    markRead(selectedPeer);
                                }
                            }
                        }
                    }
                    
                    // Legacy format support (msg.event === 'message')
                    if (msg.event === 'message' && msg.message) {
                                    // If this message includes a client cid, try to match optimistic message
                                    const incoming = msg.message || {};
                                    const cid = incoming.cid;
                                    const senderNorm = normId(incoming.sender || incoming.from || '');
                                    const incomingGroupId = incoming.group_id;
                                    
                                    // Handle group messages
                                    if (incomingGroupId) {
                                        console.log('💬 Group message received:', incoming);
                                        
                                        // Show popup notification for group messages from others
                                        const myEmail = normId(CURRENT_USER);
                                        const myMemberId = normId(CURRENT_MEMBER_ID);
                                        const normalizedSender = normId(incoming.sender || incoming.from || '');
                                        const isFromOther = (normalizedSender !== myEmail && normalizedSender !== myMemberId);
                                        
                                        console.log('🔍 Group notification check:', {
                                            myEmail,
                                            myMemberId,
                                            normalizedSender,
                                            isFromOther,
                                            hasText: !!incoming.text,
                                            groupsLoaded: groups.length,
                                            membersLoaded: members.length
                                        });
                                        
                                        if (isFromOther && incoming.text) {
                                            const senderMember = members.find(m => normId(m.email) === normalizedSender);
                                            const senderName = senderMember ? formatDisplayName((senderMember.name || '').replace(/<[^>]+>/g, '').trim() || normalizedSender) : normalizedSender;
                                            const group = groups.find(g => String(g.id) === String(incomingGroupId));
                                            const groupName = group ? group.name : 'Group';
                                            
                                            console.log('🔔 Triggering group notification:', {
                                                senderName,
                                                groupName,
                                                groupId: incomingGroupId,
                                                message: incoming.text.substring(0, 50)
                                            });
                                            
                                            // Group messages: ALWAYS show popup to all group members (except sender)
                                            // Everyone in the group should see the notification
                                            showPopupNotification(senderName, normalizedSender, incoming.text, groupName, incomingGroupId);
                                        }
                                        
                                        // Only show if we're viewing this group
                                        if (currentMode === 'group' && String(selectedGroup) === String(incomingGroupId)) {
                                            if (cid) {
                                                const existing = document.querySelector(`[data-cid="${cid}"]`);
                                                if (existing) {
                                                    console.log('✅ Matched optimistic group message with CID:', cid);
                                                    // Update the optimistic message
                                                    try {
                                                        if (incoming.id) existing.dataset.messageId = String(incoming.id);
                                                        const txt = existing.querySelector('.text');
                                                        if (txt && incoming.text) txt.innerHTML = escapeHtml(incoming.text);
                                                        const ts = existing.querySelector('.timestamp');
                                                        if (ts && incoming.created_at) {
                                                            const d = new Date(incoming.created_at);
                                                            const pad = n => n < 10 ? '0' + n : n;
                                                            ts.textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
                                                        }
                                                    } catch (e) { /* ignore */ }
                                                    return; // Don't append duplicate
                                                }
                                            }
                                            // Append the group message if not optimistic or not found
                                            appendMessage(incoming);
                                        }
                                        return; // Handled group message
                                    }
                                    
                                    // Handle DM messages
                                    if (cid) {
                                        const existing = document.querySelector(`[data-cid="${cid}"]`);
                                        if (existing) {
                                            // update existing optimistic element instead of duplicating
                                            try {
                                                if (incoming.id) existing.dataset.messageId = String(incoming.id);
                                                // update text and timestamp if server provides authoritative values
                                                const txt = existing.querySelector('.text');
                                                if (txt && incoming.text) txt.innerHTML = escapeHtml(incoming.text);
                                                const ts = existing.querySelector('.timestamp');
                                                if (ts && incoming.created_at) {
                                                    const d = new Date(incoming.created_at);
                                                    const pad = n => n < 10 ? '0' + n : n;
                                                    ts.textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
                                                }
                                                // mark as delivered (server confirmed)
                                                let st = existing.querySelector('.msg-status');
                                                if (!st) {
                                                    st = document.createElement('span'); st.className = 'msg-status'; const ic=document.createElement('i'); ic.className='fas fa-check-double'; st.appendChild(ic); existing.querySelector('.message-content').appendChild(st);
                                                }
                                                st.classList.add('delivered');
                                            } catch (e) { /* ignore */ }
                                            // if the message came from someone else, don't mark read here
                                        } else {
                                            appendMessage(incoming);
                                        }
                                    } else {
                                        appendMessage(incoming);
                                    }

                                    if (currentMode === 'dm') {
                                        // Immediately mark as read if message is from the current peer
                                        // This ensures sender sees blue checkmarks instantly
                                        if (senderNorm !== normId(CURRENT_USER) && senderNorm === normId(selectedPeer)) {
                                            console.log('🔵 Auto-marking legacy message as read (recipient is viewing chat)');
                                            markRead(selectedPeer);
                                        }
                                    }
                    }

                    // Read receipts: server broadcasts which message ids were marked read
                    if (msg.event === 'message_read' && msg.message_ids && Array.isArray(msg.message_ids)) {
                        console.log('📖 Received read receipts for message IDs:', msg.message_ids);
                        msg.message_ids.forEach(id => {
                            try {
                                const el = document.querySelector(`[data-message-id="${id}"]`);
                                if (el) {
                                    console.log('✅ Updating read status for message:', id);
                                    // update or add status icon to show read
                                    let st = el.querySelector('.msg-status');
                                    if (!st) {
                                        st = document.createElement('span');
                                        st.className = 'msg-status';
                                        const ic = document.createElement('i');
                                        ic.className = 'fas fa-check-double';
                                        st.appendChild(ic);
                                        el.querySelector('.message-content').appendChild(st);
                                    }
                                    // mark as read style and double-check icon with blue color
                                    st.classList.add('read');
                                    const ic = st.querySelector('i');
                                    if (ic) {
                                        ic.className = 'fas fa-check-double';
                                        ic.style.color = '#0A7AFF';
                                    }
                                }
                            } catch(e){ console.error('Error updating read receipt:', e); }
                        });
                    }

                    // Handle presence updates
                    if (msg.type === 'presence_update') {
                        const userEmail = (msg.user_email || '').toLowerCase();
                        const status = msg.status || 'offline';
                        console.log('👤 Presence update:', userEmail, status);
                        // Find all user-pic-sm elements for this user and update their presence indicators
                        const userPics = document.querySelectorAll(`.user-pic-sm[data-user-email="${userEmail}"]`);
                        userPics.forEach(userPic => {
                            const indicator = userPic.querySelector('.presence-indicator');
                            if (indicator) {
                                if (status === 'online') {
                                    indicator.classList.add('online');
                                    console.log('✅ Set online indicator for:', userEmail);
                                } else {
                                    indicator.classList.remove('online');
                                    console.log('❌ Removed online indicator for:', userEmail);
                                }
                            }
                        });
                    }
                    
                    // presence / notification events (unread badges)
                    if (msg.event === 'new_group_message') {
                        const gid = msg.group_id || msg.message && msg.message.group_id;
                        if (!gid) return;
                        // if current group is open, ignore (we already appended)
                        if (currentMode === 'group' && String(selectedGroup) === String(gid)) return;
                        // increment badge or set from payload
                        const badge = document.querySelector(`[data-unread-for-group="${gid}"]`);
                        if (badge) {
                            let cur = parseInt(badge.textContent || '0') || 0;
                            cur += 1;
                            badge.textContent = cur;
                            badge.style.display = '';
                        } else {
                            // reload groups to get accurate counts
                            loadGroups();
                        }
                    }
                };
                ws.onclose = () => {
                    console.log('WebSocket closed, falling back to polling');
                    startPolling();
                };
            } catch (e) {
                console.warn('WebSocket failed', e);
                startPolling();
            }
        }

        // Typing indicator WebSocket
        function initTypingWebSocket() {
            // Only initialize once
            if (typingWS && typingWS.readyState === WebSocket.OPEN) {
                return;
            }
            
            if (typingWS) {
                try { typingWS.close(); } catch (e) {}
                typingWS = null;
            }
            
            if (!TENANT_ID || TENANT_ID === 'None' || TENANT_ID === 'null' || TENANT_ID === 'undefined') {
                console.error('Cannot initialize typing WebSocket: Invalid tenant ID');
                return;
            }
            
            const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
            const url = `${scheme}://${window.location.host}/ws/is_typing/?tenant=${encodeURIComponent(TENANT_ID)}`;
            
            try {
                typingWS = new WebSocket(url);
                
                typingWS.onopen = () => {
                    console.log('✅ Typing indicator WebSocket connected');
                };
                
                typingWS.onmessage = (ev) => {
                    try {
                        const data = JSON.parse(ev.data);
                        console.log('📝 Typing event received:', data);
                        
                        if (data.event === 'typing' || data.type === 'typing.update') {
                            handleTypingIndicator(data);
                        }
                    } catch (e) {
                        console.error('Error parsing typing event:', e);
                    }
                };
                
                typingWS.onerror = (err) => {
                    console.error('❌ Typing WebSocket error:', err);
                };
                
                typingWS.onclose = () => {
                    console.log('🔌 Typing WebSocket closed');
                    // Reconnect after 3 seconds
                    setTimeout(() => {
                        if (!typingWS || typingWS.readyState === WebSocket.CLOSED) {
                            initTypingWebSocket();
                        }
                    }, 3000);
                };
            } catch (e) {
                console.error('Failed to create typing WebSocket:', e);
            }
        }

        // Send typing indicator to server
        function sendTypingIndicator(status) {
            if (!typingWS || typingWS.readyState !== WebSocket.OPEN) {
                return;
            }
            
            if (!selectedPeer) {
                return;
            }
            
            const payload = {
                type: 'typing',
                from: CURRENT_USER,
                to: selectedPeerEmail || selectedPeer,
                status: status // 'typing' or 'idle'
            };
            
            console.log('📤 Sending typing indicator:', payload);
            typingWS.send(JSON.stringify(payload));
        }

        // Handle typing indicator from remote user
        function handleTypingIndicator(data) {
            const fromUser = normId(data.from || '');
            const toUser = normId(data.to || '');
            const status = data.status;
            
            const myEmail = normId(CURRENT_USER);
            const currentPeerEmail = normId(selectedPeerEmail || selectedPeer);
            
            console.log('📝 Processing typing indicator:', {
                fromUser,
                toUser,
                status,
                myEmail,
                currentPeerEmail,
                isForMe: toUser === myEmail,
                isFromCurrentPeer: fromUser === currentPeerEmail
            });
            
            // Only show typing indicator if:
            // 1. The message is directed to me (toUser === myEmail)
            // 2. The sender is the person I'm currently chatting with (fromUser === currentPeerEmail)
            if (toUser === myEmail && fromUser === currentPeerEmail) {
                const feed = document.getElementById('messages-feed');
                const existing = document.getElementById('remote-typing-indicator');
                
                if (status === 'typing') {
                    // Remove old indicator
                    if (existing) existing.remove();
                    
                    // Clear previous timeout
                    if (remoteTypingTimeout) clearTimeout(remoteTypingTimeout);
                    
                    // Find sender name
                    const senderMember = members.find(m => normId(m.email) === fromUser);
                    const senderName = senderMember ? formatDisplayName((senderMember.name || '').replace(/<[^>]+>/g, '').trim() || fromUser) : fromUser;
                    
                    // Create typing indicator
                    const indicator = document.createElement('div');
                    indicator.id = 'remote-typing-indicator';
                    indicator.className = 'message-group';
                    indicator.style.opacity = '0.7';
                    
                    const initials = getInitials(senderName);
                    
                    indicator.innerHTML = `
                        <div class="avatar" style="background:linear-gradient(135deg, #667eea 0%, #764ba2 100%);color:white;">
                            ${initials}
                        </div>
                        <div class="message-content">
                            <div class="message-header">
                                <span class="username">${escapeHtml(senderName)}</span>
                            </div>
                            <div class="text" style="color:var(--text-muted);font-style:italic;">
                                <i class="fas fa-circle-notch fa-spin" style="font-size:10px;margin-right:4px;"></i>
                                is typing...
                            </div>
                        </div>
                    `;
                    
                    feed.appendChild(indicator);
                    try { 
                        feed.scroll({ top: feed.scrollHeight, behavior: 'smooth' }); 
                    } catch (err) { 
                        feed.scrollTop = feed.scrollHeight; 
                    }
                    
                    // Auto-remove after 3 seconds if no update
                    remoteTypingTimeout = setTimeout(() => {
                        const el = document.getElementById('remote-typing-indicator');
                        if (el) el.remove();
                    }, 3000);
                } else if (status === 'idle') {
                    // Remove typing indicator
                    if (existing) existing.remove();
                    if (remoteTypingTimeout) clearTimeout(remoteTypingTimeout);
                }
            }
        }

        // Incremental polling: fetch only new messages and append (no visible reload/blink)
        async function pollForNewMessages() {
            if (!selectedPeer) return;
            try {
                const res = await fetch(`/chat/history/?peer=${encodeURIComponent(selectedPeer)}`, { credentials: 'same-origin' });
                if (!res.ok) return;
                const data = await res.json();
                const msgs = (data.messages || []).sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
                for (const m of msgs) {
                    const mid = m.id ? String(m.id) : (m.cid ? String(m.cid) : null);
                    if (!mid) {
                        // no id — append if not present by comparing text+timestamp
                        appendMessage(m);
                        continue;
                    }
                    if (!existingMessageIds.has(mid)) {
                        appendMessage(m);
                    }
                }
            } catch (e) { /* silent fallback */ }
        }

        async function pollForNewGroupMessages() {
            if (!selectedGroup) return;
            try {
                const res = await fetch(`/chat/group/history/?group_id=${encodeURIComponent(selectedGroup)}`, { credentials: 'same-origin' });
                if (!res.ok) return;
                const data = await res.json();
                const msgs = (data.messages || []).sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
                for (const m of msgs) {
                    const mid = m.id ? String(m.id) : (m.cid ? String(m.cid) : null);
                    if (!mid) { appendMessage(m); continue; }
                    if (!existingMessageIds.has(mid)) appendMessage(m);
                }
            } catch (e) { /* silent fallback */ }
        }

        function startPolling() {
            // if already polling, do nothing
            if (pollInterval) return;
            // only start polling when there is an active target (peer or group)
            if (!selectedPeer && !selectedGroup) return;
            // poll for new messages every 5s when websocket is not available
            pollInterval = setInterval(() => {
                if (currentMode === 'dm' && selectedPeer) pollForNewMessages();
                if (currentMode === 'group' && selectedGroup) pollForNewGroupMessages();
            }, 5000);
        }

        // --- Group helpers ---
        async function loadGroups() {
            const el = document.getElementById('group-list');
            if (!el) return;
            el.innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Loading groups...</div>';
            try {
                const res = await fetch('/chat/groups/', { credentials: 'same-origin' });
                if (!res.ok) throw new Error('Failed');
                const data = await res.json();
                el.innerHTML = '';
                groups = data.groups || [];  // Assign to global variable, not local const
                // store members/unread map
                window._chat_group_meta = window._chat_group_meta || {};
                groups.forEach(g => {
                    window._chat_group_meta[g.id] = { members: g.members || [], unread: g.unread || 0 };
                    const d = document.createElement('div');
                    d.className = 'dm-item';
                    d.dataset.groupId = g.id;
                    d.innerHTML = `<div class="dm-user"><span class="user-pic-sm">${(g.name||'G').split(' ').map(s=>s[0]).slice(0,2).join('').toUpperCase()}</span><span class="dm-name">${g.name} <span style="font-size:11px;color:var(--sidebar-text-dim);">(${g.member_count})</span></span></div><span class="badge" data-unread-for-group="${g.id}" style="margin-left:auto;${(g.unread||0)>0 ? '' : 'display:none;'}">${g.unread||0}</span>`;
                    d.addEventListener('click', ()=> selectGroup(g.id, g.name));
                    el.appendChild(d);
                });
                if (groups.length === 0) el.innerHTML = '<div style="padding:12px;color:var(--text-muted);">No groups yet. Create one with the + button.</div>';
            } catch (e) {
                el.innerHTML = '<div style="padding:12px;color:#ff6b6b;">Error loading groups</div>';
            }
        }

        function selectGroup(groupId, groupName) {
            console.log('Selecting group', groupId, groupName);
            currentMode = 'group';
            selectedGroup = groupId;
            // clear DM selection
            document.querySelectorAll('.dm-item').forEach(el=>el.classList.remove('active'));
            const el = document.querySelector(`.dm-item[data-group-id="${groupId}"]`);
            if (el) el.classList.add('active');
            const headerTitle = document.getElementById('chat-header-title');
            headerTitle.innerHTML = `<i class="fas fa-users" style="margin-right:8px;opacity:0.6;"></i> ${groupName}`;
            document.getElementById('input-container').style.display = 'block';
            loadGroupHistory();
            initWebSocket();
            startPolling();

            // update header members count and show settings
            const meta = (window._chat_group_meta || {})[groupId] || { members: [] };
            document.getElementById('total-members').textContent = meta.members.length || 0;
            const memberDisplay = document.getElementById('member-count-display');
            memberDisplay.style.cursor = 'pointer';
            memberDisplay.onclick = () => showGroupMembersModal(groupId);
            const settingsBtn = document.getElementById('group-settings-btn');
            if (settingsBtn) { settingsBtn.style.display = 'inline-block'; settingsBtn.onclick = () => showGroupSettingsModal(groupId, groupName); }
            // hide unread badge for this group (we will mark read)
            const badge = document.querySelector(`[data-unread-for-group="${groupId}"]`);
            if (badge) badge.style.display = 'none';
            // mark group read on server
            try { fetch('/chat/group/mark_read/', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type':'application/json', 'X-CSRFToken': getCookie('csrftoken') }, body: JSON.stringify({ group_id: groupId }) }); } catch(e){}
        }

        async function loadGroupHistory() {
            if (!selectedGroup) return;
            const feed = document.getElementById('messages-feed');
            feed.innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Loading messages...</div>';
            try {
                const res = await fetch(`/chat/group/history/?group_id=${encodeURIComponent(selectedGroup)}`, { credentials: 'same-origin' });
                if (!res.ok) throw new Error('Failed');
                const data = await res.json();
                // reset tracking for this group (initial load)
                existingMessageIds = new Set();
                feed.innerHTML = '';
                const msgs = (data.messages || []).sort((a,b)=>new Date(a.created_at)-new Date(b.created_at));
                if (!msgs.length) {
                    feed.innerHTML = `<div class="no-messages"><i class="far fa-comment-dots"></i><p>No messages yet in this group.</p></div>`;
                } else {
                    msgs.forEach(m=> appendMessage(m));
                }
                feed.scrollTop = feed.scrollHeight;
            } catch (e) {
                console.error('loadGroupHistory error', e);
                feed.innerHTML = '<div class="no-messages"><i class="fas fa-exclamation-triangle"></i><p>Error loading messages</p></div>';
            }
        }

        // Create group button handling
        const createGroupBtn = document.getElementById('create-group-btn');
        if (createGroupBtn) {
            createGroupBtn.addEventListener('click', async ()=>{
                const name = prompt('Group name:');
                if (!name) return;
                const members = prompt('Comma-separated emails or member ids to add (optional):');
                const arr = members ? members.split(',').map(s=>s.trim()).filter(Boolean) : [];
                try {
                    const res = await fetch('/chat/groups/create/', {
                        method: 'POST',
                        credentials: 'same-origin',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken'),
                        },
                        body: JSON.stringify({ name: name.trim(), members: arr })
                    });
                    if (!res.ok) throw new Error('Create failed');
                    const data = await res.json();
                    if (data && data.ok) {
                        showToast('Group created');
                        loadGroups();
                    } else {
                        showToast('Create failed');
                    }
                } catch (e) { console.error('create group', e); showToast('Create failed'); }
            });
        }

        // --- Group members & settings modal UI ---
        function showGroupMembersModal(groupId) {
            const meta = (window._chat_group_meta || {})[groupId] || { members: [] };
            let html = `<div style="padding:14px;"><h3>Members</h3><ul style="list-style:none;padding:0;margin:8px 0;">`;
            meta.members.forEach(m=>{ html += `<li style="padding:6px 0;border-bottom:1px solid #f0f0f0;">${m}</li>`; });
            html += `</ul><div style="text-align:right;margin-top:8px;"><button id="close-members" style="padding:8px 12px;border-radius:6px;background:#f3f4f6;border:1px solid #e6e6e6;">Close</button></div></div>`;
            const overlay = document.createElement('div'); overlay.className='plus-menu-overlay'; overlay.style.display='flex'; overlay.innerHTML = `<div class="plus-menu" style="max-width:420px;">${html}</div>`;
            document.body.appendChild(overlay);
            overlay.addEventListener('click', (ev)=>{ if (ev.target === overlay) overlay.remove(); });
            overlay.querySelector('#close-members').addEventListener('click', ()=> overlay.remove());
        }

        function showGroupSettingsModal(groupId, groupName) {
            // modal with rename, add member, remove member
            const html = `
                <div style="padding:12px;">
                    <h3>Group settings — ${groupName}</h3>
                    <label style="display:block;margin-top:8px;font-weight:600">Rename</label>
                    <input id="gs-rename" style="width:100%;padding:8px;margin-top:6px;border:1px solid #e6e6e6;border-radius:6px;" value="${groupName}">
                    <button id="gs-rename-btn" style="margin-top:8px;padding:8px 10px;background:#0A7AFF;color:#fff;border:none;border-radius:6px;">Rename</button>

                    <label style="display:block;margin-top:12px;font-weight:600">Add member (email or id)</label>
                    <input id="gs-add" style="width:100%;padding:8px;margin-top:6px;border:1px solid #e6e6e6;border-radius:6px;">
                    <button id="gs-add-btn" style="margin-top:8px;padding:8px 10px;background:#10B981;color:#fff;border:none;border-radius:6px;">Add</button>

                    <label style="display:block;margin-top:12px;font-weight:600">Remove member (email or id)</label>
                    <input id="gs-remove" style="width:100%;padding:8px;margin-top:6px;border:1px solid #e6e6e6;border-radius:6px;">
                    <button id="gs-remove-btn" style="margin-top:8px;padding:8px 10px;background:#EF4444;color:#fff;border:none;border-radius:6px;">Remove</button>

                    <div style="text-align:right;margin-top:12px;"><button id="gs-close" style="padding:8px 12px;border-radius:6px;background:#f3f4f6;border:1px solid #e6e6e6;">Close</button></div>
                </div>`;
            const overlay = document.createElement('div'); overlay.className='plus-menu-overlay'; overlay.style.display='flex'; overlay.innerHTML = `<div class="plus-menu" style="max-width:520px;">${html}</div>`;
            document.body.appendChild(overlay);
            overlay.addEventListener('click', (ev)=>{ if (ev.target === overlay) overlay.remove(); });

            overlay.querySelector('#gs-close').addEventListener('click', ()=> overlay.remove());
            overlay.querySelector('#gs-rename-btn').addEventListener('click', async ()=>{
                const val = overlay.querySelector('#gs-rename').value.trim();
                if (!val) return showToast('Enter a name');
                try {
                    const res = await fetch('/chat/group/update/', { method: 'POST', credentials:'same-origin', headers: {'Content-Type':'application/json','X-CSRFToken':getCookie('csrftoken')}, body: JSON.stringify({ group_id: groupId, action: 'rename', value: val }) });
                    if (!res.ok) throw new Error('failed');
                    showToast('Renamed'); overlay.remove(); loadGroups();
                } catch(e){ showToast('Rename failed'); }
            });

            overlay.querySelector('#gs-add-btn').addEventListener('click', async ()=>{
                const val = overlay.querySelector('#gs-add').value.trim(); if (!val) return showToast('Enter member');
                try { const res = await fetch('/chat/group/update/', { method: 'POST', credentials:'same-origin', headers: {'Content-Type':'application/json','X-CSRFToken':getCookie('csrftoken')}, body: JSON.stringify({ group_id: groupId, action: 'add_member', value: val }) }); if (!res.ok) throw new Error('failed'); showToast('Member added'); overlay.remove(); loadGroups(); } catch(e){ showToast('Add failed'); }
            });

            overlay.querySelector('#gs-remove-btn').addEventListener('click', async ()=>{
                const val = overlay.querySelector('#gs-remove').value.trim(); if (!val) return showToast('Enter member');
                try { const res = await fetch('/chat/group/update/', { method: 'POST', credentials:'same-origin', headers: {'Content-Type':'application/json','X-CSRFToken':getCookie('csrftoken')}, body: JSON.stringify({ group_id: groupId, action: 'remove_member', value: val }) }); if (!res.ok) throw new Error('failed'); showToast('Member removed'); overlay.remove(); loadGroups(); } catch(e){ showToast('Remove failed'); }
            });
        }

        // Message send handler (supports DM and group modes)
        let currentMode = 'dm'; // 'dm' or 'group'
        let selectedGroup = null;

        async function sendMessage() {
            const input = document.getElementById('message-input');
            const text = input ? input.value.trim() : '';

            if (!text) {
                console.warn('sendMessage: message empty');
                if (typeof showToast === 'function') showToast('Enter a message before sending');
                return;
            }

            const sendBtn = document.getElementById('send-btn');
            if (sendBtn) sendBtn.style.opacity = '0.5';

            try {
                if (currentMode === 'group') {
                    if (!selectedGroup) {
                        if (typeof showToast === 'function') showToast('Select a group first');
                        return;
                    }
                        // generate a client id for optimistic UI
                        const cid = 'cid-' + Date.now() + '-' + Math.random().toString(36).slice(2,9);
                        // Prefer websocket for real-time group send
                        if (ws && ws.readyState === WebSocket.OPEN) {
                            ws.send(JSON.stringify({ type: 'group_message', group_id: selectedGroup, text: text, cid }));
                        } else {
                        // fallback to HTTP
                        const res = await fetch('/chat/group/send/', {
                            method: 'POST',
                            credentials: 'same-origin',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRFToken': getCookie('csrftoken'),
                            },
                            body: JSON.stringify({ group_id: selectedGroup, text }),
                        });
                        if (!res.ok) {
                            const err = await res.text().catch(()=>res.statusText||'error');
                            console.error('group send failed', err);
                            if (typeof showToast === 'function') showToast('Send failed');
                            return;
                        }
                    }
                        // optimistic append with cid so server echo can match
                        appendMessage({ sender: CURRENT_USER, text, created_at: new Date().toISOString(), cid });
                    if (input) input.value = '';
                    
                    // Silently refresh chat content without visible page reload
                    setTimeout(() => {
                        if (currentMode === 'group' && selectedGroup) {
                            loadGroupHistory();
                        }
                    }, 300);
                    return;
                }

                // DM mode (existing behavior)
                if (!selectedPeer) {
                    console.warn('sendMessage: no peer selected');
                    if (typeof showToast === 'function') showToast('Select a member to message first');
                    return;
                }

                // DM mode (existing behavior)
                // generate cid for optimistic UI
                const cid = 'cid-' + Date.now() + '-' + Math.random().toString(36).slice(2,9);
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({ type: 'message', tenant: TENANT_ID, to: selectedPeer, message: text, cid }));
                } else {
                    const res = await fetch('/chat/send/', {
                        method: 'POST',
                        credentials: 'same-origin',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': getCookie('csrftoken'),
                        },
                        body: JSON.stringify({ to: selectedPeer, text }),
                    });
                    if (!res.ok) {
                        const errText = await res.text().catch(()=>res.statusText || 'error');
                        console.error('sendMessage HTTP error', res.status, errText);
                        if (typeof showToast === 'function') showToast('Send failed: ' + (res.status || 'error'));
                        return;
                    }
                }
                
                // optimistic append with cid so server echo can match
                appendMessage({ sender: CURRENT_USER, text, created_at: new Date().toISOString(), cid });
                if (input) input.value = '';
                
                // Silently refresh chat content without visible page reload
                setTimeout(() => {
                    if (currentMode === 'dm' && selectedPeer) {
                        loadHistory();
                    }
                }, 300);
            } catch (e) {
                console.error('sendMessage error', e);
                if (typeof showToast === 'function') showToast('Error sending message');
            } finally {
                if (sendBtn) sendBtn.style.opacity = '1';
            }
        }

        // Unread counts
        async function refreshUnreadCounts() {
            try {
                const resp = await fetch('/chat/unread/');
                if (!resp.ok) return;
                const data = await resp.json();
                let total = 0;
                if (data && data.unread) {
                    for (const item of data.unread) {
                        total += item.count;
                    }
                }
                const badge = document.getElementById('unread-badge');
                if (badge) {
                    if (total > 0) {
                        badge.textContent = total;
                        badge.style.display = '';
                    } else {
                        badge.style.display = 'none';
                    }
                }
            } catch (e) {
                // Optionally log error
            }
        }

        // Mark read
        async function markRead(peer) {
            try {
                console.log('📖 Marking messages as read for peer:', peer);
                const resp = await fetch('/chat/mark_read/', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCookie('csrftoken'),
                    },
                    body: JSON.stringify({ peer: normId(peer) })
                });
                const data = await resp.json();
                console.log('✅ markRead response:', data, '- This will trigger blue checkmarks on sender side');
            } catch (e) {
                console.error('❌ markRead error', e);
            }
        }

        // Event listeners
        document.getElementById('send-btn').addEventListener('click', sendMessage);
        document.getElementById('message-input').addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        // Typing indicator (client-side): show a subtle "typing" line while user types
        const inputEl = document.getElementById('message-input');
        if (inputEl) {
            let localTypingTimeout = null;
            let isTyping = false;
            
            inputEl.addEventListener('input', (e) => {
                const feed = document.getElementById('messages-feed');
                const inputValue = (e.target.value || '').trim();
                
                // Send typing indicator to server
                if (inputValue && selectedPeer && !isTyping) {
                    sendTypingIndicator('typing');
                    isTyping = true;
                }
                
                // Clear previous timeout
                if (localTypingTimeout) clearTimeout(localTypingTimeout);
                
                // Set timeout to send 'idle' status
                localTypingTimeout = setTimeout(() => {
                    if (isTyping) {
                        sendTypingIndicator('idle');
                        isTyping = false;
                    }
                }, 1000);
            });
        }

        // Enhanced Emoji picker with categories, search, and multiple options
        const emojiBtn = document.getElementById('emoji-btn');
        const emojiPicker = document.getElementById('emoji-picker');
        const emojiContent = document.getElementById('emoji-content');
        const emojiClose = document.getElementById('emoji-close');
        const emojiSearch = document.getElementById('emoji-search');
        const emojiTabs = document.getElementById('emoji-tabs');
        const addEmojiBtn = document.getElementById('add-emoji-btn');
        const uploadEmojiBtn = document.getElementById('upload-emoji-btn');
        const skinToneSelector = document.getElementById('skin-tone-selector');

        // Categorized emoji data
        const EMOJI_DATA = {
            frequent: {
                title: 'Frequently Used',
                emojis: ['✅','👀','👍','🙏','😊','🤣','🙂','😍','🤩','😭','🔥','✨','🎉','💯','❤️','😎','🤔','😅','😂','😉','🫶','👏','😇','😢']
            },
            people: {
                title: 'Smileys & People',
                emojis: ['😀','😃','😄','😁','😆','😅','😂','🤣','🙂','🙃','😉','😊','😇','🥰','😍','🤩','😘','😗','😚','😙','😋','😛','😜','🤪','😝','🤑','🤗','🤭','🤫','🤔','🤐','🤨','😐','😑','😶','😏','😒','🙄','😬','🤥','😌','😔','😪','🤤','😴','😷','🤒','🤕','🤢','🤮','🤧','🥵','🥶','😵','🤯','🤠','🥳','😎','🤓','🧐','😕','😟','🙁','☹️','😮','😯','😲','😳','🥺','😦','😧','😨','😰','😥','😢','😭','😱','😖','😣','😞','😓','😩','😫','🥱','😤','😡','😠','🤬','👿','💀','☠️','💩','🤡','👹','👺','👻','👽','👾','🤖','😺','😸','😹','😻','😼','😽','🙀','😿','😾','🙈','🙉','🙊','💋','💌','💘','💝','💖','💗','💓','💞','💕','💟','❣️','💔','❤️','🧡','💛','💚','💙','💜','🤎','🖤','🤍','👋','🤚','🖐️','✋','🖖','👌','🤏','✌️','🤞','🤟','🤘','🤙','👈','👉','👆','🖕','👇','☝️','👍','👎','✊','👊','🤛','🤜','👏','🙌','👐','🤲','🤝','🙏']
            },
            nature: {
                title: 'Animals & Nature',
                emojis: ['🐶','🐱','🐭','🐹','🐰','🦊','🐻','🐼','🐨','🐯','🦁','🐮','🐷','🐽','🐸','🐵','🙈','🙉','🙊','🐒','🐔','🐧','🐦','🐤','🐣','🐥','🦆','🦅','🦉','🦇','🐺','🐗','🐴','🦄','🐝','🐛','🦋','🐌','🐞','🐜','🦟','🦗','🕷️','🕸️','🦂','🐢','🐍','🦎','🦖','🦕','🐙','🦑','🦐','🦞','🦀','🐡','🐠','🐟','🐬','🐳','🐋','🦈','🐊','🐅','🐆','🦓','🦍','🦧','🐘','🦛','🦏','🐪','🐫','🦒','🦘','🐃','🐂','🐄','🐎','🐖','🐏','🐑','🦙','🐐','🦌','🐕','🐩','🦮','🐕‍🦺','🐈','🐓','🦃','🦚','🦜','🦢','🦩','🕊️','🐇','🦝','🦨','🦡','🦦','🦥','🐁','🐀','🐿️','🦔','🌲','🌳','🌴','🌱','🌿','☘️','🍀','🎍','🎋','🍃','🍂','🍁','🍄','🐚','🌾','💐','🌷','🌹','🥀','🌺','🌸','🌼','🌻','🌞','🌝','🌛','🌜','🌚','🌕','🌖','🌗','🌘','🌑','🌒','🌓','🌔','🌙','🌎','🌍','🌏','💫','⭐','🌟','✨','⚡','☄️','💥','🔥','🌪️','🌈','☀️','🌤️','⛅','🌥️','☁️','🌦️','🌧️','⛈️','🌩️','🌨️','❄️','☃️','⛄','🌬️','💨','💧','💦','☔','☂️']
            },
            food: {
                title: 'Food & Drink',
                emojis: ['🍇','🍈','🍉','🍊','🍋','🍌','🍍','🥭','🍎','🍏','🍐','🍑','🍒','🍓','🥝','🍅','🥥','🥑','🍆','🥔','🥕','🌽','🌶️','🥒','🥬','🥦','🧄','🧅','🍄','🥜','🌰','🍞','🥐','🥖','🥨','🥯','🥞','🧇','🧀','🍖','🍗','🥩','🥓','🍔','🍟','🍕','🌭','🥪','🌮','🌯','🥙','🧆','🥚','🍳','🥘','🍲','🥣','🥗','🍿','🧈','🧂','🥫','🍱','🍘','🍙','🍚','🍛','🍜','🍝','🍠','🍢','🍣','🍤','🍥','🥮','🍡','🥟','🥠','🥡','🦀','🦞','🦐','🦑','🦪','🍦','🍧','🍨','🍩','🍪','🎂','🍰','🧁','🥧','🍫','🍬','🍭','🍮','🍯','🍼','🥛','☕','🍵','🍶','🍾','🍷','🍸','🍹','🍺','🍻','🥂','🥃','🥤','🧃','🧉','🧊']
            },
            activity: {
                title: 'Activities',
                emojis: ['⚽','🏀','🏈','⚾','🥎','🎾','🏐','🏉','🥏','🎱','🪀','🏓','🏸','🏒','🏑','🥍','🏏','🥅','⛳','🪁','🏹','🎣','🤿','🥊','🥋','🎽','🛹','🛼','🛷','⛸️','🥌','🎿','⛷️','🏂','🪂','🏋️','🤼','🤸','🤺','⛹️','🤾','🏌️','🏇','🧘','🏊','🤽','🚣','🧗','🚴','🚵','🎖️','🏆','🏅','🥇','🥈','🥉','🎗️','🎫','🎟️','🎪','🤹','🎭','🎨','🎬','🎤','🎧','🎼','🎹','🥁','🎷','🎺','🎸','🪕','🎻','🎲','♟️','🎯','🎳','🎮','🎰','🧩']
            },
            travel: {
                title: 'Travel & Places',
                emojis: ['🚗','🚕','🚙','🚌','🚎','🏎️','🚓','🚑','🚒','🚐','🚚','🚛','🚜','🦯','🦽','🦼','🛴','🚲','🛵','🏍️','🛺','🚨','🚔','🚍','🚘','🚖','🚡','🚠','🚟','🚃','🚋','🚞','🚝','🚄','🚅','🚈','🚂','🚆','🚇','🚊','🚉','✈️','🛫','🛬','🛩️','💺','🛰️','🚀','🛸','🚁','🛶','⛵','🚤','🛥️','🛳️','⛴️','🚢','⚓','⛽','🚧','🚦','🚥','🚏','🗺️','🗿','🗽','🗼','🏰','🏯','🏟️','🎡','🎢','🎠','⛲','⛱️','🏖️','🏝️','🏜️','🌋','⛰️','🏔️','🗻','🏕️','⛺','🏠','🏡','🏘️','🏚️','🏗️','🏭','🏢','🏬','🏣','🏤','🏥','🏦','🏨','🏪','🏫','🏩','💒','🏛️','⛪','🕌','🕍','🛕','🕋','⛩️','🛤️','🛣️','🗾','🎑','🏞️','🌅','🌄','🌠','🎇','🎆','🌇','🌆','🏙️','🌃','🌌','🌉','🌁']
            },
            objects: {
                title: 'Objects',
                emojis: ['⌚','📱','📲','💻','⌨️','🖥️','🖨️','🖱️','🖲️','🕹️','🗜️','💾','💿','📀','📼','📷','📸','📹','🎥','📽️','🎞️','📞','☎️','📟','📠','📺','📻','🎙️','🎚️','🎛️','🧭','⏱️','⏲️','⏰','🕰️','⌛','⏳','📡','🔋','🔌','💡','🔦','🕯️','🪔','🧯','🛢️','💸','💵','💴','💶','💷','💰','💳','💎','⚖️','🧰','🔧','🔨','⚒️','🛠️','⛏️','🔩','⚙️','🧱','⛓️','🧲','🔫','💣','🧨','🪓','🔪','🗡️','⚔️','🛡️','🚬','⚰️','⚱️','🏺','🔮','📿','🧿','💈','⚗️','🔭','🔬','🕳️','🩹','🩺','💊','💉','🩸','🧬','🦠','🧫','🧪','🌡️','🧹','🧺','🧻','🚽','🚰','🚿','🛁','🛀','🧼','🪒','🧽','🧴','🛎️','🔑','🗝️','🚪','🪑','🛋️','🛏️','🛌','🧸','🖼️','🛍️','🛒','🎁','🎈','🎏','🎀','🎊','🎉','🎎','🏮','🎐','🧧','✉️','📩','📨','📧','💌','📥','📤','📦','🏷️','📪','📫','📬','📭','📮','📯','📜','📃','📄','📑','🧾','📊','📈','📉','🗒️','🗓️','📆','📅','🗑️','📇','🗃️','🗳️','🗄️','📋','📁','📂','🗂️','🗞️','📰','📓','📔','📒','📕','📗','📘','📙','📚','📖','🔖','🧷','🔗','📎','🖇️','📐','📏','🧮','📌','📍','✂️','🖊️','🖋️','✒️','🖌️','🖍️','📝','✏️','🔍','🔎','🔏','🔐','🔒','🔓']
            },
            symbols: {
                title: 'Symbols',
                emojis: ['❤️','🧡','💛','💚','💙','💜','🖤','🤍','🤎','💔','❣️','💕','💞','💓','💗','💖','💘','💝','💟','☮️','✝️','☪️','🕉️','☸️','✡️','🔯','🕎','☯️','☦️','🛐','⛎','♈','♉','♊','♋','♌','♍','♎','♏','♐','♑','♒','♓','🆔','⚛️','🉑','☢️','☣️','📴','📳','🈶','🈚','🈸','🈺','🈷️','✴️','🆚','💮','🉐','㊙️','㊗️','🈴','🈵','🈹','🈲','🅰️','🅱️','🆎','🆑','🅾️','🆘','❌','⭕','🛑','⛔','📛','🚫','💯','💢','♨️','🚷','🚯','🚳','🚱','🔞','📵','🚭','❗','❕','❓','❔','‼️','⁉️','🔅','🔆','〽️','⚠️','🚸','🔱','⚜️','🔰','♻️','✅','🈯','💹','❇️','✳️','❎','🌐','💠','Ⓜ️','🌀','💤','🏧','🚾','♿','🅿️','🈳','🈂️','🛂','🛃','🛄','🛅','🚹','🚺','🚼','🚻','🚮','🎦','📶','🈁','🔣','ℹ️','🔤','🔡','🔠','🆖','🆗','🆙','🆒','🆕','🆓','0️⃣','1️⃣','2️⃣','3️⃣','4️⃣','5️⃣','6️⃣','7️⃣','8️⃣','9️⃣','🔟','🔢','#️⃣','*️⃣','⏏️','▶️','⏸️','⏯️','⏹️','⏺️','⏭️','⏮️','⏩','⏪','⏫','⏬','◀️','🔼','🔽','➡️','⬅️','⬆️','⬇️','↗️','↘️','↙️','↖️','↕️','↔️','↪️','↩️','⤴️','⤵️','🔀','🔁','🔂','🔄','🔃','🎵','🎶','➕','➖','➗','✖️','♾️','💲','💱','™️','©️','®️','〰️','➰','➿','🔚','🔙','🔛','🔝','🔜','✔️','☑️','🔘','🔴','🟠','🟡','🟢','🔵','🟣','⚫','⚪','🟤','🔺','🔻','🔸','🔹','🔶','🔷','🔳','🔲','▪️','▫️','◾','◽','◼️','◻️','🟥','🟧','🟨','🟩','🟦','🟪','⬛','⬜','🟫','🔈','🔇','🔉','🔊','🔔','🔕','📣','📢','💬','💭','🗯️','♠️','♣️','♥️','♦️','🃏','🎴','🀄','🕐','🕑','🕒','🕓','🕔','🕕','🕖','🕗','🕘','🕙','🕚','🕛','🕜','🕝','🕞','🕟','🕠','🕡','🕢','🕣','🕤','🕥','🕦','🕧']
            }
        };

        // Track frequently used emojis in localStorage
        let frequentEmojis = [];
        try {
            const stored = localStorage.getItem('frequentEmojis');
            if (stored) frequentEmojis = JSON.parse(stored);
        } catch(e) { console.log('localStorage not available'); }

        let currentCategory = 'frequent';

        function addToFrequent(emoji) {
            const maxFrequent = 24;
            frequentEmojis = frequentEmojis.filter(e => e !== emoji);
            frequentEmojis.unshift(emoji);
            if (frequentEmojis.length > maxFrequent) {
                frequentEmojis = frequentEmojis.slice(0, maxFrequent);
            }
            try {
                localStorage.setItem('frequentEmojis', JSON.stringify(frequentEmojis));
            } catch(e) {}
        }

        function populateEmojiContent(category = 'frequent'){
            if (!emojiContent) return;
            emojiContent.innerHTML = '';
            
            if (category === 'frequent') {
                if (frequentEmojis.length === 0) {
                    emojiContent.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-muted);">No frequently used emojis yet</div>';
                    return;
                }
                const catDiv = document.createElement('div');
                catDiv.className = 'emoji-category';
                const titleDiv = document.createElement('div');
                titleDiv.className = 'emoji-category-title';
                titleDiv.textContent = 'Frequently Used';
                catDiv.appendChild(titleDiv);
                
                const grid = document.createElement('div');
                grid.className = 'emoji-grid';
                frequentEmojis.forEach(emoji => {
                    const cell = createEmojiCell(emoji);
                    grid.appendChild(cell);
                });
                catDiv.appendChild(grid);
                emojiContent.appendChild(catDiv);
            } else {
                const catData = EMOJI_DATA[category];
                if (catData) {
                    const catDiv = document.createElement('div');
                    catDiv.className = 'emoji-category';
                    const titleDiv = document.createElement('div');
                    titleDiv.className = 'emoji-category-title';
                    titleDiv.textContent = catData.title;
                    catDiv.appendChild(titleDiv);
                    
                    const grid = document.createElement('div');
                    grid.className = 'emoji-grid';
                    catData.emojis.forEach(emoji => {
                        const cell = createEmojiCell(emoji);
                        grid.appendChild(cell);
                    });
                    catDiv.appendChild(grid);
                    emojiContent.appendChild(catDiv);
                }
            }
        }

        function createEmojiCell(emoji) {
            const cell = document.createElement('button');
            cell.type = 'button';
            cell.className = 'emoji-cell';
            cell.textContent = emoji;
            cell.setAttribute('aria-label', 'Emoji ' + emoji);
            cell.addEventListener('click', () => {
                insertAtCursor(document.getElementById('message-input'), emoji);
                addToFrequent(emoji);
                document.getElementById('message-input').focus();
            });
            return cell;
        }

        function searchEmojis(query) {
            if (!query.trim()) {
                populateEmojiContent(currentCategory);
                return;
            }
            emojiContent.innerHTML = '';
            const searchDiv = document.createElement('div');
            searchDiv.className = 'emoji-category';
            const titleDiv = document.createElement('div');
            titleDiv.className = 'emoji-category-title';
            titleDiv.textContent = 'Search Results';
            searchDiv.appendChild(titleDiv);
            
            const grid = document.createElement('div');
            grid.className = 'emoji-grid';
            
            let found = 0;
            Object.keys(EMOJI_DATA).forEach(catKey => {
                if (catKey === 'frequent') return;
                EMOJI_DATA[catKey].emojis.forEach(emoji => {
                    if (found < 64) { // Limit results
                        const cell = createEmojiCell(emoji);
                        grid.appendChild(cell);
                        found++;
                    }
                });
            });
            
            searchDiv.appendChild(grid);
            emojiContent.appendChild(searchDiv);
            
            if (found === 0) {
                emojiContent.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-muted);">No emojis found</div>';
            }
        }

        function insertAtCursor(input, text) {
            if (!input) return;
            input.focus();
            try {
                const start = input.selectionStart || 0;
                const end = input.selectionEnd || 0;
                const val = input.value || '';
                input.value = val.substring(0, start) + text + val.substring(end);
                const pos = start + text.length;
                input.setSelectionRange(pos, pos);
            } catch (e) {
                input.value = (input.value || '') + text;
            }
        }

        // Enhanced emoji picker with tabs, search, and actions
        if (emojiBtn && emojiPicker) {
            emojiBtn.addEventListener('click', (ev) => {
                ev.preventDefault();
                const isOpen = emojiPicker.style.display === 'block';
                if (!isOpen) {
                    currentCategory = 'frequent';
                    populateEmojiContent('frequent');
                    emojiPicker.style.display = 'block';
                    emojiPicker.setAttribute('aria-hidden','false');
                    // Update active tab
                    document.querySelectorAll('.emoji-tab').forEach(t => t.classList.remove('active'));
                    document.querySelector('.emoji-tab[data-category="frequent"]').classList.add('active');
                } else {
                    emojiPicker.style.display = 'none';
                    emojiPicker.setAttribute('aria-hidden','true');
                }
            });
            
            emojiClose.addEventListener('click', ()=>{ 
                emojiPicker.style.display='none'; 
                emojiPicker.setAttribute('aria-hidden','true'); 
                emojiBtn.focus(); 
            });

            // Tab switching
            emojiTabs.querySelectorAll('.emoji-tab').forEach(tab => {
                tab.addEventListener('click', () => {
                    const category = tab.dataset.category;
                    currentCategory = category;
                    document.querySelectorAll('.emoji-tab').forEach(t => t.classList.remove('active'));
                    tab.classList.add('active');
                    emojiSearch.value = '';
                    populateEmojiContent(category);
                });
            });

            // Search functionality
            if (emojiSearch) {
                let searchTimeout;
                emojiSearch.addEventListener('input', (e) => {
                    clearTimeout(searchTimeout);
                    searchTimeout = setTimeout(() => {
                        searchEmojis(e.target.value);
                    }, 300);
                });
            }

            // Add Emoji button (custom emoji dialog)
            if (addEmojiBtn) {
                addEmojiBtn.addEventListener('click', () => {
                    const emojiName = prompt('Enter a name for your custom emoji:');
                    if (emojiName) {
                        showToast('Custom emoji "' + emojiName + '" would be added here');
                    }
                });
            }

            // Upload image button
            if (uploadEmojiBtn) {
                uploadEmojiBtn.addEventListener('click', () => {
                    const fileInput = document.createElement('input');
                    fileInput.type = 'file';
                    fileInput.accept = 'image/*';
                    fileInput.addEventListener('change', () => {
                        if (fileInput.files[0]) {
                            showToast('Image selected: ' + fileInput.files[0].name);
                            // Here you would upload the image and add it as custom emoji
                        }
                    });
                    fileInput.click();
                });
            }

            // Skin tone selector
            if (skinToneSelector) {
                skinToneSelector.addEventListener('click', () => {
                    const tones = ['👋', '👋🏻', '👋🏼', '👋🏽', '👋🏾', '👋🏿'];
                    const selected = prompt('Select skin tone:\n0: Default\n1: Light\n2: Medium-Light\n3: Medium\n4: Medium-Dark\n5: Dark', '0');
                    if (selected !== null) {
                        showToast('Skin tone preference saved');
                    }
                });
            }

            // close when clicking outside picker
            document.addEventListener('click', (ev) => {
                if (!emojiPicker) return;
                if (emojiPicker.style.display === 'none' || emojiPicker.style.display === '') return;
                const path = ev.composedPath ? ev.composedPath() : (ev.path || []);
                if (!path.includes(emojiPicker) && !path.includes(emojiBtn)) {
                    emojiPicker.style.display = 'none';
                    emojiPicker.setAttribute('aria-hidden','true');
                }
            });

            // close on Esc key
            document.addEventListener('keydown', (ev) => {
                if (ev.key === 'Escape') {
                    if (emojiPicker && emojiPicker.style.display === 'block') {
                        emojiPicker.style.display='none'; emojiPicker.setAttribute('aria-hidden','true');
                        emojiBtn.focus();
                        markRead(selectedPeer);
                    }
                }
            });
        }

        // Plus menu: attach, invite, create canvas/task (client-side handlers)
        const plusBtn = document.querySelector('.plus-btn');
        const plusOverlay = document.getElementById('plus-menu-overlay');
        const plusClose = document.getElementById('plus-close');
        if (plusBtn && plusOverlay) {
            plusBtn.addEventListener('click', (e) => {
                e.preventDefault();
                plusOverlay.style.display = 'flex';
                plusOverlay.setAttribute('aria-hidden','false');
                // focus trap not required for simple menu
            });
            plusClose.addEventListener('click', ()=>{ plusOverlay.style.display='none'; plusOverlay.setAttribute('aria-hidden','true'); });
            plusOverlay.addEventListener('click', (ev)=>{ if (ev.target === plusOverlay) { plusOverlay.style.display='none'; plusOverlay.setAttribute('aria-hidden','true'); } });

            plusOverlay.querySelectorAll('.plus-item').forEach(it=>{
                it.addEventListener('click', async (ev)=>{
                    const action = it.dataset.action;
                    plusOverlay.style.display='none'; plusOverlay.setAttribute('aria-hidden','true');
                    if (action === 'attach') {
                        // open file picker
                        const fileInput = document.createElement('input'); fileInput.type='file'; fileInput.multiple=false;
                        fileInput.addEventListener('change', ()=>{ showToast('File selected (preview): ' + (fileInput.files[0] ? fileInput.files[0].name : '')); });
                        fileInput.click();
                    } else if (action === 'invite') {
                        const email = prompt('Enter email to invite to team chat:');
                        if (email) showToast('Invite request queued for ' + email);
                    } else if (action === 'create-canvas') {
                        showToast('Create canvas — feature placeholder');
                    } else if (action === 'create-task') {
                        showToast('Create task — feature placeholder');
                    }
                });
            });
        }

        // temporary toast helper
        function showToast(msg, timeout=2400){
            let t = document.getElementById('global-toast');
            if (!t){ t = document.createElement('div'); t.id='global-toast'; t.style.position='fixed'; t.style.right='20px'; t.style.bottom='24px'; t.style.background='rgba(17,17,17,0.9)'; t.style.color='#fff'; t.style.padding='10px 14px'; t.style.borderRadius='8px'; t.style.boxShadow='0 6px 20px rgba(0,0,0,0.2)'; t.style.zIndex=1700; document.body.appendChild(t); }
            t.textContent = msg; t.style.opacity = '1';
            clearTimeout(t._hide);
            t._hide = setTimeout(()=>{ t.style.opacity='0'; }, timeout);
        }

        // Show unread messages view (WhatsApp-style)
        async function showUnreadMessages() {
            console.log('📬 Loading unread messages...');
            currentMode = 'unread';
            selectedPeer = null;
            selectedGroup = null;
            
            // Clear active selection from sidebar
            document.querySelectorAll('.dm-item').forEach(el => el.classList.remove('active'));
            
            const headerTitle = document.getElementById('chat-header-title');
            headerTitle.innerHTML = '<i class="fas fa-envelope-open-text" style="margin-right:8px;opacity:0.6;"></i> Unread Messages';
            
            const feed = document.getElementById('messages-feed');
            feed.innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Loading unread conversations...</div>';
            
            // Hide input container
            document.getElementById('input-container').style.display = 'none';
            
            try {
                const resp = await fetch('/chat/unread/');
                if (!resp.ok) throw new Error('Failed to fetch unread');
                const data = await resp.json();
                
                if (!data.unread || data.unread.length === 0) {
                    feed.innerHTML = `
                        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:var(--text-muted);padding:40px;">
                            <i class="fas fa-inbox" style="font-size:64px;margin-bottom:20px;opacity:0.3;"></i>
                            <h3 style="margin:0 0 8px 0;font-size:20px;font-weight:600;">No unread messages</h3>
                            <p style="margin:0;font-size:14px;">All caught up! 🎉</p>
                        </div>
                    `;
                    return;
                }
                
                // Build unread conversations list (WhatsApp-style)
                let html = '<div style="padding:20px;">';
                html += '<div style="margin-bottom:20px;"><h2 style="margin:0 0 8px 0;font-size:18px;font-weight:600;">Unread Conversations</h2><p style="margin:0;color:var(--text-muted);font-size:14px;">Click on a conversation to view messages</p></div>';
                
                for (const item of data.unread) {
                    const senderEmail = (item.from || '').toLowerCase();
                    const count = item.count || 0;
                    
                    // Find member info
                    const member = members.find(m => (m.email || '').toLowerCase() === senderEmail);
                    const memberName = member ? formatDisplayName((member.name || '').replace(/<[^>]+>/g, '').trim() || senderEmail) : senderEmail;
                    const memberId = member ? member.id : senderEmail;
                    const initials = getInitials(memberName.split('<')[0].trim());
                    
                    // Check if user is online
                    const isOnline = member ? false : false; // Will be updated by presence
                    
                    html += `
                        <div class="unread-conversation-item" data-peer-id="${memberId}" data-peer-name="${memberName}" data-peer-email="${senderEmail}" style="display:flex;align-items:center;padding:16px;margin-bottom:8px;background:var(--chat-bg);border:1px solid var(--border-light);border-radius:12px;cursor:pointer;transition:all 0.2s ease;">
                            <div style="position:relative;margin-right:16px;">
                                <span class="user-pic-sm" data-user-email="${senderEmail}" style="width:48px;height:48px;font-size:16px;">
                                    ${initials}
                                    <span class="presence-indicator ${isOnline ? 'online' : ''}"></span>
                                </span>
                            </div>
                            <div style="flex:1;min-width:0;">
                                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">
                                    <h3 style="margin:0;font-size:16px;font-weight:600;color:var(--text-primary);">${memberName.split('<')[0].trim()}</h3>
                                    <span style="display:flex;align-items:center;justify-content:center;width:24px;height:24px;background:var(--accent-pink);color:#fff;font-size:12px;font-weight:700;border-radius:12px;">${count}</span>
                                </div>
                                <p style="margin:0;font-size:14px;color:var(--text-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${count} unread message${count > 1 ? 's' : ''}</p>
                            </div>
                        </div>
                    `;
                }
                
                html += '</div>';
                feed.innerHTML = html;
                
                // Add click handlers to conversation items
                document.querySelectorAll('.unread-conversation-item').forEach(item => {
                    item.addEventListener('click', () => {
                        const peerId = item.dataset.peerId;
                        const peerName = item.dataset.peerName;
                        const peerEmail = item.dataset.peerEmail;
                        console.log('🔔 Opening conversation with:', peerName, peerId);
                        selectPeer(peerId, peerName, peerEmail);
                    });
                    
                    // Hover effect
                    item.addEventListener('mouseenter', () => {
                        item.style.background = 'var(--hover-bg)';
                        item.style.transform = 'translateX(4px)';
                        item.style.boxShadow = 'var(--shadow-md)';
                    });
                    item.addEventListener('mouseleave', () => {
                        item.style.background = 'var(--chat-bg)';
                        item.style.transform = 'translateX(0)';
                        item.style.boxShadow = 'none';
                    });
                });
                
            } catch (e) {
                console.error('❌ Error loading unread messages:', e);
                feed.innerHTML = '<div style="padding:40px;text-align:center;color:#ff6b6b;">Error loading unread messages. Please try again.</div>';
            }
        }

        // Add click handler for unread messages nav item
        document.getElementById('nav-unread').addEventListener('click', () => {
            showUnreadMessages();
        });

        // Init
        loadMembers();
        loadGroups();
        refreshUnreadCounts();
        setInterval(refreshUnreadCounts, 6000);