from outlook_web import ai_translation as ai

from outlook_web.ai_translation import (
    MAX_REQUEST_BYTES, TranslationError, translate_email,
)


@app.route('/api/email/translate', methods=['POST'])
@login_required
def api_translate_email():
    """Translate only explicitly submitted displayed content; never persist it."""
    try:
        if not request.is_json:
            raise TranslationError('INVALID_INPUT', '请提交 JSON 邮件内容', 400)
        if request.content_length is not None and request.content_length > MAX_REQUEST_BYTES:
            raise TranslationError('INPUT_TOO_LONG', '邮件请求过大，请缩短内容后重试', 413)
        raw = request.stream.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            raise TranslationError('INPUT_TOO_LONG', '邮件请求过大，请缩短内容后重试', 413)
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeError):
            raise TranslationError('INVALID_INPUT', '邮件 JSON 格式无效', 400) from None
        response = jsonify({'success': True, 'translation': translate_email(data)})
    except TranslationError as error:
        response = jsonify({'success': False, 'error': {
            'code': error.code, 'message': error.message,
        }})
        response.status_code = error.status
    # Do not expose exception messages, provider response bodies or configuration.
    response.headers['Cache-Control'] = 'no-store'
    return response


def ai_settings_public(config):
    public = {k: v for k, v in config.items() if k != 'api_key'}
    public['api_key_configured'] = bool(config.get('api_key'))
    public['api_key_masked'] = '********' if public['api_key_configured'] else ''
    public['source'] = 'settings' if get_setting('ai_translation_config', '') else 'environment'
    return public


def ai_settings_candidate(data):
    if not isinstance(data, dict) or set(data) - {
        'base_url', 'api_key', 'model', 'default_language', 'timeout_seconds', 'clear_api_key'
    }:
        raise TranslationError('INVALID_INPUT', 'AI 翻译设置格式无效', 400)
    config = ai.effective_settings().copy()
    for key in ('base_url', 'model', 'default_language', 'api_key'):
        if key in data:
            if not isinstance(data[key], str):
                raise TranslationError('INVALID_INPUT', 'AI 翻译设置格式无效', 400)
            value = data[key].strip()
            if key != 'api_key' or value:
                config[key] = value
    if 'clear_api_key' in data and type(data['clear_api_key']) is not bool:
        raise TranslationError('INVALID_INPUT', '清除密钥选项无效', 400)
    if data.get('clear_api_key'):
        if data.get('api_key', '').strip():
            raise TranslationError('INVALID_INPUT', '不能同时设置和清除密钥', 400)
        config['api_key'] = ''
    if 'timeout_seconds' in data:
        if isinstance(data['timeout_seconds'], bool):
            raise TranslationError('INVALID_INPUT', '超时无效', 400)
        config['timeout_seconds'] = data['timeout_seconds']
    # Allow explicitly cleared/unconfigured key while validating all other fields.
    validation = dict(config, api_key=config.get('api_key') or 'validation-placeholder')
    try:
        ai.translation_config(validation)
    except TranslationError:
        raise TranslationError('TRANSLATION_CONFIG_INVALID', '请检查地址、模型、语言及超时（5–90 秒）', 400) from None
    config['timeout_seconds'] = float(config['timeout_seconds'])
    return config


@app.route('/api/settings/ai-translation', methods=['GET', 'POST'])
@login_required
def api_ai_translation_settings():
    try:
        if request.method == 'GET':
            config = ai.effective_settings()
        else:
            config = ai_settings_candidate(request.get_json(silent=True))
            stored = dict(config)
            # encrypt_data treats enc: inputs as already encrypted; user keys must
            # always be encrypted, even when they happen to begin with enc:.
            stored['api_key'] = ('enc:' + get_cipher().encrypt(config['api_key'].encode()).decode()) if config['api_key'] else ''
            if not set_setting('ai_translation_config', json.dumps(stored)):
                raise TranslationError('SETTINGS_SAVE_FAILED', '保存失败，请稍后重试', 500)
        response = jsonify(success=True, settings=ai_settings_public(config))
    except TranslationError as error:
        response = jsonify(success=False, error={'code': error.code, 'message': error.message})
        response.status_code = error.status
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.route('/api/settings/ai-translation/test', methods=['POST'])
@login_required
def api_ai_translation_test():
    try:
        config = ai_settings_candidate(request.get_json(silent=True))
        endpoint, key, model, timeout = ai.translation_config(config)
        if not ai._SLOTS.acquire(blocking=False):
            raise TranslationError('TRANSLATION_BUSY', '服务繁忙，请稍后重试', 429)
        try:
            deadline = time.monotonic() + timeout
            with ai.requests.post(endpoint, headers={'Authorization': 'Bearer ' + key,
                    'Content-Type': 'application/json'}, json={
                    'model': model, 'max_tokens': 8, 'stream': False,
                    'messages': [{'role': 'user', 'content': 'Reply OK.'}]},
                    timeout=(min(5, timeout), timeout), allow_redirects=False, stream=True) as provider:
                if provider.status_code != 200:
                    raise TranslationError('PROVIDER_ERROR', 'AI 服务连接测试失败', 502)
                content = bytearray()
                for chunk in provider.iter_content(chunk_size=1):
                    if time.monotonic() > deadline:
                        raise TranslationError('TRANSLATION_TIMEOUT', '连接测试超时', 504)
                    content.extend(chunk)
                    if len(content) > ai.MAX_RESPONSE_BYTES:
                        raise ValueError()
                result = json.loads(content)
                if not isinstance(result['choices'][0]['message']['content'], str):
                    raise ValueError()
        finally:
            ai._SLOTS.release()
        response = jsonify(success=True, message='连接成功（未发送邮件内容）')
    except ai.requests.Timeout:
        response = jsonify(success=False, error={'code': 'TRANSLATION_TIMEOUT', 'message': '连接测试超时'})
        response.status_code = 504
    except (ai.requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        response = jsonify(success=False, error={'code': 'PROVIDER_ERROR', 'message': 'AI 服务连接测试失败'})
        response.status_code = 502
    except TranslationError as error:
        response = jsonify(success=False, error={'code': error.code, 'message': error.message})
        response.status_code = error.status
    response.headers['Cache-Control'] = 'no-store'
    return response
