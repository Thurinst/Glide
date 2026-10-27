// 无感翻译 — content script
// 1. 全文沉浸式翻译：段落下插入译文（双语对照），可一键还原
// 2. 划词翻译：选中文字弹小窗，Alt+Q 也能触发
(() => {
  if (window.__immersiveLiteLoaded) return;
  window.__immersiveLiteLoaded = true;

  const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEXTAREA', 'INPUT', 'SELECT', 'BUTTON', 'CODE', 'PRE', 'SVG', 'CANVAS', 'IFRAME']);
  const TRANSLATED_CLASS = 'immersive-lite-translated';
  let pageTranslated = false;
  let translating = false;
  let settings = { bilingual: true, autoTranslate: false };

  chrome.storage.sync.get(['bilingual', 'autoTranslate'], (s) => {
    settings = { ...settings, ...s };
    if (settings.autoTranslate) setTimeout(() => togglePage(), 800);
  });
  chrome.storage.onChanged.addListener((changes) => {
    if (changes.bilingual) settings.bilingual = changes.bilingual.newValue;
    if (changes.autoTranslate) settings.autoTranslate = changes.autoTranslate.newValue;
  });

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === 'togglePage') togglePage();
    if (msg.type === 'translateSelection') translateSelection();
  });

  // ---------- 全文翻译 ----------
  function collectBlocks() {
    // 取可见的段落级元素：p / h1-h6 / li / td / 标题等，太短的（<2字）跳过
    const els = document.querySelectorAll('p, h1, h2, h3, h4, h5, h6, li, td, th, figcaption, blockquote, dd, dt');
    const blocks = [];
    for (const el of els) {
      if (el.closest('.immersive-lite-box, .immersive-lite-popup')) continue;
      if (el.closest('header, nav, footer')) continue;
      if (SKIP_TAGS.has(el.tagName)) continue;
      // 只取叶子段落：里面没有其他段落级子元素，避免父子重复翻译
      if (el.querySelector('p, h1, h2, h3, h4, li')) continue;
      const text = (el.innerText || '').trim();
      if (text.length < 2 || text.length > 3000) continue;
      if (!/[a-zA-Z\u4e00-\u9fff]/.test(text)) continue;
      const rect = el.getBoundingClientRect();
      if (rect.height === 0 && rect.width === 0) continue; // 隐藏元素
      blocks.push({ el, text });
    }
    return blocks;
  }

  async function togglePage() {
    if (translating) return;
    if (pageTranslated) { restorePage(); return; }
    translating = true;
    showToast('正在翻译本页…');
    try {
      const blocks = collectBlocks();
      if (!blocks.length) { showToast('本页没有可翻译的段落'); return; }
      // 分批：每批 20 段，避免一次请求过大
      for (let i = 0; i < blocks.length; i += 20) {
        const batch = blocks.slice(i, i + 20);
        const res = await chrome.runtime.sendMessage({ type: 'translateBatch', texts: batch.map(b => b.text) });
        if (!res?.ok) throw new Error(res?.error || '翻译失败');
        batch.forEach((b, k) => insertTranslation(b.el, res.texts[k]));
      }
      pageTranslated = true;
      showToast(`已翻译 ${blocks.length} 段，Alt+T 可还原`);
    } catch (e) {
      showToast('翻译失败：' + (e.message || e));
    } finally {
      translating = false;
    }
  }

  function insertTranslation(el, translated) {
    if (!translated || translated === el.innerText.trim()) return;
    el.classList.add(TRANSLATED_CLASS);
    const box = document.createElement('div');
    box.className = 'immersive-lite-box';
    box.dataset.immersiveLite = '1';
    if (settings.bilingual) {
      box.textContent = translated;
    } else {
      // 只显示译文：把原文藏起来，译文放原文位置
      el.dataset.immersiveLiteOriginalDisplay = el.style.display;
      box.textContent = translated;
    }
    el.after(box);
  }

  function restorePage() {
    document.querySelectorAll('.immersive-lite-box').forEach(b => b.remove());
    document.querySelectorAll('.' + TRANSLATED_CLASS).forEach(el => el.classList.remove(TRANSLATED_CLASS));
    pageTranslated = false;
    showToast('已还原原文');
  }

  // ---------- 划词翻译 ----------
  let popup = null;
  let lastSelection = '';

  document.addEventListener('mouseup', (e) => {
    if (e.target.closest('.immersive-lite-popup')) return;
    setTimeout(() => {
      const sel = window.getSelection();
      const text = (sel?.toString() || '').trim();
      if (text && text.length >= 1 && text.length <= 5000 && text !== lastSelection) {
        lastSelection = text;
        const range = sel.getRangeAt(0);
        const rect = range.getBoundingClientRect();
        showPopup(text, rect.left + window.scrollX, rect.bottom + window.scrollY);
      } else if (!text) {
        hidePopup();
      }
    }, 120);
  });
  document.addEventListener('mousedown', (e) => {
    if (!e.target.closest('.immersive-lite-popup')) hidePopup();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') hidePopup();
  });

  async function translateSelection() {
    const text = (window.getSelection()?.toString() || '').trim();
    if (!text) { showToast('请先选中要翻译的文字'); return; }
    const rect = window.getSelection().getRangeAt(0).getBoundingClientRect();
    showPopup(text, rect.left + window.scrollX, rect.bottom + window.scrollY);
  }

  function showPopup(text, x, y) {
    hidePopup();
    popup = document.createElement('div');
    popup.className = 'immersive-lite-popup';
    popup.innerHTML = `
      <div class="il-original"></div>
      <div class="il-result">翻译中…</div>
      <div class="il-actions">
        <button class="il-copy">复制译文</button>
        <button class="il-speak">朗读</button>
        <button class="il-close">✕</button>
      </div>`;
    popup.querySelector('.il-original').textContent = text.length > 120 ? text.slice(0, 120) + '…' : text;
    popup.style.left = Math.min(x, window.innerWidth - 340) + 'px';
    popup.style.top = (y + 8) + 'px';
    popup.style.position = 'absolute';
    document.body.appendChild(popup);

    popup.querySelector('.il-close').onclick = hidePopup;
    popup.querySelector('.il-copy').onclick = async () => {
      const t = popup.querySelector('.il-result').textContent;
      if (t && t !== '翻译中…') {
        await navigator.clipboard.writeText(t);
        popup.querySelector('.il-copy').textContent = '已复制 ✓';
      }
    };
    popup.querySelector('.il-speak').onclick = () => {
      const t = popup.querySelector('.il-result').textContent;
      if (!t || t === '翻译中…') return;
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(t);
      u.lang = /[\u4e00-\u9fff]/.test(t) ? 'zh-CN' : 'en-US';
      speechSynthesis.speak(u);
    };

    chrome.runtime.sendMessage({ type: 'translate', text })
      .then(res => {
        if (!popup) return;
        popup.querySelector('.il-result').textContent = res?.ok ? res.text : ('翻译失败：' + (res?.error || '未知错误'));
      })
      .catch(e => { if (popup) popup.querySelector('.il-result').textContent = '翻译失败：' + e.message; });
  }

  function hidePopup() {
    if (popup) { popup.remove(); popup = null; }
  }

  // ---------- 小提示 ----------
  let toastTimer = null;
  function showToast(msg) {
    let toast = document.querySelector('.immersive-lite-toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.className = 'immersive-lite-toast';
      document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.style.opacity = '1';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.style.opacity = '0'; }, 2500);
  }
})();
