"""AI4BI: helper cho vòng công cụ (tool-call loop) của Open WebUI.

Tách khỏi utils/middleware.py để middleware chỉ còn vài dòng gọi (ít xung đột khi nâng upstream)
và để test được mà không phải dựng cả luồng stream. Module không import open_webui ở mức trên cùng.
"""

import logging

log = logging.getLogger(__name__)


async def uses_responses_api(request, model: dict) -> bool:
    """Model có đi qua connection OpenAI kiểu Responses API (api_type='responses') không.

    Tra như routers/openai.py: model tuỳ biến dùng connection của base model.
    """
    try:
        from open_webui.routers.openai import get_openai_connection

        model_id = (model.get('info') or {}).get('base_model_id') or model.get('id')
        openai_model = (request.app.state.OPENAI_MODELS or {}).get(model_id)
        if not openai_model or 'urlIdx' not in openai_model:
            return False
        _, _, api_config = await get_openai_connection(openai_model['urlIdx'])
        return api_config.get('api_type') == 'responses'
    except Exception:
        log.debug('uses_responses_api: không tra được connection, coi như Chat Completions', exc_info=True)
        return False


def responses_replay_items(output: list[dict]) -> list[dict]:
    """Item của lượt hiện tại để gửi lại Responses API ở vòng công cụ sau.

    convert_output_to_messages bỏ reasoning, nên mỗi vòng mô hình mất mạch suy luận và phải
    nghĩ lại từ đầu. Ở đây giữ reasoning có encrypted_content, function_call (kèm id),
    kết quả công cụ và tin nhắn có chữ; bỏ item riêng của Open WebUI. Reasoning do Open WebUI
    tự dựng (không có encrypted_content) thì bỏ, kèm id của function_call ngay sau nó: Azure
    từ chối function_call có id mà thiếu item reasoning sinh ra nó.
    """
    items = []
    dropped_reasoning = False
    for item in output:
        item_type = item.get('type')
        if item_type == 'reasoning':
            if item.get('id') and item.get('encrypted_content'):
                items.append(item)
                dropped_reasoning = False
            else:
                dropped_reasoning = True
        elif item_type == 'function_call':
            items.append({k: v for k, v in item.items() if k != 'id'} if dropped_reasoning else item)
        elif item_type == 'function_call_output':
            items.append(item)
            dropped_reasoning = False
        elif item_type == 'message':
            parts = item.get('content') or []
            if any(isinstance(part, dict) and (part.get('text') or '').strip() for part in parts):
                items.append(item)
    return items


def tool_loop_http_error(iteration: int, response) -> str | None:
    """Lỗi hiện cho người dùng khi vòng công cụ nhận phản hồi không stream có status ≥ 400.

    Trả None nếu không phải lỗi HTTP (vd phản hồi thành công nhưng không stream).
    """
    status = getattr(response, 'status_code', None)
    if not status or status < 400:
        return None
    body = getattr(response, 'body', b'') or b''
    body = body.decode('utf-8', 'replace') if isinstance(body, bytes) else str(body)
    return f'Mô hình trả lỗi ở vòng công cụ thứ {iteration} (HTTP {status}): {body[:500]}'


def tool_loop_exception_error(iteration: int, exc: BaseException) -> str:
    """Lỗi hiện cho người dùng khi gọi mô hình ở một vòng công cụ ném exception (vd stream đứt)."""
    return f'Gọi mô hình ở vòng công cụ thứ {iteration} bị lỗi: {type(exc).__name__}: {exc}'
