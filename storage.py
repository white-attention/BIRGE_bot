"""JSON persistence for the hackathon MVP."""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any


EMPTY_DATA: dict[str, Any] = {
    "users": {},
    "profiles": {},
    "tasks": {},
    "proposals": {},
    "counters": {"task": 0, "proposal": 0},
}


class Storage:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write(deepcopy(EMPTY_DATA))

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            data = deepcopy(EMPTY_DATA)
        for key, value in EMPTY_DATA.items():
            data.setdefault(key, deepcopy(value))
        return data

    def _write(self, data: dict[str, Any]) -> None:
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def get_user(self, user_id: int) -> dict[str, Any]:
        with self.lock:
            return self._read()["users"].get(str(user_id), {})

    def update_user(self, user_id: int, **values: Any) -> dict[str, Any]:
        with self.lock:
            data = self._read()
            user = data["users"].setdefault(str(user_id), {})
            user.update(values)
            self._write(data)
            return deepcopy(user)

    def set_profile(self, user_id: int, profile: dict[str, Any]) -> None:
        with self.lock:
            data = self._read()
            data["profiles"][str(user_id)] = profile
            self._write(data)

    def get_profile(self, user_id: int) -> dict[str, Any] | None:
        with self.lock:
            return self._read()["profiles"].get(str(user_id))

    def create_task(self, owner_id: int, task: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            data = self._read()
            data["counters"]["task"] += 1
            task_id = str(data["counters"]["task"])
            item = {"id": task_id, "owner_id": owner_id, "status": "published", **task}
            data["tasks"][task_id] = item
            self._write(data)
            return deepcopy(item)

    def list_tasks(self, owner_id: int | None = None) -> list[dict[str, Any]]:
        with self.lock:
            tasks = list(self._read()["tasks"].values())
        if owner_id is not None:
            tasks = [task for task in tasks if task["owner_id"] == owner_id]
        return sorted(tasks, key=lambda item: (-item.get("readiness_score", 0), int(item["id"])))

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self.lock:
            return self._read()["tasks"].get(str(task_id))

    def create_proposal(self, task_id: str, graduate_id: int, proposal: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            data = self._read()
            for existing in data["proposals"].values():
                if existing["task_id"] == str(task_id) and existing["graduate_id"] == graduate_id:
                    return deepcopy(existing)
            data["counters"]["proposal"] += 1
            proposal_id = str(data["counters"]["proposal"])
            item = {
                "id": proposal_id,
                "task_id": str(task_id),
                "graduate_id": graduate_id,
                "status": "pending",
                **proposal,
            }
            data["proposals"][proposal_id] = item
            self._write(data)
            return deepcopy(item)

    def list_proposals(self, task_id: str | None = None, graduate_id: int | None = None) -> list[dict[str, Any]]:
        with self.lock:
            proposals = list(self._read()["proposals"].values())
        if task_id is not None:
            proposals = [item for item in proposals if item["task_id"] == str(task_id)]
        if graduate_id is not None:
            proposals = [item for item in proposals if item["graduate_id"] == graduate_id]
        return proposals

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        with self.lock:
            return self._read()["proposals"].get(str(proposal_id))

    def set_proposal_status(self, proposal_id: str, status: str) -> dict[str, Any] | None:
        with self.lock:
            data = self._read()
            item = data["proposals"].get(str(proposal_id))
            if not item:
                return None
            item["status"] = status
            self._write(data)
            return deepcopy(item)

    def seed_demo(self) -> None:
        with self.lock:
            data = self._read()
            if data["tasks"]:
                return
            examples = [
                {
                    "id": "1",
                    "owner_id": 0,
                    "status": "published",
                    "company": "Qadam Education",
                    "title": "Telegram-бот для выбора образовательной программы",
                    "context": "Абитуриенты задают одинаковые вопросы менеджерам и долго ждут ответа.",
                    "problem": "Нужно автоматизировать первичную консультацию абитуриентов.",
                    "users": "Школьники 9–11 классов и их родители",
                    "data": "FAQ из 120 вопросов и описания 18 программ",
                    "expected": "Работающий прототип Telegram-бота с поиском по FAQ",
                    "success": "Бот корректно отвечает минимум на 80% тестовых вопросов",
                    "constraints": "Python, Telegram, срок 2 недели",
                    "contact": "Одна онлайн-консультация с представителем бизнеса в неделю",
                    "skills": "Python, Telegram Bot API, работа с текстом",
                    "readiness_score": 94,
                    "readiness_level": "Приоритетная",
                    "readiness_notes": ["Карточка содержит измеримый результат и доступные данные."],
                },
                {
                    "id": "2",
                    "owner_id": 0,
                    "status": "published",
                    "company": "EcoStep",
                    "title": "Карта пунктов приёма вторсырья",
                    "context": "Жители города не знают, куда сдавать разные виды отходов.",
                    "problem": "Информация разбросана по социальным сетям и быстро устаревает.",
                    "users": "Жители Астаны",
                    "data": "Черновой список из 70 пунктов с адресами",
                    "expected": "Интерактивная веб-карта с фильтрами по типу отходов",
                    "success": "Пользователь находит подходящий пункт не более чем за 30 секунд",
                    "constraints": "Веб-приложение, открытые карты, срок 3 недели",
                    "contact": "Чат с куратором проекта",
                    "skills": "JavaScript, карты, UX/UI",
                    "readiness_score": 88,
                    "readiness_level": "Готовая",
                    "readiness_notes": ["Нужно уточнить порядок обновления адресов."],
                },
            ]
            data["tasks"] = {item["id"]: item for item in examples}
            data["counters"]["task"] = 2
            self._write(data)

