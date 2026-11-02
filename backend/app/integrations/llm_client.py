import json
from pathlib import Path

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.integrations.ai_diff import redact
from app.modules.ai_reviews.schemas import LlmReview

# Trần output theo từng prompt; prompt cũ giữ nguyên trần cho vòng đã chốt.
# v2 tự giới hạn độ dài nên trần rộng hơn nhiều để còn chỗ cho token suy luận, tránh cắt giữa JSON.
MAX_OUTPUT_TOKENS = {"code-review-v1": 2048, "code-review-v2": 8192}


class LlmError(Exception):
    def __init__(self, code: str, usage: int | None = None) -> None:
        self.code = code
        self.usage = usage
        super().__init__(code)


def request_body(model: str, prompt_version: str, data: dict) -> dict:
    if prompt_version not in MAX_OUTPUT_TOKENS:
        raise LlmError("AI_PROVIDER_REJECTED")
    prompt = (Path(__file__).parent / "prompts" / f"{prompt_version}.txt").read_text("utf-8")
    schema = LlmReview.model_json_schema()

    def supported(node: object) -> None:
        if isinstance(node, dict):
            for key in ("minimum", "maximum", "minLength", "maxLength", "maxItems", "minItems"):
                node.pop(key, None)
            for value in node.values():
                supported(value)
        elif isinstance(node, list):
            for value in node:
                supported(value)

    supported(schema)
    return {
        "model": model,
        "max_completion_tokens": MAX_OUTPUT_TOKENS[prompt_version],
        "store": False,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "code_review", "strict": True, "schema": schema},
        },
    }


def reservation(body: dict) -> int:
    # Bound bảo thủ không cần tokenizer: mỗi byte input có thể thành một token.
    return (
        len(json.dumps(body, ensure_ascii=False).encode("utf-8"))
        + 1024
        + body["max_completion_tokens"]
    )


class LlmClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise LlmError("AI_NOT_CONFIGURED")
        self.client = httpx.Client(
            base_url="https://api.openai.com/v1",
            timeout=90,
            follow_redirects=False,
            headers={"Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}"},
        )

    def close(self) -> None:
        self.client.close()

    def review(self, body: dict) -> tuple[LlmReview, int | None]:
        try:
            response = self.client.post("/chat/completions", json=body)
        except httpx.TimeoutException:
            raise LlmError("AI_PROVIDER_TIMEOUT") from None
        except httpx.HTTPError:
            raise LlmError("AI_PROVIDER_UNAVAILABLE") from None
        if response.status_code == 429:
            raise LlmError("AI_RATE_LIMITED", 0)
        if response.status_code >= 500:
            raise LlmError("AI_PROVIDER_UNAVAILABLE")
        if response.status_code != 200:
            raise LlmError("AI_PROVIDER_REJECTED", 0)
        usage = None
        try:
            data = response.json()
            count = data.get("usage", {}).get("total_tokens")
            if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
                usage = count
            choice = data["choices"][0]
            if choice["message"].get("refusal"):
                raise LlmError("AI_PROVIDER_REJECTED", usage)
            # Chạm trần output: gửi lại cùng diff sẽ bị cắt tiếp, nên mã riêng, không tự retry
            if choice.get("finish_reason") == "length":
                raise LlmError("AI_OUTPUT_TRUNCATED", usage)
            if choice.get("finish_reason") != "stop":
                raise LlmError("AI_SCHEMA_INVALID", usage)
            result = LlmReview.model_validate_json(choice["message"]["content"])
            # Lọc cả output vì model có thể nhắc lại credential từ dữ liệu đầu vào.
            safe = result.model_dump()
            safe["summary"] = redact(safe["summary"])
            safe["issues"] = [
                {k: redact(v) if isinstance(v, str) else v for k, v in issue.items()}
                for issue in safe["issues"]
            ]
            result = LlmReview.model_validate(safe)
            return result, usage
        except (ValueError, KeyError, TypeError, IndexError, ValidationError):
            raise LlmError("AI_SCHEMA_INVALID", usage) from None
