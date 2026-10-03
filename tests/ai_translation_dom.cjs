/* Optional DOM regression suite: NODE_PATH=/path/to/node_modules node tests/ai_translation_dom.cjs */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const createDOMPurify = require('dompurify');
const source = fs.readFileSync(path.join(__dirname, '../static/js/index/05-emails.js'), 'utf8');
const mount = 'function mountEmailTranslation' + source.split('function mountEmailTranslation')[1].split('function renderEmailDetail')[0];

async function runCase(html, invalid = false, hidden = false) {
    const dom = new JSDOM('<div id="detail"><div class="email-detail-body"></div><section class="email-translation"><button>Translate</button><select><option value="zh-CN">Chinese</option></select><p role="status"></p><details class="email-translation-result" hidden><h3 class="email-translation-subject"></h3><div class="email-translation-body"></div></details></section></div>');
    const w = dom.window;
    const container = w.document.getElementById('detail');
    const originalBody = container.querySelector('.email-detail-body');
    if (html) {
        const original = w.document.createElement('iframe');
        original.id = 'emailBodyFrame';
        original.srcdoc = '<html><head><style>body{font-family:Arial;font-size:15px}td{padding:12px}</style></head><body><table style="border:1px solid red"><tr><td> Hello <b>world</b></td><td><a href="https://example.com">Link</a><img src="https://example.com/logo.png" width="20"></td></tr></table><div hidden>Hidden</div><script>evil()</script><div onclick="evil()">Last</div></body></html>';
        originalBody.append(original);
    } else {
        originalBody.innerHTML = '<div class="email-body-text" style="white-space:pre-wrap;font-size:15px;line-height:1.7">Hello\nWorld &lt;b&gt;literal&lt;/b&gt;</div>';
    }
    const before = originalBody.innerHTML;
    w.DOMPurify = createDOMPurify(w);
    w.confirm = () => !hidden;
    let sent;
    w.fetchWithTimeout = async (url, options) => {
        sent = JSON.parse(options.body);
        return { ok: true, json: async () => ({ success: true, translation: {
            subject: '<img src=x onerror=evil()>',
            segments: invalid ? [] : sent.segments.map(({ id }) => ({ id, text: '<script>literal-' + id + '</script>' }))
        } }) };
    };
    const mountInWindow = new Function('window', 'document', 'DOMPurify', 'DOMParser',
        'NodeFilter', 'AbortController', 'fetchWithTimeout',
        'let activeTranslationController = null; ' + mount + '; return mountEmailTranslation;')(
        w, w.document, w.DOMPurify, w.DOMParser, w.NodeFilter, w.AbortController, w.fetchWithTimeout);
    mountInWindow(container, { subject: 'Hello' }, html);
    container.querySelector('button').click();
    await new Promise(resolve => setTimeout(resolve, 0));
    assert.equal(originalBody.innerHTML, before, 'Original DOM must stay unchanged');
    const output = container.querySelector('.email-translation-result');
    if (hidden) {
        assert.equal(sent, undefined, 'Declining consent must not send a request');
        assert.equal(output.hidden, true);
    } else if (invalid) {
        assert.equal(output.hidden, true, 'Mismatched segments must not render');
        assert.match(container.querySelector('[role="status"]').textContent, /失败/);
    } else {
        assert.deepEqual(Object.keys(sent).sort(), ['segments', 'subject', 'target_language']);
        const frame = output.querySelector('iframe');
        assert.equal(frame.getAttribute('sandbox'), 'allow-same-origin');
        assert.equal(output.querySelector('h3').textContent, '<img src=x onerror=evil()>');
        assert.equal(output.querySelector('h3 img'), null);
        const parsed = new w.DOMParser().parseFromString(frame.srcdoc, 'text/html');
        assert.equal(parsed.querySelector('script'), null);
        assert.equal(parsed.querySelector('[onclick]'), null);
        assert.match(parsed.querySelector('meta[http-equiv]').content, /script-src 'none'/);
        assert.match(parsed.body.textContent, /<script>literal-0<\/script>/);
        if (html) {
            assert.equal(sent.segments.length, 4);
            assert.equal(parsed.querySelectorAll('td').length, 2);
            assert.equal(parsed.querySelector('table').getAttribute('style'), 'border:1px solid red');
            assert.equal(parsed.querySelector('a').getAttribute('href'), 'https://example.com');
            assert.equal(parsed.querySelector('img').getAttribute('src'), 'https://example.com/logo.png');
            assert.match(parsed.querySelector('style').textContent, /td\{padding:12px\}/);
            assert.match(parsed.querySelector('td').firstChild.data, /^ /);
            assert.equal(sent.segments.some(s => /evil|Hidden/.test(s.text)), false);
        } else {
            assert.equal(sent.segments.length, 1);
            assert.match(sent.segments[0].text, /Hello\nWorld <b>literal<\/b>/);
            assert.equal(parsed.querySelector('.email-body-text').style.whiteSpace, 'pre-wrap');
            assert.equal(parsed.querySelector('.email-body-text').style.lineHeight, '1.7');
        }
    }
    dom.window.close();
}
(async () => {
    await runCase(true);
    await runCase(false);
    await runCase(true, true);
    await runCase(true, false, true);
    console.log('4 DOM translation regression cases passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
