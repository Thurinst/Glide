// 后台 Service Worker：统一走这里调翻译接口，避免页面 CSP 拦截。
// content.js 只发消息，不直接 fetch 翻译接口。

const DEFAULTS = {
  engine: 'googleFree', // googleFree | openAI | deepL
  apiBaseURL: 'https://api.openai.com/v1',
  apiKey: '',
  model: 'gpt-4o-mini',
  deepLKey: '',
  target: 'auto', // auto | zh-CN | en
  bilingual: true, // true=原文+译文对照，false=只显示译文替换原文
  autoTranslate: false, // 打开网页自动翻译（默认关，手动 Alt+T 开）
};

function targetLangFor(text, target) {
  if (target !== 'auto') return target;
  return /[\u4e00-\u9fff]/.test(text) ? 'en' : 'zh-CN';
}

async function googleTranslate(text, target) {
  const tl = target === 'en' ? 'en' : 'zh-CN';
  const url = 'https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl='
    + encodeURIComponent(tl) + '&dt=t&q=' + encodeURIComponent(text);
  const res = await fetch(url, { headers: { 'User-Agent': 'Mozilla/5.0' } });
  if (!res.ok) throw new Error('Google 翻译返回 ' + res.status);
  const json = await res.json();
  const out = (json[0] || []).map(s => s[0]).filter(Boolean).join('');
  if (!out) throw new Error('Google 翻译返回为空');
  return out;
}

async function openAITranslate(text, target, cfg) {
  if (!cfg.apiKey) throw new Error('请先在设置里填写 AI API Key');
  const targetName = target === 'en' ? 'English' : 'Simplified Chinese';
  const base = cfg.apiBaseURL.replace(/\/+$/, '');
  const res = await fetch(base + '/chat/completions', {
    method: 'POST',
    headers: {
      'Authorization': 'Bearer ' + cfg.apiKey,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: cfg.model || 'gpt-4o-mini',
      temperature: 0.2,
      messages: [
        { role: 'system', content: `You are a professional translator. Translate the user text into ${targetName}. Return ONLY the translation, no explanation, no quotes. Preserve line breaks.` },
        { role: 'user', content: text },
      ],
    }),
  });
  if (!res.ok) throw new Error('AI 接口返回 ' + res.status + '：' + (await res.text()).slice(0, 200));
  const json = await res.json();
  const out = (json.choices?.[0]?.message?.content || '').trim();
  if (!out) throw new Error('AI 接口返回为空');
  return out;
}

async function deepLTranslate(text, target, cfg) {
  if (!cfg.deepLKey) throw new Error('请先在设置里填写 DeepL Key');
  const tl = target === 'en' ? 'EN-US' : 'ZH';
  const host = cfg.deepLKey.endsWith(':fx') ? 'https://api-free.deepl.com' : 'https://api.deepl.com';
  const res = await fetch(host + '/v2/translate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ auth_key: cfg.deepLKey, text, target_lang: tl }),
  });
  if (!res.ok) throw new Error('DeepL 返回 ' + res.status);
  const json = await res.json();
  const out = json.translations?.[0]?.text;
  if (!out) throw new Error('DeepL 返回为空');
  return out;
}

// 批量翻译：全文翻译时多段合并成一次请求，省次数、保上下文。
// 用 \n§N§ 分隔，译完再按标记拆回来；拆不开就逐段重试。
async function translateBatch(texts, cfg) {
  const targets = texts.map(t => targetLangFor(t, cfg.target));
  // 目标语言不一致时（中英混排页）按语言分组翻译
  const groups = {};
  texts.forEach((t, i) => { (groups[targets[i]] ||= []).push([i, t]); });
  const out = new Array(texts.length);
  for (const [tl, items] of Object.entries(groups)) {
    if (cfg.engine === 'openAI') {
      // AI 按段逐条翻，质量比合并高，且不易丢段
      for (const [i, t] of items) out[i] = await openAITranslate(t, tl, cfg);
    } else {
      const joined = items.map(([, t], k) => `\n§${k}§\n${t}`).join('\n');
      const fn = cfg.engine === 'deepL'
        ? (txt) => deepLTranslate(txt, tl, cfg)
        : (txt) => googleTranslate(txt, tl);
      let translated = await fn(joined);
      const map = {};
      translated.replace(/§(\d+)§\s*([\s\S]*?)(?=§\d+§|$)/g, (_, k, v) => { map[k] = v.trim(); return ''; });
      if (Object.keys(map).length === items.length) {
        items.forEach(([,], k) => { out[items[k][0]] = map[k] || ''; });
      } else {
        // 拆分失败：逐段重试
        for (const [i, t] of items) out[i] = await fn(t);
      }
    }
  }
  return out;
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    const cfg = { ...DEFAULTS, ...(await chrome.storage.sync.get(DEFAULTS)) };
    if (msg.type === 'translate') {
      const target = targetLangFor(msg.text, cfg.target);
      const fn = cfg.engine === 'openAI' ? () => openAITranslate(msg.text, target, cfg)
        : cfg.engine === 'deepL' ? () => deepLTranslate(msg.text, target, cfg)
        : () => googleTranslate(msg.text, target);
      sendResponse({ ok: true, text: await fn() });
    } else if (msg.type === 'translateBatch') {
      sendResponse({ ok: true, texts: await translateBatch(msg.texts, cfg) });
    } else if (msg.type === 'getSettings') {
      sendResponse({ ok: true, settings: cfg });
    }
  })().catch(e => sendResponse({ ok: false, error: String(e.message || e) }));
  return true; // 异步回包
});

chrome.commands.onCommand.addListener(async (command) => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) return;
  if (command === 'toggle-translate') chrome.tabs.sendMessage(tab.id, { type: 'togglePage' });
  if (command === 'translate-selection') chrome.tabs.sendMessage(tab.id, { type: 'translateSelection' });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === 'translate-selection' && tab?.id) {
    chrome.tabs.sendMessage(tab.id, { type: 'translateSelection' });
  }
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'translate-selection', title: '翻译选中文字', contexts: ['selection'],
  });
});
