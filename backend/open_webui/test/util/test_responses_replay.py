"""Tests for replaying reasoning items between tool-call rounds (Responses API)."""

import asyncio
import copy
from types import SimpleNamespace

import pytest

from open_webui.utils.middleware import handle_responses_streaming_event
from open_webui.utils.tool_loop import responses_replay_items, uses_responses_api


def _reasoning(item_id='rs_1', encrypted='enc', **extra):
    item = {'type': 'reasoning', 'id': item_id, 'summary': [], **extra}
    if encrypted is not None:
        item['encrypted_content'] = encrypted
    return item


def _call(call_id, item_id=None):
    item = {'type': 'function_call', 'call_id': call_id, 'name': 'execute_sql', 'arguments': '{}'}
    if item_id:
        item['id'] = item_id
    return item


def _call_output(call_id):
    return {'type': 'function_call_output', 'call_id': call_id, 'output': [{'type': 'input_text', 'text': 'ok'}]}


def _message(text):
    return {'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': text}]}


class TestResponsesReplayItems:
    def test_keeps_provider_reasoning_with_calls_in_order(self):
        output = [_reasoning('rs_1'), _call('c1', 'fc_1'), _call_output('c1'), _reasoning('rs_2'), _message('xong')]
        assert responses_replay_items(output) == output

    def test_reasoning_without_encrypted_content_is_dropped_with_following_call_ids(self):
        output = [
            _reasoning('rs_local', encrypted=None, duration=3),
            _call('c1', 'fc_1'),
            _call('c2', 'fc_2'),
            _call_output('c1'),
            _call_output('c2'),
        ]
        items = responses_replay_items(output)
        assert [item['type'] for item in items] == [
            'function_call',
            'function_call',
            'function_call_output',
            'function_call_output',
        ]
        assert all('id' not in item for item in items if item['type'] == 'function_call')

    def test_call_after_tool_output_keeps_its_id(self):
        output = [_reasoning('rs_local', encrypted=None), _call('c1', 'fc_1'), _call_output('c1'), _call('c2', 'fc_2')]
        items = responses_replay_items(output)
        assert items[-1] == _call('c2', 'fc_2')

    def test_reasoning_without_id_is_dropped(self):
        output = [_reasoning(item_id=None), _call('c1', 'fc_1')]
        assert responses_replay_items(output) == [_call('c1')]

    def test_drops_empty_messages_and_unknown_items(self):
        output = [
            _message(''),
            _message('   '),
            {'type': 'message', 'content': ['not a dict']},
            {'type': 'open_webui:code_interpreter', 'code': 'print(1)'},
            {'type': 'web_search_call', 'id': 'ws_1'},
            _message('Doanh thu 3,02 nghìn tỷ'),
        ]
        assert responses_replay_items(output) == [_message('Doanh thu 3,02 nghìn tỷ')]

    def test_does_not_mutate_input(self):
        output = [_reasoning('rs_local', encrypted=None), _call('c1', 'fc_1')]
        snapshot = copy.deepcopy(output)
        responses_replay_items(output)
        assert output == snapshot


def _request(openai_models):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(OPENAI_MODELS=openai_models)))


@pytest.fixture
def connection(monkeypatch):
    """Patch the lazily imported get_openai_connection; returns the dict of api configs by urlIdx."""
    import open_webui.routers.openai as openai_router

    configs = {0: {'api_type': 'responses'}, 1: {}}

    async def fake_get_openai_connection(idx):
        return 'http://litellm', 'key', configs[idx]

    monkeypatch.setattr(openai_router, 'get_openai_connection', fake_get_openai_connection)
    return configs


class TestUsesResponsesApi:
    def test_base_model_on_responses_connection(self, connection):
        request = _request({'gpt-6-luna': {'urlIdx': 0}})
        assert asyncio.run(uses_responses_api(request, {'id': 'gpt-6-luna'})) is True

    def test_custom_model_uses_its_base_model_connection(self, connection):
        request = _request({'gpt-6-luna': {'urlIdx': 0}})
        model = {'id': 'nbc', 'info': {'base_model_id': 'gpt-6-luna'}}
        assert asyncio.run(uses_responses_api(request, model)) is True

    def test_chat_completions_connection(self, connection):
        request = _request({'other': {'urlIdx': 1}})
        assert asyncio.run(uses_responses_api(request, {'id': 'other'})) is False

    @pytest.mark.parametrize('openai_models', [{}, None, {'gpt-6-luna': {}}])
    def test_unknown_model_or_missing_url_index(self, connection, openai_models):
        request = _request(openai_models)
        assert asyncio.run(uses_responses_api(request, {'id': 'gpt-6-luna'})) is False

    def test_lookup_error_falls_back_to_false(self, monkeypatch):
        import open_webui.routers.openai as openai_router

        async def broken(idx):
            raise IndexError(idx)

        monkeypatch.setattr(openai_router, 'get_openai_connection', broken)
        request = _request({'gpt-6-luna': {'urlIdx': 9}})
        assert asyncio.run(uses_responses_api(request, {'id': 'gpt-6-luna'})) is False


class TestResponsesStreamingEvents:
    def test_completed_keeps_encrypted_reasoning(self):
        final = [{'type': 'reasoning', 'id': 'rs_1', 'encrypted_content': 'enc', 'status': 'in_progress'}]
        output, metadata = handle_responses_streaming_event(
            {'type': 'response.completed', 'response': {'id': 'resp_1', 'output': final, 'usage': {'input_tokens': 1}}},
            [],
        )
        assert output[0]['encrypted_content'] == 'enc'
        assert output[0]['status'] == 'completed'
        assert metadata['done'] is True
        assert metadata['usage'] == {'input_tokens': 1}

    def test_output_item_added_appends_without_mutating(self):
        current = [{'type': 'reasoning', 'id': 'rs_1'}]
        added = {'type': 'function_call', 'id': 'fc_1', 'call_id': 'c1'}
        output, _ = handle_responses_streaming_event({'type': 'response.output_item.added', 'item': added}, current)
        assert output == [current[0], added]
        assert current == [{'type': 'reasoning', 'id': 'rs_1'}]

    def test_items_are_finalised_by_completed_not_output_item_done(self):
        # Upstream: nhánh chung '.done' đứng trước 'response.output_item.done' nên item chỉ được
        # chốt ở response.completed. Test này giữ giả định đó; upstream sửa thì cập nhật lại.
        current = [{'type': 'function_call', 'id': 'fc_1'}]
        done_item = {'type': 'function_call', 'id': 'fc_1', 'arguments': '{"sql": "SELECT 1"}'}
        output, _ = handle_responses_streaming_event(
            {'type': 'response.output_item.done', 'output_index': 0, 'item': done_item}, current
        )
        assert output == current

    def test_failed_returns_error(self):
        _, metadata = handle_responses_streaming_event(
            {'type': 'response.failed', 'response': {'error': {'message': 'boom'}}}, []
        )
        assert metadata == {'error': {'message': 'boom'}}
