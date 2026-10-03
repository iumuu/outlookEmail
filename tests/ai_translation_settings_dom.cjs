const assert = require('node:assert/strict');
const fs = require('node:fs');
const { JSDOM } = require('jsdom');
const template = fs.readFileSync('templates/partials/index/dialogs-management.html', 'utf8');
const section = template.split('<section class="settings-section" id="settingsAiTranslationSection">')[1].split('</section>')[0];
const source = 'async function loadTranslationSettings' + fs.readFileSync('static/js/index/07-settings.js', 'utf8').split('async function loadTranslationSettings')[1];
(async () => {
    const dom = new JSDOM('<section>' + section + '</section>');
    const w = dom.window;
    for (const id of ['translationBaseUrl', 'translationApiKey', 'translationModel', 'translationTimeout']) {
        assert.equal(w.document.getElementById(id).className, 'form-input');
        assert.equal(w.document.querySelector(`label[for="${id}"]`).className, 'form-label');
    }
    assert.equal(w.document.getElementById('translationLanguage').className, 'form-select');
    assert.ok(w.document.querySelector('.settings-panel.settings-panel-grid'));
    assert.ok(w.document.querySelector('.btn.btn-primary'));
    assert.ok(w.document.querySelector('.btn.btn-secondary'));
    const requests = [];
    w.confirm = () => true;
    w.fetch = async (url, options = {}) => {
        requests.push({ url, options });
        return { json: async () => options.method === 'POST'
            ? { success: true, message: 'OK' }
            : { success: true, settings: { base_url: 'https://example.com/v1', model: 'model', timeout_seconds: 45, default_language: 'ja', api_key_configured: true, source: 'settings' } } };
    };
    Object.assign(w, new Function('window', 'document', 'fetch', source + '; return {loadTranslationSettings, submitTranslationSettings};')(w, w.document, (...args) => w.fetch(...args)));
    await w.loadTranslationSettings();
    assert.equal(w.document.getElementById('translationApiKey').type, 'password');
    assert.equal(w.document.getElementById('translationApiKey').value, '');
    assert.match(w.document.getElementById('translationKeyStatus').textContent, /已配置/);
    assert.equal(w.document.getElementById('translationLanguage').value, 'ja');
    const button = w.document.querySelector('button');
    w.document.getElementById('translationApiKey').value = 'typed-secret';
    await w.submitTranslationSettings(true, button);
    const test = requests.find(r => r.url.endsWith('/test'));
    assert.equal(JSON.parse(test.options.body).api_key, 'typed-secret');
    assert.equal(w.document.getElementById('translationApiKey').value, '');
    assert.equal(button.disabled, false);
    w.document.getElementById('translationClearKey').checked = true;
    await w.submitTranslationSettings(false, button);
    const save = requests.find(r => r.options.method === 'POST' && !r.url.endsWith('/test'));
    assert.equal(JSON.parse(save.options.body).clear_api_key, true);
    assert.equal(JSON.parse(save.options.body).api_key, '');
    w.fetch = async () => { throw new Error('network failure'); };
    w.document.getElementById('translationApiKey').value = 'typed-secret';
    await w.submitTranslationSettings(true, button);
    assert.equal(w.document.getElementById('translationApiKey').value, '');
    assert.equal(button.disabled, false);
    dom.window.close();
    console.log('Settings DOM load, masked key, test, clear/save and failure cases passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
