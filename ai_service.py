"""Explainable local AI fallback used by the MVP.

The hackathon brief permits a local fallback if the team can show the input,
output and prompt logic. This module never invents facts: it scores only fields
that the user entered and provides deterministic explanations.
"""

from __future__ import annotations

import re
from typing import Any


STOP_WORDS = {
    "для", "или", "как", "что", "это", "при", "нам", "нужен", "нужна",
    "нужно", "проект", "задача", "работа", "система", "создать", "сделать",
    "the", "and", "with", "from", "into", "our", "your",
}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-zа-яё0-9+#.-]{2,}", text.lower())
    return {word for word in words if word not in STOP_WORDS}


def _filled(value: str, minimum: int = 8) -> bool:
    return len(value.strip()) >= minimum


def build_clarifying_questions(description: str) -> list[str]:
    text = description.lower()
    questions: list[str] = []
    if not any(word in text for word in ("пользователь", "клиент", "ученик", "студент", "житель")):
        questions.append("Кто будет основным пользователем результата?")
    if not any(word in text for word in ("данн", "база", "список", "материал", "пример")):
        questions.append("Какие данные, материалы или примеры вы можете предоставить?")
    if not any(word in text for word in ("результат", "прототип", "бот", "сайт", "приложение")):
        questions.append("Какой конкретный результат должна создать команда?")
    if not any(word in text for word in ("процент", "метрик", "измер", "успех", "сократ", "увелич")):
        questions.append("По каким измеримым признакам вы поймёте, что задача решена успешно?")
    if not any(word in text for word in ("срок", "недел", "месяц", "огранич", "технолог")):
        questions.append("Какие есть сроки, технологии или другие ограничения?")
    defaults = [
        "Какие навыки особенно важны для участия в проекте?",
        "Как команда сможет связываться с представителем бизнеса?",
    ]
    for question in defaults:
        if len(questions) >= 3:
            break
        questions.append(question)
    return questions[:5]


def score_task(task: dict[str, Any]) -> tuple[int, str, list[str]]:
    groups = [
        ("Контекст и потребность", 20, [task.get("context", ""), task.get("problem", "")]),
        ("Данные и материалы", 20, [task.get("data", "")]),
        ("Ожидаемый результат", 15, [task.get("expected", "")]),
        ("Критерии успеха", 15, [task.get("success", "")]),
        ("Ограничения", 10, [task.get("constraints", "")]),
        ("Пользователи", 10, [task.get("users", "")]),
        ("Связь с бизнесом", 10, [task.get("contact", "")]),
    ]
    score = 0
    missing: list[str] = []
    for name, weight, values in groups:
        combined = " ".join(values).strip()
        if _filled(combined, 12):
            score += weight
        elif _filled(combined, 3):
            score += weight // 2
            missing.append(f"Дополните раздел «{name}» конкретными деталями.")
        else:
            missing.append(f"Заполните раздел «{name}».")
    if score < 40:
        level = "Черновик"
    elif score < 70:
        level = "Рабочая"
    elif score < 90:
        level = "Готовая"
    else:
        level = "Приоритетная"
    notes = missing or ["Карточка полная: можно публиковать и собирать отклики."]
    return score, level, notes


def match_profile_to_task(profile: dict[str, Any], task: dict[str, Any]) -> tuple[int, list[str]]:
    profile_skills = _tokens(profile.get("skills", "") + " " + profile.get("projects", ""))
    wanted_skills = _tokens(task.get("skills", "") + " " + task.get("constraints", ""))
    interests = _tokens(profile.get("interests", ""))
    task_theme = _tokens(" ".join(str(task.get(key, "")) for key in ("title", "context", "problem", "users")))

    skill_overlap = profile_skills & wanted_skills
    interest_overlap = interests & task_theme
    skill_ratio = len(skill_overlap) / max(1, len(wanted_skills))
    interest_ratio = len(interest_overlap) / max(1, min(5, len(task_theme)))
    has_projects = _filled(profile.get("projects", ""), 12)
    has_portfolio = _filled(profile.get("portfolio", ""), 5)
    available = _filled(profile.get("availability", ""), 3)

    score = round(
        min(1.0, skill_ratio) * 45
        + min(1.0, interest_ratio) * 20
        + (20 if has_projects else 5)
        + (5 if has_portfolio else 0)
        + (10 if available else 0)
    )
    score = max(25, min(98, score))

    reasons: list[str] = []
    if skill_overlap:
        reasons.append("Совпадающие навыки: " + ", ".join(sorted(skill_overlap)[:5]) + ".")
    else:
        reasons.append("Прямые совпадения навыков не найдены — стоит уточнить опыт кандидата.")
    if interest_overlap:
        reasons.append("Задача соответствует интересам кандидата.")
    if has_projects:
        reasons.append("Есть описанный проектный опыт.")
    if available:
        reasons.append("Кандидат указал доступность для участия.")
    if score < 60:
        reasons.append("Перед выбором рекомендуется короткое знакомство и проверка навыков.")
    return score, reasons


def readiness_report(task: dict[str, Any]) -> str:
    score, level, notes = score_task(task)
    return (
        f"📊 Рейтинг готовности: {score}/100 — {level}\n\n"
        + "\n".join(f"• {note}" for note in notes[:4])
    )

