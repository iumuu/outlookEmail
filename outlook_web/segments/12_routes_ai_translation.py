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
