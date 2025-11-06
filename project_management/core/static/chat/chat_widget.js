(function () {
  const openBtn = document.getElementById('chat-open-btn');
  const panel = document.getElementById('chat-panel');
  const closeBtn = document.getElementById('chat-close-btn');
  const membersList = document.getElementById('chat-members-list');
  const search = document.getElementById('chat-member-search');
  const chatWindow = document.getElementById('chat-window');
  const historyEl = document.getElementById('chat-history');
  const input = document.getElementById('chat-input');
  const sendBtn = document.getElementById('chat-send');

  let selectedPeer = null;
  let selectedPeerName = '';
  let ws = null;
  let pollInterval = null;
  let unreadPollHandle = null;

  function showPanel() {
    panel.classList.remove('hidden');
    startUnreadPolling();
  }
  function hidePanel() {
    panel.classList.add('hidden');
    stopUnreadPolling();
  }

  openBtn.addEventListener('click', () => {
    showPanel();
    loadMembers();
  });
  closeBtn.addEventListener('click', hidePanel);

  // Helper to include credentials for same-origin requests
  const fetchOptions = (method = 'GET', body = null) => {
    const opts = {
      method,
      credentials: 'same-origin', // important: send cookies/session to Django
      headers: {}
    };
    if (body !== null) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    return opts;
  };

  async function loadMembers() {
  membersList.innerHTML = '<li style="text-align:center;padding:8px;color:#999;">Loading...</li>';
  try {
    const res = await fetch('/chat/members/', { credentials: 'same-origin' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    membersList.innerHTML = '';

    // inside loadMembers(), when iterating over data.members:
    data.members.forEach((m) => {
      // normalize id to trimmed string, and fallback to CURRENT_USER if empty
      const rawId = (m.id || '').toString().trim();
      const memberId = rawId || (m.is_self ? (typeof CURRENT_USER !== 'undefined' ? String(CURRENT_USER).trim() : '') : '');

      const memberName = (m.name || '').toString().trim();

      const li = document.createElement('li');
      li.dataset.id = memberId;
      li.dataset.email = memberId;
      li.dataset.name = memberName;
      if (m.is_self) li.dataset.self = 'true';

      const dot = document.createElement('span');
      dot.className = 'presence-dot offline';
      dot.setAttribute('data-user', memberId);

      if (m.is_self) {
        dot.classList.remove('offline');
        dot.classList.add('online');
      }

      const label = document.createElement('span');
      label.textContent = memberName;
      label.style.verticalAlign = 'middle';
      label.style.marginLeft = '6px';
      label.style.fontSize = '13px';
      label.style.fontWeight = m.is_self ? '600' : '500';

      const badge = document.createElement('span');
      badge.className = 'member-badge';
      badge.style.display = 'none';
      badge.setAttribute('data-unread-for', memberId);

      // Make rows clickable (including self)
      li.addEventListener('click', () => selectPeer({ id: memberId, name: memberName, is_self: !!m.is_self }));

      li.appendChild(dot);
      li.appendChild(label);
      li.appendChild(badge);
      membersList.appendChild(li);
    });


    // initial unread counts
    await refreshUnreadCounts();

  } catch (e) {
    console.error('Failed to load members', e);
    membersList.innerHTML = '<li style="color:red;padding:8px;">Error loading members</li>';
  }
}



  function findMemberLiById(id) {
    return [...membersList.children].find((li) => li.dataset.id === id);
  }

  function selectPeer(m) {
  // normalize and derive a usable id
  const raw = (m.id || '').toString().trim();
  let memberId = raw;

  // If raw empty, try extracting from name <email>
  if (!memberId && m.name) {
    const em = (m.name || '').match(/<([^>]+)>/);
    if (em && em[1]) memberId = em[1].trim();
  }

  // If still empty and this row is flagged self, try CURRENT_USER
  if (!memberId && m.is_self && (typeof CURRENT_USER !== 'undefined') && CURRENT_USER) {
    memberId = String(CURRENT_USER).trim();
  }

  // Final fallback: try dataset of an element flagged as self
  if (!memberId) {
    const selfLi = document.querySelector('#chat-members-list li[data-self="true"]');
    if (selfLi) {
      memberId = (selfLi.dataset.id || selfLi.dataset.email || '').toString().trim();
    }
  }

  // highlight active
  membersList.querySelectorAll('li').forEach((li) => li.classList.remove('active'));
  const li = [...membersList.children].find((x) => ((x.dataset.id || '').toString().trim() === memberId));
  if (li) li.classList.add('active');

  selectedPeer = memberId || '';               // explicit
  selectedPeerName = (m.name || '').toString().trim() || (memberId || '');
  chatWindow.classList.remove('hidden');

  // show loading placeholder (will be replaced by loadHistory)
  historyEl.innerHTML = '<div style="color:#888;text-align:center;margin-top:8px;">Loading messages...</div>';

  // header update
  if (m.is_self) {
    const header = document.querySelector('.chat-header .chat-title');
    header.innerHTML = `Team chat <span class="chat-partner">(notes for ${selectedPeerName})</span>`;
  } else {
    updateHeaderPeer(selectedPeerName);
  }

  console.log('[chat] selectPeer -> selectedPeer=', selectedPeer, 'CURRENT_USER=', (typeof CURRENT_USER !== 'undefined' ? CURRENT_USER : null), 'is_self=', !!m.is_self);

  // init websocket & load history
  initWebSocket();
  loadHistory().then(() => {
    // Mark read only when we have a valid non-empty selectedPeer
    if (selectedPeer) {
      console.log('[chat] calling markRead for', selectedPeer);
      markRead(selectedPeer).catch(err => console.warn('markRead failed in selectPeer', err));
      // hide unread badge for this peer
      const b = document.querySelector(`[data-unread-for="${selectedPeer}"]`);
      if (b) b.style.display = 'none';
    } else {
      console.warn('[chat] selectPeer resolved to empty id, skipping markRead');
      // show a helpful message in UI so it's obvious to the user
      historyEl.innerHTML = '<div style="color:#d9534f;text-align:center;margin-top:10px;">Cannot determine your identifier — please refresh the page.</div>';
    }
  }).catch(err => {
    console.error('loadHistory failed in selectPeer', err);
    if (selectedPeer) markRead(selectedPeer).catch(e => console.warn('markRead after failed loadHistory', e));
  });
}

  function updateHeaderPeer(name) {
    const header = document.querySelector('.chat-header .chat-title');
    header.innerHTML = `Team chat <span class="chat-partner">with ${name}</span>`;
  }

    // -------------------------
  // Load chat history (robust)
  // -------------------------
  // loadHistory: fetch messages and render them each on their own line
    async function loadHistory() {
  if (!selectedPeer) {
    historyEl.innerHTML = '<div style="color:#999;text-align:center;margin-top:10px;">Select a member to load messages</div>';
    return;
  }

  historyEl.innerHTML = '<div style="color:#888;text-align:center;margin-top:8px;">Loading messages...</div>';

  try {
    const res = await fetch(`/chat/history/?peer=${encodeURIComponent(selectedPeer)}`, { credentials: 'same-origin' });
    if (!res.ok) {
      historyEl.innerHTML = `<div style="color:#d9534f;text-align:center;margin-top:10px;">Failed to load messages (status ${res.status}).</div>`;
      return;
    }

    const data = await res.json();
    historyEl.innerHTML = '';

    // assume data.messages is an array of objects: { sender, text, created_at, sender_name (optional) }
    // sort ascending by created_at to show oldest at top
    const msgs = (data.messages || []).slice().sort((a,b) => {
      const ta = new Date(a.created_at || 0).getTime() || 0;
      const tb = new Date(b.created_at || 0).getTime() || 0;
      return ta - tb;
    });

    if (!msgs.length) {
      historyEl.innerHTML = '<div style="color:#999;text-align:center;margin-top:10px;">No previous messages</div>';
    } else {
      msgs.forEach((m) => appendMessage(m));
    }
    historyEl.scrollTop = historyEl.scrollHeight;
  } catch (err) {
    console.error('loadHistory error', err);
    historyEl.innerHTML = '<div style="color:#d9534f;text-align:center;margin-top:10px;">Error loading messages. See console.</div>';
  }
}



  function initWebSocket() {
    if (ws) {
      try {
        ws.close();
      } catch (e) {}
      ws = null;
    }
    if (!TENANT_ID || !selectedPeer) return;

    const qs = `?tenant=${encodeURIComponent(TENANT_ID)}&peer=${encodeURIComponent(selectedPeer)}`;
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${scheme}://${window.location.host}/ws/chat/${qs}`;
    try {
      ws = new WebSocket(url);
      ws.onopen = () => console.log('Chat WebSocket connected');
      ws.onmessage = (ev) => {
        let msg;
        try {
          msg = JSON.parse(ev.data);
        } catch (e) {
          return;
        }

        // presence events (online/offline)
        if (msg.event === 'presence') {
          const user = msg.user;
          const status = msg.status; // 'online' or 'offline'
          const li = findMemberLiById(user);
          if (li) {
            const dot = li.querySelector('.presence-dot');
            if (dot) {
              dot.classList.remove('online', 'offline');
              dot.classList.add(status === 'online' ? 'online' : 'offline');
            }
          }
          return;
        }

        // new_message broadcast for badge handling
        if (msg.event === 'new_message') {
          // msg.to may not be current user's email depending on consumer; ignore if not for us
          // if message from a different sender, increment badge
          if (msg.from && msg.from !== selectedPeer) {
            incrementBadgeFor(msg.from, 1);
          }
          return;
        }

        // chat message event
        if (msg.event === 'message' && msg.message) {
          const m = msg.message;
          appendMessage(m);

          // if message came from selected peer and not from self, mark read
          if (m.sender !== CURRENT_USER) {
            if (m.sender === selectedPeer) {
              markRead(selectedPeer);
            } else {
              incrementBadgeFor(m.sender, 1);
            }
          }
        }
      };
      ws.onclose = () => {
        console.log('Chat WebSocket closed');
        startAjaxPolling();
      };
    } catch (e) {
      console.warn('WebSocket init failed', e);
      startAjaxPolling();
    }
  }

  // Append a single message object to the chat history as a new row.
// Message object format expected: { sender: "<email-or-id>", text: "<message text>", created_at: "<ISO timestamp>" }
function appendMessage(m) {
  try {
    // create row wrapper
    const row = document.createElement('div');
    const isMe = (m.sender === CURRENT_USER);
    row.className = 'msg-row ' + (isMe ? 'me' : 'other');

    // message bubble container
    const bubble = document.createElement('div');
    bubble.className = 'msg ' + (isMe ? 'me' : 'other');

    // text content (preserve line breaks)
    const txt = document.createElement('div');
    txt.className = 'msg-text';
    txt.textContent = m.text || ''; // use textContent to avoid accidental HTML injection

    // meta (sender short + time)
    const meta = document.createElement('div');
    meta.className = 'msg-meta';

    // show sender (for other messages), and timestamp
    const timeSpan = document.createElement('span');
    timeSpan.className = 'time';

    // format timestamp if available
    let timeStr = '';
    if (m.created_at) {
      try {
        // try ISO parse; will fall back to raw string if invalid
        const d = new Date(m.created_at);
        if (!isNaN(d.getTime())) {
          // show "HH:MM" or "DD/MM HH:MM" if older than today
          const now = new Date();
          const sameDay = d.toDateString() === now.toDateString();
          const pad = (n) => (n < 10 ? '0' + n : n);
          if (sameDay) {
            timeStr = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
          } else {
            timeStr = `${pad(d.getDate())}/${pad(d.getMonth()+1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
          }
        } else {
          timeStr = String(m.created_at).slice(0,16);
        }
      } catch (e) {
        timeStr = String(m.created_at).slice(0,16);
      }
    }
    timeSpan.textContent = timeStr;

    // show sender label for messages from others (short form)
    if (!isMe) {
      const senderSpan = document.createElement('strong');
      // show short name: either part before '<' in name or the sender id
      senderSpan.textContent = (m.sender_name || m.sender || '').toString();
      senderSpan.style.display = 'block';
      senderSpan.style.fontSize = '12px';
      senderSpan.style.marginBottom = '4px';
      senderSpan.style.color = '#0b57a4';
      meta.appendChild(senderSpan);
    }

    meta.appendChild(timeSpan);

    // assemble bubble
    bubble.appendChild(txt);
    bubble.appendChild(meta);

    row.appendChild(bubble);
    historyEl.appendChild(row);

    // keep view scrolled to bottom
    historyEl.scrollTop = historyEl.scrollHeight;
  } catch (ex) {
    console.error('appendMessage error', ex, m);
  }
}


  function startAjaxPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(() => loadHistory(), 3000);
  }

  // ------------- unread badge helpers ---------------
  async function refreshUnreadCounts() {
    try {
      const res = await fetch('/chat/unread/', { credentials: 'same-origin' });
      if (!res.ok) {
        console.warn('refreshUnreadCounts failed status', res.status);
        return;
      }
      const data = await res.json();
      // hide all badges initially
      document.querySelectorAll('.member-badge').forEach(b => b.style.display = 'none');

      data.unread.forEach(u => {
        const li = findMemberLiById(u.from);
        if (!li) return;
        const b = li.querySelector('.member-badge');
        if (b) {
          b.textContent = u.count;
          b.style.display = u.count > 0 ? 'inline-block' : 'none';
        }
      });
    } catch (e) {
      console.error('Failed to refresh unread counts', e);
    }
  }

  function incrementBadgeFor(email, by) {
    const li = findMemberLiById(email);
    if (!li) return;
    const badge = li.querySelector('.member-badge');
    if (!badge) return;
    let cur = parseInt(badge.textContent || '0') || 0;
    cur += by;
    badge.textContent = cur;
    badge.style.display = cur > 0 ? 'inline-block' : 'none';
  }

  function startUnreadPolling() {
    if (unreadPollHandle) clearInterval(unreadPollHandle);
    refreshUnreadCounts();
    unreadPollHandle = setInterval(refreshUnreadCounts, 6000);
  }
  function stopUnreadPolling() {
    if (unreadPollHandle) clearInterval(unreadPollHandle);
    unreadPollHandle = null;
  }

  // mark messages as read for this conversation
  async function markRead(peerEmail) {
  if (!peerEmail) {
    console.warn('[chat] markRead called with empty peerEmail');
    return;
  }
  console.log('[chat] markRead -> peerEmail=', peerEmail);
  try {
    const res = await fetch('/chat/mark_read/', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: JSON.stringify({ peer: peerEmail })
    });

    console.log('[chat] markRead response status=', res.status);
    if (!res.ok) {
      // fallback form-encoded attempt
      console.warn('[chat] markRead non-ok, trying fallback form post');
      const res2 = await fetch('/chat/mark_read/', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-CSRFToken': getCookie('csrftoken'),
        },
        body: `peer=${encodeURIComponent(peerEmail)}`
      });
      console.log('[chat] markRead fallback status=', res2.status);
      if (!res2.ok) {
        console.warn('[chat] markRead fallback failed', res2.status);
      }
    } else {
      // success
      const j = await res.json().catch(()=>null);
      console.log('[chat] markRead success json=', j);
      const b = document.querySelector(`[data-unread-for="${peerEmail}"]`);
      if (b) b.style.display = 'none';
    }
  } catch (err) {
    console.error('[chat] markRead exception', err);
  }
}



  // ---------------- send message ----------------
  sendBtn.addEventListener('click', sendMessage);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendMessage();
  });

    async function sendMessage() {
  const text = input.value.trim();
  if (!text) return;

  if (!selectedPeer) {
    const err = document.createElement('div');
    err.style.color = '#d9534f';
    err.style.textAlign = 'center';
    err.style.marginTop = '8px';
    err.textContent = 'Please select a member to send message';
    historyEl.appendChild(err);
    return;
  }

  // Disable send button to prevent double send
  sendBtn.disabled = true;
  sendBtn.style.opacity = '0.7';

  try {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'message', tenant: TENANT_ID, to: selectedPeer, text }));
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
        const textErr = document.createElement('div');
        textErr.style.color = '#d9534f';
        textErr.style.textAlign = 'center';
        textErr.style.marginTop = '8px';
        textErr.textContent = `Send failed (status ${res.status})`;
        historyEl.appendChild(textErr);
        return;
      }
    }

    // optimistic UI (self messages are stored server-side as read)
    appendMessage({ sender: CURRENT_USER, text });
    input.value = '';
    historyEl.scrollTop = historyEl.scrollHeight;
  } catch (err) {
    console.error('sendMessage exception', err);
    const e = document.createElement('div');
    e.style.color = '#d9534f';
    e.style.textAlign = 'center';
    e.style.marginTop = '8px';
    e.textContent = 'Error sending message (see console)';
    historyEl.appendChild(e);
  } finally {
    sendBtn.disabled = false;
    sendBtn.style.opacity = '1';
  }
}



  function getCookie(name) {
    const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return v ? v.pop() : '';
  }
})();
