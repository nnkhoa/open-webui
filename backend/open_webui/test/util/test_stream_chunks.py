"""Tests for SSE line splitting of long upstream lines and output-to-message conversion.

Responses API sends the whole response in one `response.completed` SSE line; at high reasoning
effort it exceeds aiohttp's 128 KB readline limit (LineTooLong). With
CHAT_STREAM_RESPONSE_CHUNK_MAX_BUFFER_SIZE set, stream_chunks_handler splits lines itself.
"""

import asyncio
import json

from open_webui.utils import misc


class FakeStream:
    def __init__(self, chunks):
        self.chunks = chunks

    async def iter_chunks(self):
        for chunk in self.chunks:
            yield chunk, False


def _collect(stream):
    async def run():
        return [line async for line in stream]

    return asyncio.run(run())


def _split(data: bytes, size: int) -> list[bytes]:
    return [data[i : i + size] for i in range(0, len(data), size)]


def test_without_limit_returns_original_stream(monkeypatch):
    monkeypatch.setattr(misc, 'CHAT_STREAM_RESPONSE_CHUNK_MAX_BUFFER_SIZE', None)
    stream = FakeStream([])
    assert misc.stream_chunks_handler(stream) is stream


def test_long_completed_line_passes_intact(monkeypatch):
    monkeypatch.setattr(misc, 'CHAT_STREAM_RESPONSE_CHUNK_MAX_BUFFER_SIZE', 32 * 1024 * 1024)
    event = {
        'type': 'response.completed',
        'response': {'output': [{'type': 'reasoning', 'encrypted_content': 'x' * 200_000}]},
    }
    line = b'data: ' + json.dumps(event).encode() + b'\n'
    assert len(line) > 128 * 1024

    lines = _collect(misc.stream_chunks_handler(FakeStream(_split(line, 64 * 1024))))

    assert lines == [line]
    assert json.loads(lines[0][len(b'data: ') :]) == event


def test_several_lines_in_one_chunk_and_trailing_fragment(monkeypatch):
    monkeypatch.setattr(misc, 'CHAT_STREAM_RESPONSE_CHUNK_MAX_BUFFER_SIZE', 1024)
    stream = FakeStream([b'data: 1\n\ndata: 2\n', b'data: 3'])
    assert _collect(misc.stream_chunks_handler(stream)) == [b'data: 1\n', b'\n', b'data: 2\n', b'data: 3\n']


def test_oversized_line_is_replaced_then_stream_recovers(monkeypatch):
    monkeypatch.setattr(misc, 'CHAT_STREAM_RESPONSE_CHUNK_MAX_BUFFER_SIZE', 1000)
    stream = FakeStream([b'data: ' + b'x' * 5000 + b'\ndata: ok\n'])
    lines = _collect(misc.stream_chunks_handler(stream))
    assert lines[0] == b'data: {}\n'
    assert lines[1].rstrip(b'\n') == b'data: ok'


def test_convert_output_to_messages_drops_reasoning_by_default():
    output = [
        {'type': 'reasoning', 'id': 'rs_1', 'summary': [{'type': 'summary_text', 'text': 'nghĩ'}]},
        {'type': 'function_call', 'call_id': 'c1', 'name': 'execute_sql', 'arguments': '{"sql": "SELECT 1"}'},
        {'type': 'function_call_output', 'call_id': 'c1', 'output': [{'type': 'input_text', 'text': '[1]'}]},
        {'type': 'message', 'content': [{'type': 'output_text', 'text': 'Xong'}]},
    ]
    messages = misc.convert_output_to_messages(output, raw=True)
    assert messages[0]['role'] == 'assistant'
    assert messages[0]['tool_calls'][0]['id'] == 'c1'
    assert 'reasoning_content' not in messages[0]
    assert messages[1] == {'role': 'tool', 'tool_call_id': 'c1', 'content': '[1]'}
    assert messages[-1]['content'] == 'Xong'
