from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from worldbuilding_wiki.errors import ValidationError, VaultError


@dataclass(slots=True)
class AISettings:
    mode: str
    endpoint: str
    model: str
    api_key: str

    @classmethod
    def from_environment(cls) -> AISettings:
        mode = os.environ.get("WORLDBUILDING_AI_MODE", "disabled").strip().lower()
        if mode not in {"disabled", "local", "external"}:
            mode = "disabled"
        endpoint = os.environ.get(
            "WORLDBUILDING_AI_ENDPOINT",
            "http://127.0.0.1:11434/api/chat" if mode == "local" else "",
        ).strip()
        return cls(
            mode=mode,
            endpoint=endpoint,
            model=os.environ.get("WORLDBUILDING_AI_MODEL", "").strip(),
            api_key=os.environ.get("WORLDBUILDING_AI_API_KEY", "").strip(),
        )

    def public_info(self) -> dict[str, Any]:
        parsed = urlparse(self.endpoint) if self.endpoint else None
        return {
            "mode": self.mode,
            "enabled": self.mode != "disabled" and bool(self.endpoint and self.model),
            "model": self.model,
            "endpoint_origin": f"{parsed.scheme}://{parsed.netloc}" if parsed else "",
            "has_api_key": bool(self.api_key),
        }


class AIClient:
    def __init__(self, settings: AISettings | None = None):
        self.settings = settings or AISettings.from_environment()

    def generate(self, prompt: str) -> str:
        info = self.settings.public_info()
        if not info["enabled"]:
            raise ValidationError("AI 建议层未启用或缺少模型配置")
        parsed = urlparse(self.settings.endpoint)
        if self.settings.mode == "local" and parsed.hostname not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise ValidationError("本地 AI 端点必须位于回环地址")
        if self.settings.mode == "external" and parsed.scheme != "https":
            raise ValidationError("外部 AI 端点必须使用 HTTPS")
        messages = [
            {
                "role": "system",
                "content": "你是世界观编辑顾问。只给出建议和理由，不声称已经修改任何文件。",
            },
            {"role": "user", "content": prompt},
        ]
        if self.settings.mode == "local":
            payload = {"model": self.settings.model, "messages": messages, "stream": False}
        else:
            payload = {"model": self.settings.model, "messages": messages}
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"
        request = Request(
            self.settings.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=90) as response:  # noqa: S310 - endpoint is user config
                result = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise VaultError(f"AI 服务调用失败：{exc}") from exc
        try:
            return str(
                result["message"]["content"]
                if self.settings.mode == "local"
                else result["choices"][0]["message"]["content"]
            ).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise VaultError("AI 服务返回了无法识别的响应") from exc
