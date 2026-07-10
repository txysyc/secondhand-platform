"""DRF 统一异常响应。"""

from rest_framework.views import exception_handler


def _extract_message(data):
    """从 DRF 默认错误结构中提取适合前端直接展示的中文消息。"""

    if isinstance(data, dict):
        detail = data.get("detail")
        if detail:
            return str(detail)

        for value in data.values():
            if isinstance(value, list) and value:
                return str(value[0])
            if value:
                return str(value)

    if isinstance(data, list) and data:
        return str(data[0])

    return "请求处理失败，请稍后重试。"


def api_exception_handler(exc, context):
    """将 DRF 异常稳定包装为 message + errors。"""

    response = exception_handler(exc, context)
    if response is None:
        return response

    if response.status_code == 429:
        message = "请求过于频繁，请稍后再试。"
    else:
        message = _extract_message(response.data)

    response.data = {
        "message": message,
        "errors": response.data,
    }
    return response
