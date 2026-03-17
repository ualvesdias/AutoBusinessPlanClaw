from __future__ import annotations

import json
import os
from typing import Any

import requests

from .models import LLMConfig


class LLMError(RuntimeError):
    pass


class OpenAICompatibleClient:
    def __init__(self, config: LLMConfig):
        self.config = config

    def is_configured(self) -> bool:
        return bool(os.getenv(self.config.api_key_env, ""))

    def _api_key(self) -> str:
        key = os.getenv(self.config.api_key_env, "")
        if not key:
            raise LLMError(f"Environment variable {self.config.api_key_env} is not set")
        return key

    def complete(self, system: str, user: str) -> str:
        response = requests.post(
            f"{self.config.base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key()}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.config.model,
                "temperature": self.config.temperature,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=120,
        )
        if response.status_code >= 400:
            raise LLMError(f"LLM request failed ({response.status_code}): {response.text[:500]}")
        payload: dict[str, Any] = response.json()
        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected LLM response: {json.dumps(payload)[:500]}") from exc
