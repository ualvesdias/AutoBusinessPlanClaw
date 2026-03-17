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
        provider = self.config.provider.lower()
        if provider == "openclaw-http":
            return bool(os.getenv(self.config.openclaw_api_key_env, ""))
        if provider == "openai-compatible":
            return bool(os.getenv(self.config.api_key_env, ""))
        if provider == "auto":
            return bool(os.getenv(self.config.api_key_env, "") or os.getenv(self.config.openclaw_api_key_env, ""))
        return False

    def complete(self, system: str, user: str) -> str:
        provider = self.config.provider.lower()
        if provider == "openai-compatible":
            return self._complete_openai_compatible(system, user)
        if provider == "openclaw-http":
            return self._complete_openclaw_http(system, user)
        if provider == "auto":
            api_key = os.getenv(self.config.api_key_env, "")
            if api_key:
                try:
                    return self._complete_openai_compatible(system, user)
                except LLMError:
                    pass
            openclaw_key = os.getenv(self.config.openclaw_api_key_env, "")
            if openclaw_key:
                return self._complete_openclaw_http(system, user)
            raise LLMError("No configured LLM provider succeeded")
        raise LLMError(f"Unsupported provider: {self.config.provider}")

    def _complete_openai_compatible(self, system: str, user: str) -> str:
        key = os.getenv(self.config.api_key_env, "")
        if not key:
            raise LLMError(f"Environment variable {self.config.api_key_env} is not set")
        return self._chat_completion(
            base_url=self.config.base_url,
            bearer=key,
            model=self.config.model,
            system=system,
            user=user,
        )

    def _complete_openclaw_http(self, system: str, user: str) -> str:
        key = os.getenv(self.config.openclaw_api_key_env, "")
        if not key:
            raise LLMError(f"Environment variable {self.config.openclaw_api_key_env} is not set")
        return self._chat_completion(
            base_url=self.config.openclaw_base_url,
            bearer=key,
            model=self.config.openclaw_model,
            system=system,
            user=user,
        )

    def _chat_completion(self, base_url: str, bearer: str, model: str, system: str, user: str) -> str:
        timeout = (10, self.config.timeout_seconds)
        response = requests.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {bearer}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "temperature": self.config.temperature,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=timeout,
        )
        if response.status_code >= 400:
            raise LLMError(f"LLM request failed ({response.status_code}): {response.text[:500]}")
        payload: dict[str, Any] = response.json()
        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected LLM response: {json.dumps(payload)[:500]}") from exc
