"""Tests for turning Open WebUI messages into a Responses API payload."""

from open_webui.routers.openai import _normalize_stored_item, convert_to_responses_payload
from open_webui.utils.tool_loop import responses_replay_items


def _stored_reasoning():
    return {
        'type': 'reasoning',
        'id': 'rs_1',
        'summary': [{'type': 'summary_text', 'text': '**Plan**'}],
        'encrypted_content': 'enc',
        'content': [],
        'status': 'completed',
        'duration': 4,
        'started_at': 1.0,
    }


class TestNormalizeStoredItem:
    def test_reasoning_keeps_only_fields_the_api_accepts(self):
        assert _normalize_stored_item(_stored_reasoning()) == {
            'type': 'reasoning',
            'id': 'rs_1',
            'summary': [{'type': 'summary_text', 'text': '**Plan**'}],
            'encrypted_content': 'enc',
        }

    def test_function_call_keeps_its_id(self):
        item = {'type': 'function_call', 'id': 'fc_1', 'call_id': 'c1', 'name': 't', 'arguments': '{}', 'status': 'x'}
        assert _normalize_stored_item(item) == {
            'type': 'function_call',
            'id': 'fc_1',
            'call_id': 'c1',
            'name': 't',
            'arguments': '{}',
        }

    def test_message_drops_id_and_status(self):
        item = {'type': 'message', 'id': 'msg_1', 'status': 'completed', 'role': 'assistant', 'content': []}
        assert _normalize_stored_item(item) == {'type': 'message', 'role': 'assistant', 'content': []}

    def test_unknown_type_passes_through(self):
        item = {'type': 'web_search_call', 'id': 'ws_1', 'status': 'completed'}
        assert _normalize_stored_item(item) == item


class TestConvertToResponsesPayload:
    def test_assistant_output_is_replayed_as_items(self):
        output = [
            _stored_reasoning(),
            {'type': 'function_call', 'id': 'fc_1', 'call_id': 'c1', 'name': 't', 'arguments': '{}'},
            {'type': 'function_call_output', 'call_id': 'c1', 'output': [{'type': 'input_text', 'text': '[]'}]},
        ]
        payload = convert_to_responses_payload(
            {
                'model': 'gpt-6-luna',
                'messages': [
                    {'role': 'system', 'content': 'Bạn là trợ lý NBC'},
                    {'role': 'user', 'content': 'Doanh thu lũy kế?'},
                    {'role': 'assistant', 'content': '', 'output': output},
                ],
            }
        )
        assert payload['instructions'] == 'Bạn là trợ lý NBC'
        assert [item['type'] for item in payload['input']] == [
            'message',
            'reasoning',
            'function_call',
            'function_call_output',
        ]
        assert payload['input'][1] == _normalize_stored_item(_stored_reasoning())
        assert payload['input'][2]['id'] == 'fc_1'

    def test_chat_completions_tool_messages_still_convert(self):
        payload = convert_to_responses_payload(
            {
                'model': 'm',
                'messages': [
                    {
                        'role': 'assistant',
                        'content': '',
                        'tool_calls': [{'id': 'c1', 'function': {'name': 't', 'arguments': '{"a": 1}'}}],
                    },
                    {'role': 'tool', 'tool_call_id': 'c1', 'content': 'kết quả'},
                ],
                'max_tokens': 100,
            }
        )
        assert payload['input'] == [
            {'type': 'function_call', 'call_id': 'c1', 'name': 't', 'arguments': '{"a": 1}'},
            {'type': 'function_call_output', 'call_id': 'c1', 'output': 'kết quả'},
        ]
        assert payload['max_output_tokens'] == 100
        assert 'max_tokens' not in payload

    def test_replay_round_trip_never_sends_call_id_without_its_reasoning(self):
        output = [
            {'type': 'reasoning', 'id': 'rs_local', 'summary': [], 'duration': 2},
            {'type': 'function_call', 'id': 'fc_1', 'call_id': 'c1', 'name': 't', 'arguments': '{}'},
            {'type': 'function_call_output', 'call_id': 'c1', 'output': [{'type': 'input_text', 'text': '[]'}]},
            _stored_reasoning(),
            {'type': 'function_call', 'id': 'fc_2', 'call_id': 'c2', 'name': 't', 'arguments': '{}'},
        ]
        payload = convert_to_responses_payload(
            {
                'model': 'm',
                'messages': [{'role': 'assistant', 'content': '', 'output': responses_replay_items(output)}],
            }
        )
        items = payload['input']
        for index, item in enumerate(items):
            if item['type'] == 'function_call' and 'id' in item:
                assert items[index - 1]['type'] == 'reasoning', item
        assert [item.get('id') for item in items if item['type'] == 'function_call'] == [None, 'fc_2']
