"""Minimal Telegram Bot API client built on Python's standard library."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class TelegramAPI:
    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}/"

    def call(self, method: str, payload: dict[str, Any] | None = None) -> Any:
        body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.base + method,
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=65) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Telegram connection error: {exc}") from exc
        if not result.get("ok"):
            raise RuntimeError(f"Telegram API error: {result}")
        return result.get("result")

    def get_updates(self, offset: int | None = None) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": 50, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            payload["offset"] = offset
        return self.call("getUpdates", payload)

    def send_message(self, chat_id: int, text: str, keyboard: dict[str, Any] | None = None) -> Any:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if keyboard:
            payload["reply_markup"] = keyboard
        return self.call("sendMessage", payload)

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        self.call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})


def inline_keyboard(rows: list[list[tuple[str, str]]]) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": title, "callback_data": data} for title, data in row]
            for row in rows
        ]
    }

