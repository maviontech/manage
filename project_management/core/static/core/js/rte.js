/* Trackline lightweight rich-text editor.
   Wires a contenteditable surface to a hidden <textarea> so the form posts HTML.
   Self-contained (uses document.execCommand) — no external dependency. */
(function () {
  if (window.__TLRTE_INIT__) return;
  window.__TLRTE_INIT__ = true;

  function setup(rte) {
    if (rte.getAttribute('data-rte-ready')) return;
    rte.setAttribute('data-rte-ready', '1');
    var editor = rte.querySelector('.tl-rte-editor');
    var textarea = rte.querySelector('textarea');
    var form = rte.closest('form');
    if (!editor || !textarea) return;

    function sync() { textarea.value = editor.innerHTML.trim() === '<br>' ? '' : editor.innerHTML; }

    editor.addEventListener('input', sync);
    editor.addEventListener('blur', sync);

    // ---- image upload support ----
    var uploadUrl = rte.getAttribute('data-rte-upload');
    function getCookie(name) {
      var m = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
      return m ? decodeURIComponent(m.pop()) : '';
    }
    function insertImageFile(file) {
      if (!uploadUrl || !file) return;
      if (file.size > 5 * 1024 * 1024) { alert('Image too large (max 5MB).'); return; }
      var fd = new FormData(); fd.append('image', file);
      fetch(uploadUrl, { method: 'POST', headers: { 'X-CSRFToken': getCookie('csrftoken') }, body: fd })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d && d.url) { editor.focus(); document.execCommand('insertImage', false, d.url); sync(); }
          else { alert((d && d.error) || 'Image upload failed.'); }
        })
        .catch(function () { alert('Image upload failed.'); });
    }
    function pickImage() {
      var inp = document.createElement('input');
      inp.type = 'file'; inp.accept = 'image/*';
      inp.addEventListener('change', function () { if (inp.files && inp.files[0]) insertImageFile(inp.files[0]); });
      inp.click();
    }
    // paste screenshots directly
    editor.addEventListener('paste', function (e) {
      var items = (e.clipboardData || {}).items || [];
      for (var i = 0; i < items.length; i++) {
        if (items[i].type && items[i].type.indexOf('image') === 0) {
          e.preventDefault(); insertImageFile(items[i].getAsFile()); return;
        }
      }
    });

    rte.querySelectorAll('[data-cmd]').forEach(function (ctrl) {
      var cmd = ctrl.getAttribute('data-cmd');
      if (ctrl.tagName === 'SELECT') {
        ctrl.addEventListener('mousedown', saveSel);
        ctrl.addEventListener('change', function () {
          restoreSel(); editor.focus();
          if (ctrl.value) document.execCommand(cmd, false, ctrl.value);
          ctrl.selectedIndex = 0; sync();
        });
      } else if (ctrl.type === 'color') {
        ctrl.addEventListener('mousedown', saveSel);
        ctrl.addEventListener('input', function () {
          restoreSel(); editor.focus();
          document.execCommand(cmd, false, ctrl.value); sync();
        });
      } else {
        // keep the current selection when clicking a toolbar button
        ctrl.addEventListener('mousedown', function (e) { e.preventDefault(); });
        ctrl.addEventListener('click', function () {
          editor.focus();
          if (cmd === 'insertImageUpload') {
            pickImage();
          } else if (cmd === 'createLink') {
            var url = window.prompt('Link URL:', 'https://');
            if (url) document.execCommand('createLink', false, url);
          } else {
            document.execCommand(cmd, false, null);
          }
          sync(); updateActive();
        });
      }
    });

    var saved = null;
    function saveSel() { var s = window.getSelection(); if (s.rangeCount) saved = s.getRangeAt(0).cloneRange(); }
    function restoreSel() { if (saved) { var s = window.getSelection(); s.removeAllRanges(); s.addRange(saved); } }

    function updateActive() {
      rte.querySelectorAll('.tl-rte-btn[data-cmd]').forEach(function (btn) {
        var c = btn.getAttribute('data-cmd');
        if (c === 'createLink') return;
        try { btn.classList.toggle('active', document.queryCommandState(c)); } catch (e) {}
      });
    }
    editor.addEventListener('keyup', updateActive);
    editor.addEventListener('mouseup', updateActive);

    if (form) form.addEventListener('submit', sync);
    sync();
  }

  function initAll() { document.querySelectorAll('.tl-rte').forEach(setup); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initAll);
  else initAll();
  window.TLRTE = { initAll: initAll };
})();
