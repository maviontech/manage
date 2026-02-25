// Compact enterprise chat widget controller.
(function () {
    'use strict';

    function ready(fn) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', fn);
        } else {
            fn();
        }
    }

    ready(function () {
        const root = document.getElementById('chat-shortcut');
        const openBtn = document.getElementById('chat-open-btn');
        const panel = document.getElementById('chat-panel');
        const closeBtn = document.getElementById('chat-close-btn');
        const maximizeBtn = document.getElementById('chat-maximize-btn');
        const iframe = document.getElementById('chat-widget-iframe');
        if (!root || !openBtn || !panel || !closeBtn || !maximizeBtn || !iframe) return;

        const KEY = 'trackline.chat.widget.maximized';
        const icon = maximizeBtn.querySelector('i');
        let maximized = localStorage.getItem(KEY) === '1';

        function applyMaximizedState() {
            panel.classList.toggle('chat-panel-maximized', maximized);
            maximizeBtn.setAttribute('aria-label', maximized ? 'Restore chat size' : 'Maximize chat');
            if (icon) {
                icon.classList.toggle('fa-expand', !maximized);
                icon.classList.toggle('fa-compress', maximized);
            }
        }

        function ensureIframeLoaded() {
            if (iframe.src && iframe.src !== 'about:blank') return;
            const src = iframe.getAttribute('data-src');
            if (src) iframe.src = src;
        }

        function openPanel() {
            ensureIframeLoaded();
            panel.classList.remove('hidden');
            panel.classList.add('chat-panel-open');
            root.classList.add('chat-open');
        }

        function closePanel() {
            panel.classList.add('hidden');
            panel.classList.remove('chat-panel-open');
            root.classList.remove('chat-open');
        }

        openBtn.addEventListener('click', function (e) {
            e.preventDefault();
            if (panel.classList.contains('hidden')) openPanel();
            else closePanel();
        });

        closeBtn.addEventListener('click', function () {
            closePanel();
        });

        maximizeBtn.addEventListener('click', function () {
            maximized = !maximized;
            localStorage.setItem(KEY, maximized ? '1' : '0');
            applyMaximizedState();
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && !panel.classList.contains('hidden')) {
                closePanel();
            }
        });

        document.addEventListener('click', function (e) {
            if (panel.classList.contains('hidden')) return;
            if (root.contains(e.target)) return;
            closePanel();
        });

        applyMaximizedState();
    });
})();
