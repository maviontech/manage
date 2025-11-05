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
      // include credentials to avoid Django redirect to login
      const res = await fetch('/chat/members/', { credentials: 'same-origin' });
      if (!res.ok) {
        throw new Error('Failed to load members: HTTP ' + res.status);
      }
      const data = await res.json();
      membersList.innerHTML = '';

      // remove old event listeners (if any)
      // (we simply replace innerHTML below, so previous elements are dropped)
      data.members.forEach((m) => {
        const li = document.createElement('li');
        li.dataset.id = m.id;
        li.dataset.email = m.id;
        li.dataset.name = m.name;
        if (m.is_self) li.dataset.self = 'true';
        // presence dot + label + unread badge
        const dot = document.createElement('span');
        dot.className = 'presence-dot offline';
        dot.setAttribute('data-user', m.id);

        // If it's self, mark online immediately
        if (m.is_self) {
          dot.classList.remove('offline');
          dot.classList.add('online');
        }

        const label = document.createElement('span');
        label.textContent = m.name;
        label.style.verticalAlign = 'middle';
        label.style.marginLeft = '6px';
        label.style.fontSize = '13px';
        label.style.fontWeight = m.is_self ? '600' : '500';

        const badge = document.createElement('span');
        badge.className = 'member-badge';
        badge.style.display = 'none';
        badge.setAttribute('data-unread-for', m.id);

        // Make the list item clickable for everyone (including self)
        li.addEventListener('click', () => selectPeer(m));
        // Add inner elements and append
        li.appendChild(dot);
        li.appendChild(label);
        li.appendChild(badge);
        membersList.appendChild(li);
      });

      // fetch unread counts once immediately
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
    // highlight active
    membersList.querySelectorAll('li').forEach((li) => li.classList.remove('active'));
    const li = findMemberLiById(m.id);
    if (li) li.classList.add('active');

    selectedPeer = m.id;
    selectedPeerName = m.name;
    chatWindow.classList.remove('hidden');
    historyEl.innerHTML = '<div style="color:#888;text-align:center;margin-top:8px;">Loading messages...</div>';

    updateHeaderPeer(selectedPeerName);
    initWebSocket();
    loadHistory().then(() => {
      // After history loaded, mark messages as read
      markRead(selectedPeer);
      // hide unread badge for this peer
      const b = document.querySelector(`[data-unread-for="${selectedPeer}"]`);
      if (b) b.style.display = 'none';
    });
  }

  function updateHeaderPeer(name) {
    const header = document.querySelector('.chat-header .chat-title');
    header.innerHTML = `Team chat <span class="chat-partner">with ${name}</span>`;
  }

  async function loadHistory() {
    if (!selectedPeer) return;
    const res = await fetch(`/chat/history/?peer=${encodeURIComponent(selectedPeer)}`, { credentials: 'same-origin' });
    if (!res.ok) {
      historyEl.innerHTML = '<div style="color:red;text-align:center;margin-top:10px;">Failed to load history</div>';
      return;
    }
    const data = await res.json();
    historyEl.innerHTML = '';
    if (!data.messages.length) {
      historyEl.innerHTML = '<div style="color:#999;text-align:center;margin-top:10px;">No previous messages</div>';
    } else {
      data.messages.forEach((m) => appendMessage(m));
    }
    historyEl.scrollTop = historyEl.scrollHeight;
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

  function appendMessage(m) {
    const d = document.createElement('div');
    d.className = m.sender === CURRENT_USER ? 'msg me' : 'msg other';
    d.textContent = m.text;
    historyEl.appendChild(d);
    historyEl.scrollTop = historyEl.scrollHeight;
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
    try {
      await fetch('/chat/mark_read/', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken'),
        },
        body: JSON.stringify({ peer: peerEmail }),
      });
      const b = document.querySelector(`[data-unread-for="${peerEmail}"]`);
      if (b) b.style.display = 'none';
    } catch (e) {
      console.warn('markRead failed', e);
    }
  }

  // ---------------- send message ----------------
  sendBtn.addEventListener('click', sendMessage);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendMessage();
  });

  async function sendMessage() {
    const text = input.value.trim();
    if (!text || !selectedPeer) return;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'message', tenant: TENANT_ID, to: selectedPeer, text }));
    } else {
      await fetch('/chat/send/', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken'),
        },
        body: JSON.stringify({ to: selectedPeer, text }),
      });
    }
    input.value = '';
    appendMessage({ sender: CURRENT_USER, text });
  }

  function getCookie(name) {
    const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
    return v ? v.pop() : '';
  }
})();
