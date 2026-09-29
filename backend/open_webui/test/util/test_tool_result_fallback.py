"""Tests for the tool-result fallback and permission-error detection helpers."""

import json

from open_webui.utils.middleware import (
    build_tool_result_fallback_message,
    extract_tool_error_text,
    is_permission_error,
)


def _result(content):
    return {'tool_call_id': 'call-1', 'content': content if isinstance(content, str) else json.dumps(content)}


class TestBuildToolResultFallbackMessage:
    def test_no_results_gives_no_message(self):
        assert build_tool_result_fallback_message([]) == ''

    def test_rows_returned_gives_no_message(self):
        assert build_tool_result_fallback_message([_result([{'revenue': 10}])]) == ''

    def test_empty_row_set_is_reported(self):
        message = build_tool_result_fallback_message([_result([])])
        assert 'did not receive any matching records' in message

    def test_error_payload_includes_the_detail(self):
        message = build_tool_result_fallback_message([_result({'error': 'table users does not exist'})])
        assert 'table users does not exist' in message

    def test_error_without_detail_still_explains(self):
        message = build_tool_result_fallback_message([_result({'error': True})])
        assert "couldn't get a final result" in message

    def test_non_json_content_is_ignored(self):
        assert build_tool_result_fallback_message([_result('plain text answer')]) == ''


class TestExtractToolErrorText:
    def test_plain_error_string(self):
        assert extract_tool_error_text('Error: Tool "x" not found.').startswith('Error:')

    def test_error_field(self):
        assert extract_tool_error_text(json.dumps({'error': 'permission denied'})) == 'permission denied'

    def test_nested_error_message(self):
        assert extract_tool_error_text({'error': {'message': 'access denied for user'}}) == 'access denied for user'

    def test_mcp_is_error_flag(self):
        assert extract_tool_error_text({'isError': True, 'message': 'forbidden'}) == 'forbidden'

    def test_successful_result_reports_no_error(self):
        assert extract_tool_error_text(json.dumps([{'id': 1}])) == ''

    def test_data_containing_error_words_is_not_an_error(self):
        # A row about a "forbidden" product must not read as a tool failure.
        rows = json.dumps([{'policy': 'forbidden substances', 'status': 'unauthorized access log'}])
        assert extract_tool_error_text(rows) == ''
        assert not is_permission_error(extract_tool_error_text(rows))


class TestIsPermissionError:
    def test_detects_each_keyword(self):
        for text in (
            'permission denied',
            'Access Denied for table sales',
            'HTTP 403 Forbidden',
            'Unauthorized',
            'user is not authorized',
        ):
            assert is_permission_error(text), text

    def test_ignores_unrelated_errors(self):
        assert not is_permission_error('syntax error near SELECT')
        assert not is_permission_error('')
