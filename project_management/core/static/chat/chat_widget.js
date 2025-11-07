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

  const fetchOptions = (method = 'GET', body = null) => {
    const opts = {
      method,
      credentials: 'same-origin',
      headers: {}
    };
    if (body !== null) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    return opts;
  };

  // canonical normalizer used across the file
  function normId(v) {
    try {
      return (v || '').toString().trim().toLowerCase();
    } catch (e) {
      return '';
    }
  }

  async function loadMembers() {
    membersList.innerHTML = '<li style="text-align:center;padding:8px;color:#999;">Loading...</li>';
    try {
      const res = await fetch('/chat/members/', { credentials: 'same-origin' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      membersList.innerHTML = '';

      data.members.forEach((m) => {
        const rawId = (m.id || '').toString().trim();
        // fallback to email inside name if server sent name like "Name <email>"
        let extracted = rawId;
        if (!extracted && m.name) {
          const em = (m.name || '').match(/<([^>]+)>/);
          if (em && em[1]) extracted = em[1].trim();
        }
        // if still empty and server flagged this as self, use CURRENT_USER fallback (if set)
        let memberId = extracted || (m.is_self ? (typeof CURRENT_USER !== 'undefined' ? String(CURRENT_USER) : '') : '');
        memberId = normId(memberId); // canonical lowercase trimmed id

        const memberName = (m.name || '').toString().trim() || memberId || 'Unknown';

        const li = document.createElement('li');
        li.dataset.id = memberId;           // ALWAYS store canonical id
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

        li.addEventListener('click', () => selectPeer({ id: memberId, name: memberName, is_self: !!m.is_self }));

        li.appendChild(dot);
        li.appendChild(label);
        li.appendChild(badge);
        membersList.appendChild(li);
      });

      await refreshUnreadCounts();

    } catch (e) {
      console.error('Failed to load members', e);
      membersList.innerHTML = '<li style="color:red;padding:8px;">Error loading members</li>';
    }
  }

  // derive CURRENT_USER from DOM only if not set; always canonicalize
  (function ensureCurrentUser() {
    try {
      if (typeof CURRENT_USER !== 'undefined' && CURRENT_USER) {
        window.CURRENT_USER = normId(CURRENT_USER);
        console.info('[chat] CURRENT_USER (from template) ->', window.CURRENT_USER);
        return;
      }
      const selfLi = document.querySelector('#chat-members-list li[data-self="true"]') || document.querySelector('#chat-members-list li');
      if (selfLi && (selfLi.dataset.id || selfLi.dataset.email)) {
        window.CURRENT_USER = normId(selfLi.dataset.id || selfLi.dataset.email);
        console.info('[chat] CURRENT_USER derived from members list ->', window.CURRENT_USER);
        return;
      }
      const welcome = document.querySelector('.user-name') || document.querySelector('.brand-sub');
      if (welcome && welcome.textContent) {
        const m = welcome.textContent.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
        if (m) {
          window.CURRENT_USER = normId(m[0]);
          console.info('[chat] CURRENT_USER extracted from page ->', window.CURRENT_USER);
          return;
        }
      }
      window.CURRENT_USER = '';
    } catch (e) {
      console.warn('[chat] ensureCurrentUser failed', e);
      window.CURRENT_USER = '';
    }
  })();

  function findMemberLiById(id) {
    if (!id) return null;
    const idnorm = normId(id);
    return [...membersList.children].find((li) => normId(li.dataset.id || li.dataset.email) === idnorm);
  }

  function selectPeer(m) {
    // normalise and derive id
    let memberId = normId(m.id || '');
    if (!memberId && m.name) {
      const em = (m.name || '').match(/<([^>]+)>/);
      if (em && em[1]) memberId = normId(em[1]);
    }
    if (!memberId && m.is_self && typeof CURRENT_USER !== 'undefined') {
      memberId = normId(CURRENT_USER);
    }
    if (!memberId) {
      const selfLi = document.querySelector('#chat-members-list li[data-self="true"]');
      if (selfLi) memberId = normId(selfLi.dataset.id || selfLi.dataset.email);
    }

    // highlight active
    membersList.querySelectorAll('li').forEach((li) => li.classList.remove('active'));
    const li = findMemberLiById(memberId);
    if (li) li.classList.add('active');

    selectedPeer = memberId || '';
    selectedPeerName = (m.name || '').toString().trim() || memberId || '';
    chatWindow.classList.remove('hidden');

    historyEl.innerHTML = '<div style="color:#888;text-align:center;margin-top:8px;">Loading messages...</div>';

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
      if (selectedPeer) {
        markRead(selectedPeer).catch(err => console.warn('markRead failed in selectPeer', err));
        const b = document.querySelector(`[data-unread-for="${selectedPeer}"]`);
        if (b) b.style.display = 'none';
      } else {
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
      try { ws.close(); } catch (e) {}
      ws = null;
    }
    if (!TENANT_ID || !selectedPeer) return;

    // ensure selectedPeer is canonical
    const peerForWs = normId(selectedPeer);
    const qs = `?tenant=${encodeURIComponent(TENANT_ID)}&peer=${encodeURIComponent(peerForWs)}`;
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${scheme}://${window.location.host}/ws/chat/${qs}`;
    try {
      ws = new WebSocket(url);
      ws.onopen = () => console.log('Chat WebSocket connected');
      ws.onmessage = (ev) => {
        let msg;
        try { msg = JSON.parse(ev.data); } catch (e) { return; }

        if (msg.event === 'presence') {
          const user = normId(msg.user);
          const status = msg.status;
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

        if (msg.event === 'new_message') {
          if (msg.from) {
            const fromNorm = normId(msg.from);
            if (fromNorm !== normId(selectedPeer)) incrementBadgeFor(fromNorm, 1);
          }
          return;
        }

        if (msg.event === 'message' && msg.message) {
          const m = msg.message;
          appendMessage(m);

          // mark read if message from selected peer and not self
          const senderNorm = normId(m.sender || m.from || '');
          if (senderNorm && senderNorm !== normId(CURRENT_USER)) {
            if (senderNorm === normId(selectedPeer)) {
              markRead(selectedPeer);
            } else {
              incrementBadgeFor(senderNorm, 1);
            }
          }
        }
      };
      ws.onclose = () => {
        console.log('Chat WebSocket closed, falling back to AJAX polling');
        startAjaxPolling();
      };
    } catch (e) {
      console.warn('WebSocket init failed', e);
      startAjaxPolling();
    }
  }

  function appendMessage(m) {
    try {
      const senderRaw = (m.sender || m.from || '').toString().trim();
      const sender = normId(senderRaw);

      let me = (typeof CURRENT_USER !== 'undefined' ? normId(CURRENT_USER) : '');
      if (!me) {
        const selfLi = document.querySelector('#chat-members-list li[data-self="true"]');
        me = (selfLi && (selfLi.dataset.id || selfLi.dataset.email)) ? normId(selfLi.dataset.id || selfLi.dataset.email) : '';
      }

      const isMe = sender && me ? (sender === me) : false;

      const row = document.createElement('div');
      row.className = 'msg-row ' + (isMe ? 'me' : 'other');

      const bubble = document.createElement('div');
      bubble.className = 'msg ' + (isMe ? 'me' : 'other');

      if (!isMe) {
        const sname = document.createElement('div');
        sname.className = 'sender';
        sname.textContent = (m.sender_name || m.sender || m.from || '').toString();
        bubble.appendChild(sname);
      }

      const txt = document.createElement('div');
      txt.className = 'msg-text';
      txt.textContent = m.text || '';
      bubble.appendChild(txt);

      const meta = document.createElement('div');
      meta.className = 'msg-meta';
      const leftMeta = document.createElement('div'); leftMeta.className = 'meta-left';
      const rightMeta = document.createElement('div'); rightMeta.className = 'meta-right';
      let timeStr = '';
      if (m.created_at) {
        try {
          const d = new Date(m.created_at);
          if (!isNaN(d.getTime())) {
            const pad = n => n < 10 ? '0'+n : n;
            const now = new Date();
            if (d.toDateString() === now.toDateString()) {
              timeStr = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
            } else {
              timeStr = `${pad(d.getDate())}/${pad(d.getMonth()+1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
            }
          } else {
            timeStr = String(m.created_at).slice(0,16);
          }
        } catch(e) {
          timeStr = String(m.created_at).slice(0,16);
        }
      }
      rightMeta.textContent = timeStr;
      meta.appendChild(leftMeta); meta.appendChild(rightMeta);
      bubble.appendChild(meta);

      row.appendChild(bubble);
      historyEl.appendChild(row);
      historyEl.scrollTop = historyEl.scrollHeight;

      console.debug('[chat] appended message. sender=', sender, 'me=', me, 'isMe=', isMe, 'text=', m.text);
    } catch (err) {
      console.error('appendMessage error', err, m);
    }
  }

  function startAjaxPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(() => loadHistory(), 3000);
  }

  async function refreshUnreadCounts() {
    try {
      const res = await fetch('/chat/unread/', { credentials: 'same-origin' });
      if (!res.ok) { console.warn('refreshUnreadCounts failed status', res.status); return; }
      const data = await res.json();
      document.querySelectorAll('.member-badge').forEach(b => b.style.display = 'none');

      data.unread.forEach(u => {
        const fromNorm = normId(u.from);
        const li = findMemberLiById(fromNorm);
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

  function incrementBadgeFor(id, by) {
    const li = findMemberLiById(id);
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

  async function markRead(peerEmail) {
    if (!peerEmail) {
      console.warn('[chat] markRead called with empty peerEmail');
      return;
    }
    const peerNorm = normId(peerEmail);
    try {
      const res = await fetch('/chat/mark_read/', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken'),
        },
        body: JSON.stringify({ peer: peerNorm })
      });

      if (!res.ok) {
        console.warn('[chat] markRead non-ok, trying fallback form post');
        const res2 = await fetch('/chat/mark_read/', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': getCookie('csrftoken'),
          },
          body: `peer=${encodeURIComponent(peerNorm)}`
        });
        if (!res2.ok) console.warn('[chat] markRead fallback failed', res2.status);
      } else {
        const j = await res.json().catch(()=>null);
        const b = document.querySelector(`[data-unread-for="${peerNorm}"]`);
        if (b) b.style.display = 'none';
      }
    } catch (err) {
      console.error('[chat] markRead exception', err);
    }
  }

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

    sendBtn.disabled = true;
    sendBtn.style.opacity = '0.7';

    try {
      const toNorm = normId(selectedPeer);
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'message', tenant: TENANT_ID, to: toNorm, text }));
      } else {
        const res = await fetch('/chat/send/', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken'),
          },
          body: JSON.stringify({ to: toNorm, text }),
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

      appendMessage({ sender: CURRENT_USER, text, created_at: new Date().toISOString() });
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
