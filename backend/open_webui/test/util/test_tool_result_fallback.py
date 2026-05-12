import html
import json
import unittest


ERROR_PREFIX = 'Mình chưa lấy được kết quả cuối cùng từ công cụ dữ liệu.'
EMPTY_PREFIX = 'Mình đã chạy công cụ dữ liệu nhưng hiện chưa nhận được bản ghi phù hợp để trả lời câu hỏi này.'


def build_tool_result_fallback_message(results: list) -> str:
    had_tool_result_error = False
    had_empty_tool_result = False
    fallback_tool_error_messages = []

    for result in results:
        result_content = result.get('content', '')

        if not isinstance(result_content, str):
            continue

        stripped_result_content = result_content.strip()
        if not stripped_result_content:
            continue

        try:
            parsed_tool_result = json.loads(stripped_result_content)
        except Exception:
            continue

        if isinstance(parsed_tool_result, list) and len(parsed_tool_result) == 0:
            had_empty_tool_result = True
        elif isinstance(parsed_tool_result, dict):
            tool_error_message = parsed_tool_result.get('error') or parsed_tool_result.get('message')
            if parsed_tool_result.get('error'):
                had_tool_result_error = True
            if tool_error_message:
                fallback_tool_error_messages.append(str(tool_error_message))

    if had_tool_result_error:
        unique_messages = []
        for message in fallback_tool_error_messages:
            if message and message not in unique_messages:
                unique_messages.append(message)

        primary_message = unique_messages[0] if unique_messages else ''
        if primary_message:
            return ERROR_PREFIX + f' Chi tiết: {primary_message}'
        return ERROR_PREFIX + ' Vui lòng kiểm tra lại nguồn dữ liệu hoặc thử lại.'

    if had_empty_tool_result:
        return EMPTY_PREFIX

    return ''


def serialize_output(output: list) -> str:
    content = ''
    tool_outputs = {}
    for item in output:
        if item.get('type') == 'function_call_output':
            tool_outputs[item.get('call_id')] = item

    for item in output:
        item_type = item.get('type', '')
        if item_type == 'message':
            for content_part in item.get('content', []):
                if 'text' in content_part:
                    text = content_part.get('text', '').strip()
                    if text:
                        content = f'{content}{text}\n'
        elif item_type == 'function_call':
            call_id = item.get('call_id', '')
            name = item.get('name', '')
            arguments = item.get('arguments', '')
            result_item = tool_outputs.get(call_id)
            if result_item:
                result_text = ''
                for result_output in result_item.get('output', []):
                    if 'text' in result_output:
                        output_text = result_output.get('text', '')
                        result_text += str(output_text) if not isinstance(output_text, str) else output_text
                content += f'<details type="tool_calls" done="true" id="{call_id}" name="{name}" arguments="{html.escape(json.dumps(arguments))}" result="{html.escape(json.dumps(result_text, ensure_ascii=False))}">\n<summary>Tool Executed</summary>\n</details>\n'
            else:
                content += f'<details type="tool_calls" done="false" id="{call_id}" name="{name}" arguments="{html.escape(json.dumps(arguments))}">\n<summary>Executing...</summary>\n</details>\n'
    return content.strip()


class ToolResultFallbackTests(unittest.TestCase):
    def test_error_payload_gets_error_fallback(self):
        message = build_tool_result_fallback_message([
            {"tool_call_id": "a1", "content": '{"error":"DB timeout"}'},
        ])
        self.assertIn(ERROR_PREFIX, message)
        self.assertIn("DB timeout", message)

    def test_empty_array_gets_empty_fallback(self):
        message = build_tool_result_fallback_message([
            {"tool_call_id": "a1", "content": '[]'},
        ])
        self.assertEqual(message, EMPTY_PREFIX)

    def test_error_wins_over_empty_result(self):
        message = build_tool_result_fallback_message([
            {"tool_call_id": "a1", "content": '[]'},
            {"tool_call_id": "a2", "content": '{"error":"backend failed"}'},
        ])
        self.assertIn("backend failed", message)
        self.assertNotIn("bản ghi phù hợp", message)

    def test_plain_text_result_has_no_fallback(self):
        message = build_tool_result_fallback_message([
            {"tool_call_id": "a1", "content": 'normal tool text'},
        ])
        self.assertEqual(message, "")

    def test_message_without_error_stays_non_error(self):
        message = build_tool_result_fallback_message([
            {"tool_call_id": "a1", "content": '{"message":"not an error"}'},
        ])
        self.assertEqual(message, "")

    def test_post_tool_blank_turn_gets_backfilled(self):
        fallback_message = build_tool_result_fallback_message([
            {"tool_call_id": "a1", "content": '[]'}
        ])
        output = [
            {
                'type': 'function_call',
                'id': 'fc_1',
                'call_id': 'a1',
                'name': 'search_data',
                'arguments': '{}',
                'status': 'completed',
            },
            {
                'type': 'function_call_output',
                'id': 'fco_1',
                'call_id': 'a1',
                'output': [{'type': 'input_text', 'text': '[]'}],
                'status': 'completed',
            },
            {
                'type': 'message',
                'id': 'msg_1',
                'status': 'in_progress',
                'role': 'assistant',
                'content': [{'type': 'output_text', 'text': ''}],
            },
        ]

        streamed_response_has_visible_text = False
        for item in output:
            if item.get('type') != 'message':
                continue
            for content_part in item.get('content', []):
                if content_part.get('type') == 'output_text' and content_part.get('text', '').strip():
                    streamed_response_has_visible_text = True
                    break
            if streamed_response_has_visible_text:
                break

        if not streamed_response_has_visible_text and fallback_message:
            output[-1]['status'] = 'completed'
            output[-1]['content'] = [{'type': 'output_text', 'text': fallback_message}]

        html_output = serialize_output(output)
        self.assertIn(EMPTY_PREFIX, html_output)
        self.assertNotIn('Executing...', html_output)

    def test_five_regression_loops_stay_stable(self):
        scenario_results = [
            [{"tool_call_id": "1", "content": '{"error":"x"}'}],
            [{"tool_call_id": "2", "content": '[]'}],
            [
                {"tool_call_id": "3", "content": '[]'},
                {"tool_call_id": "4", "content": '{"error":"y"}'},
            ],
            [{"tool_call_id": "5", "content": 'plain text'}],
            [{"tool_call_id": "6", "content": '{"message":"not an error"}'}],
        ]

        for _ in range(5):
            for results in scenario_results:
                message = build_tool_result_fallback_message(results)
                self.assertIsInstance(message, str)
                self.assertNotIn('Traceback', message)


if __name__ == '__main__':
    unittest.main()
