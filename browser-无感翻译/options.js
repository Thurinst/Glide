const DEFAULTS = {
  engine: 'googleFree',
  apiBaseURL: 'https://api.openai.com/v1',
  apiKey: '', model: 'gpt-4o-mini', deepLKey: '',
  target: 'auto', bilingual: true, autoTranslate: false,
};
const $ = (id) => document.getElementById(id);

function refreshVisibility() {
  $('aiFields').style.display = $('engine').value === 'openAI' ? 'block' : 'none';
  $('deeplFields').style.display = $('engine').value === 'deepL' ? 'block' : 'none';
}
$('engine').addEventListener('change', refreshVisibility);

chrome.storage.sync.get(DEFAULTS, (s) => {
  $('engine').value = s.engine;
  $('apiBaseURL').value = s.apiBaseURL;
  $('apiKey').value = s.apiKey;
  $('model').value = s.model;
  $('deepLKey').value = s.deepLKey;
  $('target').value = s.target;
  $('bilingual').checked = s.bilingual;
  $('autoTranslate').checked = s.autoTranslate;
  refreshVisibility();
});

$('save').onclick = () => {
  chrome.storage.sync.set({
    engine: $('engine').value,
    apiBaseURL: $('apiBaseURL').value.trim(),
    apiKey: $('apiKey').value.trim(),
    model: $('model').value.trim() || 'gpt-4o-mini',
    deepLKey: $('deepLKey').value.trim(),
    target: $('target').value,
    bilingual: $('bilingual').checked,
    autoTranslate: $('autoTranslate').checked,
  }, () => {
    const el = $('saved');
    el.style.display = 'inline';
    setTimeout(() => el.style.display = 'none', 2000);
  });
};
