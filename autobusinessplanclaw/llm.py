from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests

from .models import LLMConfig


class LLMError(RuntimeError):
    pass


class OpenAICompatibleClient:
    def __init__(self, config: LLMConfig):
        self.config = config
        self._provider_dead: dict[str, bool] = {
            "openclaw-http": False,
            "openai-compatible": False,
        }

    def is_configured(self) -> bool:
        provider = self.config.provider.lower()
        if provider == "openclaw-http":
            return (not self._provider_dead["openclaw-http"]) and bool(self._openclaw_token())
        if provider == "openai-compatible":
            return (not self._provider_dead["openai-compatible"]) and bool(os.getenv(self.config.api_key_env, ""))
        if provider == "auto":
            return (
                ((not self._provider_dead["openclaw-http"]) and bool(self._openclaw_token()))
                or ((not self._provider_dead["openai-compatible"]) and bool(os.getenv(self.config.api_key_env, "")))
            )
        return False

    def complete(self, system: str, user: str) -> str:
        provider = self.config.provider.lower()
        if provider == "openclaw-http":
            return self._complete_openclaw_http(system, user)
        if provider == "openai-compatible":
            return self._complete_openai_compatible(system, user)
        if provider == "auto":
            openclaw_key = self._openclaw_token()
            if openclaw_key and not self._provider_dead["openclaw-http"]:
                try:
                    return self._complete_openclaw_http(system, user)
                except LLMError:
                    self._provider_dead["openclaw-http"] = True
            api_key = os.getenv(self.config.api_key_env, "")
            if api_key and not self._provider_dead["openai-compatible"]:
                try:
                    return self._complete_openai_compatible(system, user)
                except LLMError:
                    self._provider_dead["openai-compatible"] = True
            raise LLMError("No configured LLM provider succeeded")
        raise LLMError(f"Unsupported provider: {self.config.provider}")

    def _openclaw_token(self) -> str:
        token = os.getenv(self.config.openclaw_api_key_env, "")
        if token:
            return token
        config_path = Path.home() / ".openclaw" / "openclaw.json"
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                return str(((data.get("gateway") or {}).get("auth") or {}).get("token") or "")
            except Exception:
                return ""
        return ""

    def _complete_openai_compatible(self, system: str, user: str) -> str:
        key = os.getenv(self.config.api_key_env, "")
        if not key:
            raise LLMError(f"Environment variable {self.config.api_key_env} is not set")
        try:
            return self._chat_completion(
                base_url=self.config.base_url,
                bearer=key,
                model=self.config.model,
                system=system,
                user=user,
            )
        except LLMError:
            self._provider_dead["openai-compatible"] = True
            raise

    def _complete_openclaw_http(self, system: str, user: str) -> str:
        key = self._openclaw_token()
        if not key:
            raise LLMError(f"No OpenClaw token available via {self.config.openclaw_api_key_env} or ~/.openclaw/openclaw.json")
        try:
            return self._chat_completion(
                base_url=self.config.openclaw_base_url,
                bearer=key,
                model=self.config.openclaw_model,
                system=system,
                user=user,
            )
        except LLMError:
            self._provider_dead["openclaw-http"] = True
            raise

    def _chat_completion(self, base_url: str, bearer: str, model: str, system: str, user: str) -> str:
        timeout = (10, self.config.timeout_seconds)
        try:
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
        except requests.RequestException as exc:
            raise LLMError(f"LLM transport failed for {base_url}: {exc}") from exc
        if response.status_code >= 400:
            raise LLMError(f"LLM request failed ({response.status_code}): {response.text[:500]}")
        payload: dict[str, Any] = response.json()
        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"Unexpected LLM response: {json.dumps(payload)[:500]}") from exc
