document.getElementById('toggle').onclick = async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id) chrome.tabs.sendMessage(tab.id, { type: 'togglePage' });
  window.close();
};
document.getElementById('options').onclick = () => chrome.runtime.openOptionsPage();

chrome.storage.sync.get(['engine', 'apiKey', 'deepLKey'], (s) => {
  const engineName = { googleFree: 'Google 免费机翻', openAI: 'AI 大模型', deepL: 'DeepL' }[s.engine || 'googleFree'];
  const hasKey = s.engine === 'openAI' ? !!s.apiKey : s.engine === 'deepL' ? !!s.deepLKey : true;
  document.getElementById('status').textContent =
    `当前引擎：${engineName}` + (hasKey ? '' : '（未填 Key，翻译会失败，请去设置里填）');
});
