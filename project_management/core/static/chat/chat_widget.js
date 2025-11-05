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

  function showPanel() {
    panel.classList.remove('hidden');
  }
  function hidePanel() {
    panel.classList.add('hidden');
  }

  openBtn.addEventListener('click', () => {
    showPanel();
    loadMembers();
  });
  closeBtn.addEventListener('click', hidePanel);

  // -------------------------
  // Load members list
  // -------------------------
  async function loadMembers() {
    membersList.innerHTML = '<li style="text-align:center;padding:8px;color:#999;">Loading...</li>';
    try {
      const res = await fetch('/chat/members/');
      const data = await res.json();
      membersList.innerHTML = '';
      data.members.forEach((m) => {
        const li = document.createElement('li');
        li.textContent = m.name;
        li.dataset.id = m.id;
        li.dataset.name = m.name;
        li.addEventListener('click', () => selectPeer(m));
        membersList.appendChild(li);
      });
    } catch (e) {
      console.error('Failed to load members', e);
      membersList.innerHTML = '<li style="color:red;padding:8px;">Error loading members</li>';
    }
  }

  // -------------------------
  // When a member is selected
  // -------------------------
  function selectPeer(m) {
    // highlight active member
    membersList.querySelectorAll('li').forEach((li) => li.classList.remove('active'));
    const li = [...membersList.children].find((x) => x.dataset.id === m.id);
    if (li) li.classList.add('active');

    selectedPeer = m.id;
    selectedPeerName = m.name;
    chatWindow.classList.remove('hidden');
    historyEl.innerHTML = '<div style="color:#888;text-align:center;margin-top:8px;">Loading messages...</div>';

    updateHeaderPeer(selectedPeerName);
    initWebSocket();
    loadHistory();
  }

  // -------------------------
  // Update header with peer name
  // -------------------------
  function updateHeaderPeer(name) {
    const header = document.querySelector('.chat-header .chat-title');
    header.innerHTML = `Team chat <span class="chat-partner">with ${name}</span>`;
  }

  // -------------------------
  // Load chat history
  // -------------------------
  async function loadHistory() {
    if (!selectedPeer) return;
    const res = await fetch(`/chat/history/?peer=${encodeURIComponent(selectedPeer)}`);
    const data = await res.json();
    historyEl.innerHTML = '';
    if (!data.messages.length) {
      historyEl.innerHTML = '<div style="color:#999;text-align:center;margin-top:10px;">No previous messages</div>';
    } else {
      data.messages.forEach((m) => appendMessage(m));
    }
    historyEl.scrollTop = historyEl.scrollHeight;
  }

  // -------------------------
  // WebSocket setup
  // -------------------------
  function initWebSocket() {
    if (ws) {
      try {
        ws.close();
      } catch (e) {}
      ws = null;
    }
    if (!TENANT_ID) return;

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
        appendMessage(msg);
      };
      ws.onclose = () => {
        console.log('Chat WebSocket closed');
        startAjaxPolling();
      };
    } catch (e) {
      console.warn('WebSocket failed, fallback to AJAX');
      startAjaxPolling();
    }
  }

  // -------------------------
  // Append message
  // -------------------------
  function appendMessage(m) {
    const d = document.createElement('div');
    d.className = m.sender === CURRENT_USER ? 'msg me' : 'msg other';
    d.textContent = m.text;
    historyEl.appendChild(d);
    historyEl.scrollTop = historyEl.scrollHeight;
  }

  // -------------------------
  // Fallback polling
  // -------------------------
  function startAjaxPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(() => loadHistory(), 3000);
  }

  // -------------------------
  // Send message
  // -------------------------
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
