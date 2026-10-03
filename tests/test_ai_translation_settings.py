import json
from unittest.mock import patch

import pytest
import requests
from test_ai_translation import web, ai, FakeResponse, config


@pytest.fixture
def client():
    web.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with web.app.app_context():
        web.init_db()
        db = web.get_db()
        db.execute("DELETE FROM settings WHERE key = 'ai_translation_config'")
        db.commit()
    client = web.app.test_client()
    with client.session_transaction() as session:
        session['logged_in'] = True
    yield client
    with web.app.app_context():
        db = web.get_db()
        db.execute("DELETE FROM settings WHERE key = 'ai_translation_config'")
        db.commit()


def payload(**changes):
    return dict(base_url='https://other.example/v1', model='other-model',
                default_language='ja', timeout_seconds=30, api_key='new-private-key', **changes)


def test_read_env_masked(client):
    response = client.get('/api/settings/ai-translation')
    assert response.json['settings']['source'] == 'environment'
    assert response.json['settings']['api_key_configured'] is True
    assert 'api_key' not in response.json['settings']
    assert 'private-test-key' not in response.text
    assert response.headers['Cache-Control'] == 'no-store'


def test_save_retain_clear_and_priority(client):
    response = client.post('/api/settings/ai-translation', json=payload())
    assert response.status_code == 200
    assert 'new-private-key' not in response.text
    with web.app.app_context():
        raw = web.get_setting('ai_translation_config')
        assert 'new-private-key' not in raw
        assert json.loads(raw)['api_key'].startswith('enc:')
        assert ai.translation_config() == ('https://other.example/v1/chat/completions', 'new-private-key', 'other-model', 30)
    assert 'ai_translation_config' not in client.get('/api/settings').json['settings']
    assert client.post('/api/settings/ai-translation', json={'api_key': '', 'model': 'updated'}).status_code == 200
    with web.app.app_context():
        assert ai.translation_config()[1:3] == ('new-private-key', 'updated')
    assert client.post('/api/settings/ai-translation', json={'clear_api_key': True}).status_code == 200
    assert client.get('/api/settings/ai-translation').json['settings']['api_key_configured'] is False
    with patch.object(ai.requests, 'post') as post:
        response = client.post('/api/email/translate', json={'subject': 'Hi'})
    assert response.status_code == 503
    post.assert_not_called()


@pytest.mark.parametrize('path,method', [('/api/settings/ai-translation', 'get'), ('/api/settings/ai-translation', 'post'), ('/api/settings/ai-translation/test', 'post')])
def test_auth(client, path, method):
    with client.session_transaction() as session:
        session.clear()
    with patch.object(ai.requests, 'post') as provider:
        assert getattr(client, method)(path).status_code == 401
    provider.assert_not_called()


@pytest.mark.parametrize('path', ['/api/settings/ai-translation', '/api/settings/ai-translation/test'])
def test_csrf(client, path):
    web.app.config['WTF_CSRF_ENABLED'] = True
    try:
        with patch.object(ai.requests, 'post') as provider:
            assert client.post(path, json=payload()).status_code == 400
        provider.assert_not_called()
        token = client.get('/api/csrf-token').json['csrf_token']
        with patch.object(ai.requests, 'post', return_value=FakeResponse()):
            assert client.post(path, json=payload(), headers={'X-CSRFToken': token}).status_code == 200
    finally:
        web.app.config['WTF_CSRF_ENABLED'] = False


@pytest.mark.parametrize('field,value', [('base_url', 'ftp://example.com'), ('base_url', 'https://user:secret@example.com'), ('base_url', 'https://example.com?key=secret'), ('model', ''), ('model', 'x'*201), ('api_key', 'secret\nkey'), ('timeout_seconds', 4), ('timeout_seconds', 91), ('timeout_seconds', 'nan'), ('timeout_seconds', True), ('default_language', 'invalid'), ('clear_api_key', 'true'), ('unknown', 'x')])
def test_invalid_does_not_persist(client, field, value):
    data = payload()
    data[field] = value
    response = client.post('/api/settings/ai-translation', json=data)
    assert response.status_code == 400
    assert 'new-private-key' not in response.text
    assert client.get('/api/settings/ai-translation').json['settings']['source'] == 'environment'


def test_clear_conflicts(client):
    data = payload(clear_api_key=True)
    assert client.post('/api/settings/ai-translation', json=data).status_code == 400


def test_default_language_used(client):
    client.post('/api/settings/ai-translation', json=payload())
    with patch.object(ai.requests, 'post', return_value=FakeResponse()) as post:
        result = client.post('/api/email/translate', json={'subject': 'Hi', 'body': 'World'})
    assert result.json['translation']['target_language'] == 'ja'
    assert 'Japanese' in post.call_args.kwargs['json']['messages'][0]['content']


def test_minimal_test_unsaved_and_retains_key(client):
    client.post('/api/settings/ai-translation', json=payload())
    with patch.object(ai.requests, 'post', return_value=FakeResponse()) as post:
        response = client.post('/api/settings/ai-translation/test', json={'model': 'draft', 'api_key': ''})
    assert response.status_code == 200
    args, kwargs = post.call_args
    assert kwargs['json'] == {'model': 'draft', 'max_tokens': 8, 'stream': False, 'messages': [{'role': 'user', 'content': 'Reply OK.'}]}
    assert kwargs['headers']['Authorization'] == 'Bearer new-private-key'
    assert kwargs['allow_redirects'] is False
    assert client.get('/api/settings/ai-translation').json['settings']['model'] == 'other-model'
    assert 'new-private-key' not in response.text


@pytest.mark.parametrize('failure', [requests.Timeout('new-private-key'), requests.ConnectionError('new-private-key')])
def test_test_connection_redacts_exception(client, failure):
    with patch.object(ai.requests, 'post', side_effect=failure):
        response = client.post('/api/settings/ai-translation/test', json=payload())
    assert response.status_code in (502, 504)
    assert 'new-private-key' not in response.text


def test_provider_body_not_returned(client):
    with patch.object(ai.requests, 'post', return_value=FakeResponse(status=401, raw=b'new-private-key')):
        response = client.post('/api/settings/ai-translation/test', json=payload())
    assert response.status_code == 502
    assert 'new-private-key' not in response.text


@pytest.mark.parametrize('data', [None, [], 'key'])
def test_invalid_json(client, data):
    assert client.post('/api/settings/ai-translation', data=json.dumps(data), content_type='application/json').status_code == 400
