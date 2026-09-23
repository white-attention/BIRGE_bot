"""BIRGE Telegram bot: business tasks meet talented graduates."""

from __future__ import annotations

import html
import logging
import sys
import time
from typing import Any

from ai_service import build_clarifying_questions, match_profile_to_task, readiness_report, score_task
from config import BOT_TOKEN, DATA_FILE
from storage import Storage
from telegram_api import TelegramAPI, inline_keyboard


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("birge")
storage = Storage(DATA_FILE)


TASK_FIELDS = [
    ("company", "Как называется компания или организация?"),
    ("title", "Дайте задаче короткое понятное название."),
    ("context", "Что происходит сейчас? Опишите контекст."),
    ("problem", "Какую конкретную проблему нужно решить?"),
    ("users", "Кто будет пользоваться результатом?"),
    ("data", "Какие данные, материалы или примеры вы предоставите?"),
    ("expected", "Какой конкретный результат должна создать команда?"),
    ("success", "Как измерить успешность результата?"),
    ("constraints", "Какие есть сроки, технологии и ограничения?"),
    ("contact", "Как участники смогут консультироваться с бизнесом?"),
    ("skills", "Какие навыки особенно полезны для этой задачи?"),
]

PROFILE_FIELDS = [
    ("name", "Как вас зовут?"),
    ("city", "Из какого вы города?"),
    ("skills", "Перечислите ваши навыки через запятую."),
    ("interests", "Какие направления и проблемы вам интересны?"),
    ("projects", "Кратко опишите достижения или проекты."),
    ("availability", "Сколько времени вы готовы уделять проекту?"),
    ("portfolio", "Отправьте ссылку на портфолио или напишите «нет»."),
]


def e(value: Any) -> str:
    return html.escape(str(value or "—"))


def main_menu(role: str | None) -> dict[str, Any]:
    if role == "business":
        return inline_keyboard([
            [("➕ Создать задачу", "business:create")],
            [("📋 Мои задачи и отклики", "business:tasks")],
            [("🔄 Сменить роль", "role:choose")],
        ])
    if role == "graduate":
        return inline_keyboard([
            [("🔥 Смотреть задачи", "graduate:browse")],
            [("👤 Мой профиль", "graduate:profile"), ("📨 Мои отклики", "graduate:proposals")],
            [("🔄 Сменить роль", "role:choose")],
        ])
    return inline_keyboard([
        [("🏢 Я представляю бизнес", "role:business")],
        [("🎓 Я выпускник", "role:graduate")],
    ])


def role_title(role: str | None) -> str:
    return "бизнес" if role == "business" else "выпускник" if role == "graduate" else "не выбрана"


def send_home(api: TelegramAPI, chat_id: int, user_id: int) -> None:
    user = storage.get_user(user_id)
    role = user.get("role")
    text = (
        "<b>BIRGE</b> — таланты находят реальные задачи 🇰🇿\n\n"
        f"Ваша роль: <b>{role_title(role)}</b>.\n"
        "Выберите действие:"
    )
    api.send_message(chat_id, text, main_menu(role))


def task_card(task: dict[str, Any], include_full: bool = False) -> str:
    base = (
        f"<b>{e(task.get('title'))}</b>\n"
        f"🏢 {e(task.get('company'))}\n"
        f"📊 Готовность: <b>{task.get('readiness_score', 0)}/100</b> — {e(task.get('readiness_level'))}\n\n"
        f"<b>Проблема:</b> {e(task.get('problem'))}\n"
        f"<b>Результат:</b> {e(task.get('expected'))}\n"
        f"<b>Навыки:</b> {e(task.get('skills'))}\n"
        f"<b>Ограничения:</b> {e(task.get('constraints'))}"
    )
    if include_full:
        base += (
            f"\n\n<b>Контекст:</b> {e(task.get('context'))}"
            f"\n<b>Пользователи:</b> {e(task.get('users'))}"
            f"\n<b>Данные:</b> {e(task.get('data'))}"
            f"\n<b>Критерии успеха:</b> {e(task.get('success'))}"
            f"\n<b>Связь с бизнесом:</b> {e(task.get('contact'))}"
        )
    return base


def profile_card(profile: dict[str, Any]) -> str:
    return (
        f"<b>{e(profile.get('name'))}</b>, {e(profile.get('city'))}\n\n"
        f"🛠 <b>Навыки:</b> {e(profile.get('skills'))}\n"
        f"💡 <b>Интересы:</b> {e(profile.get('interests'))}\n"
        f"🏆 <b>Проекты:</b> {e(profile.get('projects'))}\n"
        f"⏱ <b>Доступность:</b> {e(profile.get('availability'))}\n"
        f"🔗 <b>Портфолио:</b> {e(profile.get('portfolio'))}"
    )


def begin_task(api: TelegramAPI, chat_id: int, user_id: int) -> None:
    storage.update_user(user_id, state="task_raw", draft={})
    api.send_message(
        chat_id,
        "Опишите задачу своими словами — даже одного предложения достаточно. "
        "AI найдёт пробелы и поможет превратить черновик в качественную карточку.",
    )


def begin_profile(api: TelegramAPI, chat_id: int, user_id: int) -> None:
    storage.update_user(user_id, state="profile_field", field_index=0, draft={})
    api.send_message(chat_id, "Создадим профиль выпускника.\n\n" + PROFILE_FIELDS[0][1])


def finish_task(api: TelegramAPI, chat_id: int, user_id: int, draft: dict[str, Any]) -> None:
    score, level, notes = score_task(draft)
    draft["readiness_score"] = score
    draft["readiness_level"] = level
    draft["readiness_notes"] = notes
    storage.update_user(user_id, state="task_preview", draft=draft)
    api.send_message(
        chat_id,
        task_card(draft, include_full=True) + "\n\n" + readiness_report(draft),
        inline_keyboard([
            [("✅ Опубликовать", "task:publish")],
            [("✏️ Редактировать поле", "task:editmenu")],
            [("🔄 Заполнить заново", "business:create"), ("❌ Отмена", "menu")],
        ]),
    )


def show_next_task(api: TelegramAPI, chat_id: int, user_id: int, after_id: str | None = None) -> None:
    profile = storage.get_profile(user_id)
    if not profile:
        api.send_message(
            chat_id,
            "Сначала заполните профиль — тогда AI сможет объяснить совместимость с задачами.",
            inline_keyboard([[("👤 Создать профиль", "graduate:profile")], [("⬅️ Меню", "menu")]]),
        )
        return
    tasks = storage.list_tasks()
    if not tasks:
        api.send_message(chat_id, "Пока нет опубликованных задач.", main_menu("graduate"))
        return
    start = 0
    if after_id:
        ids = [task["id"] for task in tasks]
        if after_id in ids:
            start = (ids.index(after_id) + 1) % len(tasks)
    task = tasks[start]
    score, reasons = match_profile_to_task(profile, task)
    explanation = "\n".join(f"• {e(reason)}" for reason in reasons)
    api.send_message(
        chat_id,
        task_card(task) + f"\n\n🤖 <b>AI-совместимость: {score}%</b>\n{explanation}",
        inline_keyboard([
            [("🔥 Хочу участвовать", f"task:apply:{task['id']}"), ("⏭ Пропустить", f"task:skip:{task['id']}")],
            [("🔎 Подробнее", f"task:details:{task['id']}"), ("⬅️ Меню", "menu")],
        ]),
    )


def show_business_tasks(api: TelegramAPI, chat_id: int, user_id: int) -> None:
    tasks = storage.list_tasks(owner_id=user_id)
    if not tasks:
        api.send_message(
            chat_id,
            "У вас пока нет опубликованных задач.",
            inline_keyboard([[("➕ Создать задачу", "business:create")], [("⬅️ Меню", "menu")]]),
        )
        return
    rows = []
    lines = ["<b>Ваши задачи</b>"]
    for task in tasks:
        count = len(storage.list_proposals(task_id=task["id"]))
        lines.append(f"\n#{task['id']} {e(task['title'])}\nРейтинг {task['readiness_score']}/100 · откликов: {count}")
        rows.append([(f"Отклики: {task['title'][:22]}", f"business:applicants:{task['id']}")])
    rows.append([("⬅️ Меню", "menu")])
    api.send_message(chat_id, "\n".join(lines), inline_keyboard(rows))


def show_applicants(api: TelegramAPI, chat_id: int, task_id: str) -> None:
    task = storage.get_task(task_id)
    if not task:
        api.send_message(chat_id, "Задача не найдена.")
        return
    proposals = storage.list_proposals(task_id=task_id)
    if not proposals:
        api.send_message(
            chat_id,
            f"По задаче <b>{e(task['title'])}</b> пока нет откликов.",
            inline_keyboard([[("⬅️ К задачам", "business:tasks")]]),
        )
        return
    api.send_message(chat_id, f"<b>Отклики на задачу:</b> {e(task['title'])}")
    for proposal in proposals:
        profile = storage.get_profile(proposal["graduate_id"]) or {}
        score, reasons = match_profile_to_task(profile, task)
        body = (
            profile_card(profile)
            + f"\n\n🤖 <b>AI-совместимость: {score}%</b>\n"
            + "\n".join(f"• {e(reason)}" for reason in reasons)
            + f"\n\n💬 <b>Идея:</b> {e(proposal.get('idea'))}"
            + f"\n🗺 <b>План:</b> {e(proposal.get('plan'))}"
            + f"\n🔗 <b>Ссылка:</b> {e(proposal.get('link'))}"
            + f"\n📌 <b>Статус:</b> {e(proposal.get('status'))}"
        )
        api.send_message(
            chat_id,
            body,
            inline_keyboard([[
                ("🤝 Познакомиться", f"proposal:accept:{proposal['id']}"),
                ("⏭ Пропустить", f"proposal:reject:{proposal['id']}"),
            ]]),
        )


def handle_text(api: TelegramAPI, message: dict[str, Any]) -> None:
    chat_id = message["chat"]["id"]
    sender = message.get("from", {})
    user_id = sender["id"]
    text = message.get("text", "").strip()
    username = sender.get("username", "")
    storage.update_user(user_id, chat_id=chat_id, username=username)
    user = storage.get_user(user_id)

    if text in ("/start", "/menu"):
        storage.update_user(user_id, state="idle")
        send_home(api, chat_id, user_id)
        return
    if text == "/demo":
        storage.seed_demo()
        api.send_message(chat_id, "✅ Добавлены демонстрационные задачи.")
        send_home(api, chat_id, user_id)
        return
    if text == "/help":
        api.send_message(chat_id, "Команды: /start — главное меню, /demo — добавить примеры, /help — помощь.")
        return

    state = user.get("state", "idle")
    draft = dict(user.get("draft") or {})

    if state == "task_raw":
        draft["raw_description"] = text
        questions = build_clarifying_questions(text)
        preliminary_score, preliminary_level, _ = score_task({"context": text, "problem": text})
        storage.update_user(user_id, state="task_field", field_index=0, draft=draft)
        api.send_message(
            chat_id,
            f"📊 Предварительная готовность: <b>{preliminary_score}/100 — {preliminary_level}</b>\n\n"
            "🤖 <b>AI нашёл информацию, которую стоит уточнить:</b>\n\n"
            + "\n".join(f"• {e(question)}" for question in questions)
            + "\n\nТеперь соберём полную карточку.\n\n"
            + TASK_FIELDS[0][1],
        )
        return

    if state == "task_field":
        index = int(user.get("field_index", 0))
        field, _ = TASK_FIELDS[index]
        draft[field] = text
        index += 1
        if index >= len(TASK_FIELDS):
            finish_task(api, chat_id, user_id, draft)
        else:
            storage.update_user(user_id, field_index=index, draft=draft)
            api.send_message(chat_id, TASK_FIELDS[index][1])
        return

    if state == "task_edit_field":
        field = str(user.get("edit_field", ""))
        if field not in {item[0] for item in TASK_FIELDS}:
            api.send_message(chat_id, "Поле не найдено. Откройте меню заново.")
            return
        draft[field] = text
        storage.update_user(user_id, edit_field=None)
        finish_task(api, chat_id, user_id, draft)
        return

    if state == "profile_field":
        index = int(user.get("field_index", 0))
        field, _ = PROFILE_FIELDS[index]
        draft[field] = text
        index += 1
        if index >= len(PROFILE_FIELDS):
            storage.set_profile(user_id, draft)
            storage.update_user(user_id, state="idle", draft={})
            api.send_message(chat_id, "✅ Профиль готов!\n\n" + profile_card(draft), main_menu("graduate"))
        else:
            storage.update_user(user_id, field_index=index, draft=draft)
            api.send_message(chat_id, PROFILE_FIELDS[index][1])
        return

    if state == "proposal_idea":
        draft["idea"] = text
        storage.update_user(user_id, state="proposal_plan", draft=draft)
        api.send_message(chat_id, "Опишите короткий план работы — 2–4 шага.")
        return
    if state == "proposal_plan":
        draft["plan"] = text
        storage.update_user(user_id, state="proposal_link", draft=draft)
        api.send_message(chat_id, "Добавьте ссылку на прототип/портфолио или напишите «позже».")
        return
    if state == "proposal_link":
        draft["link"] = text
        task_id = str(user.get("pending_task_id"))
        storage.create_proposal(task_id, user_id, draft)
        storage.update_user(user_id, state="idle", draft={}, pending_task_id=None)
        task = storage.get_task(task_id) or {}
        api.send_message(
            chat_id,
            f"✅ Отклик отправлен на задачу <b>{e(task.get('title'))}</b>. Решение остаётся за представителем бизнеса.",
            main_menu("graduate"),
        )
        owner = storage.get_user(int(task.get("owner_id", 0)))
        if owner.get("chat_id"):
            api.send_message(int(owner["chat_id"]), f"📨 Новый отклик на задачу <b>{e(task.get('title'))}</b>!")
        return

    api.send_message(chat_id, "Используйте кнопки меню или команду /start.", main_menu(user.get("role")))


def handle_callback(api: TelegramAPI, callback: dict[str, Any]) -> None:
    callback_id = callback["id"]
    data = callback.get("data", "")
    message = callback.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    user_id = callback.get("from", {}).get("id")
    if not chat_id or not user_id:
        return
    api.answer_callback(callback_id)

    if data in ("menu", "role:choose"):
        if data == "role:choose":
            storage.update_user(user_id, role=None, state="idle")
        send_home(api, chat_id, user_id)
        return
    if data.startswith("role:"):
        role = data.split(":", 1)[1]
        storage.update_user(user_id, role=role, state="idle")
        if role == "graduate" and not storage.get_profile(user_id):
            api.send_message(
                chat_id,
                "Вы выбрали роль выпускника. Сначала создайте профиль.",
                inline_keyboard([[("👤 Создать профиль", "graduate:profile")], [("⬅️ Меню", "menu")]]),
            )
        else:
            send_home(api, chat_id, user_id)
        return
    if data == "business:create":
        begin_task(api, chat_id, user_id)
        return
    if data == "business:tasks":
        show_business_tasks(api, chat_id, user_id)
        return
    if data.startswith("business:applicants:"):
        show_applicants(api, chat_id, data.rsplit(":", 1)[1])
        return
    if data == "task:publish":
        user = storage.get_user(user_id)
        draft = dict(user.get("draft") or {})
        if not draft:
            api.send_message(chat_id, "Черновик не найден. Создайте задачу заново.")
            return
        task = storage.create_task(user_id, draft)
        storage.update_user(user_id, state="idle", draft={})
        api.send_message(
            chat_id,
            f"✅ Задача <b>{e(task['title'])}</b> опубликована в общем каталоге.",
            main_menu("business"),
        )
        return
    if data == "task:editmenu":
        user = storage.get_user(user_id)
        if not user.get("draft"):
            api.send_message(chat_id, "Черновик не найден.")
            return
        labels = {
            "company": "Компания", "title": "Название", "context": "Контекст",
            "problem": "Проблема", "users": "Пользователи", "data": "Данные",
            "expected": "Результат", "success": "Критерии успеха",
            "constraints": "Ограничения", "contact": "Связь", "skills": "Навыки",
        }
        buttons = [(labels[field], f"taskedit:{field}") for field, _ in TASK_FIELDS]
        rows = [buttons[index:index + 2] for index in range(0, len(buttons), 2)]
        rows.append([("⬅️ К карточке", "task:preview")])
        api.send_message(chat_id, "Какое поле изменить?", inline_keyboard(rows))
        return
    if data == "task:preview":
        user = storage.get_user(user_id)
        draft = dict(user.get("draft") or {})
        if draft:
            finish_task(api, chat_id, user_id, draft)
        return
    if data.startswith("taskedit:"):
        field = data.split(":", 1)[1]
        prompts = dict(TASK_FIELDS)
        if field not in prompts:
            api.send_message(chat_id, "Поле не найдено.")
            return
        storage.update_user(user_id, state="task_edit_field", edit_field=field)
        api.send_message(chat_id, "Введите новое значение.\n\n" + prompts[field])
        return
    if data == "graduate:profile":
        begin_profile(api, chat_id, user_id)
        return
    if data == "graduate:browse":
        show_next_task(api, chat_id, user_id)
        return
    if data == "graduate:proposals":
        proposals = storage.list_proposals(graduate_id=user_id)
        if not proposals:
            api.send_message(chat_id, "Вы пока не отправляли отклики.", main_menu("graduate"))
            return
        lines = ["<b>Ваши отклики</b>"]
        for proposal in proposals:
            task = storage.get_task(proposal["task_id"]) or {}
            lines.append(f"\n• {e(task.get('title'))} — <b>{e(proposal.get('status'))}</b>")
        api.send_message(chat_id, "\n".join(lines), main_menu("graduate"))
        return
    if data.startswith("task:skip:"):
        show_next_task(api, chat_id, user_id, data.rsplit(":", 1)[1])
        return
    if data.startswith("task:details:"):
        task_id = data.rsplit(":", 1)[1]
        task = storage.get_task(task_id)
        if task:
            api.send_message(
                chat_id,
                task_card(task, include_full=True),
                inline_keyboard([[("🔥 Откликнуться", f"task:apply:{task_id}"), ("⏭ Далее", f"task:skip:{task_id}")]]),
            )
        return
    if data.startswith("task:apply:"):
        task_id = data.rsplit(":", 1)[1]
        if storage.list_proposals(task_id=task_id, graduate_id=user_id):
            api.send_message(chat_id, "Вы уже откликнулись на эту задачу.")
            return
        storage.update_user(user_id, state="proposal_idea", pending_task_id=task_id, draft={})
        api.send_message(chat_id, "Почему эта задача вам интересна и какую идею решения вы предлагаете?")
        return
    if data.startswith("proposal:accept:") or data.startswith("proposal:reject:"):
        parts = data.split(":")
        status = "accepted" if parts[1] == "accept" else "rejected"
        proposal = storage.set_proposal_status(parts[2], status)
        if not proposal:
            api.send_message(chat_id, "Отклик не найден.")
            return
        task = storage.get_task(proposal["task_id"]) or {}
        word = "принят" if status == "accepted" else "отклонён"
        api.send_message(chat_id, f"Отклик {word}.", inline_keyboard([[("⬅️ К задачам", "business:tasks")]]))
        graduate = storage.get_user(proposal["graduate_id"])
        if graduate.get("chat_id"):
            notice = (
                f"🤝 Ваш отклик на задачу <b>{e(task.get('title'))}</b> принят! Бизнес хочет познакомиться."
                if status == "accepted"
                else f"Спасибо за интерес к задаче <b>{e(task.get('title'))}</b>. Сейчас бизнес продолжит с другим предложением."
            )
            api.send_message(int(graduate["chat_id"]), notice)
        return

    api.send_message(chat_id, "Кнопка устарела. Откройте /start.")


def run() -> None:
    if not BOT_TOKEN:
        print("Не задан TELEGRAM_BOT_TOKEN. Скопируйте .env.example в .env и вставьте токен.")
        sys.exit(1)
    storage.seed_demo()
    api = TelegramAPI(BOT_TOKEN)
    bot = api.call("getMe")
    log.info("BIRGE started as @%s", bot.get("username"))
    offset: int | None = None
    while True:
        try:
            for update in api.get_updates(offset):
                offset = update["update_id"] + 1
                if "message" in update:
                    handle_text(api, update["message"])
                elif "callback_query" in update:
                    handle_callback(api, update["callback_query"])
        except KeyboardInterrupt:
            log.info("Stopped")
            break
        except Exception:
            log.exception("Update failed; retrying")
            time.sleep(3)


if __name__ == "__main__":
    run()
