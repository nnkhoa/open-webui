"""Tests for the user-facing errors raised when a tool-call round fails."""

from types import SimpleNamespace

import pytest

from open_webui.utils.tool_loop import tool_loop_exception_error, tool_loop_http_error


class TestToolLoopHttpError:
    def test_bytes_body(self):
        response = SimpleNamespace(status_code=400, body=b'{"error": "reasoning item missing"}')
        assert tool_loop_http_error(3, response) == (
            'Mô hình trả lỗi ở vòng công cụ thứ 3 (HTTP 400): {"error": "reasoning item missing"}'
        )

    def test_str_body(self):
        response = SimpleNamespace(status_code=502, body='Bad Gateway')
        assert tool_loop_http_error(1, response).endswith('(HTTP 502): Bad Gateway')

    def test_body_is_truncated(self):
        response = SimpleNamespace(status_code=500, body=b'x' * 2000)
        message = tool_loop_http_error(1, response)
        assert message.endswith('x' * 500)
        assert 'x' * 501 not in message

    def test_invalid_utf8_is_replaced(self):
        response = SimpleNamespace(status_code=400, body=b'\xff\xfe loi')
        assert 'loi' in tool_loop_http_error(1, response)

    def test_missing_body(self):
        assert tool_loop_http_error(2, SimpleNamespace(status_code=429)).endswith('(HTTP 429): ')

    @pytest.mark.parametrize('response', [SimpleNamespace(status_code=200, body=b'{}'), SimpleNamespace(), {}])
    def test_not_an_http_error(self, response):
        assert tool_loop_http_error(1, response) is None


def test_exception_error_names_round_and_type():
    error = tool_loop_exception_error(9, ValueError('Got more than 131072 bytes'))
    assert error == 'Gọi mô hình ở vòng công cụ thứ 9 bị lỗi: ValueError: Got more than 131072 bytes'
