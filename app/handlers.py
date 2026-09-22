from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from typing import Iterable

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, ForceReply, FSInputFile, Message

import app.keyboards as kb
from app.config import (
    COURSE_CHANNEL_ID,
    COURSE_INTRO_URL,
    EXCLUSIVE_BONUS_FILE,
    EXTRA_LIFE_EXPIRED_MESSAGE,
    EXTRA_LIFE_GRANTED_MESSAGE,
    FIGMA_TEMPLATE_URL,
    FINAL_BONUS_VIDEO_URL,
    GUIDE_FIGMA_FILE,
    LESSON_1_BRIEF_FILE,
    LESSON_1_URL,
    LESSON_2_URL,
    LESSON_3_URL,
    LIFE_IMAGES,
    LIFE_IMAGES_DIR,
    LIFE_MESSAGES,
    SUPPORT_ADMINS,
    SURVEY_URL,
)
from app.course_steps import CourseStep
from app.instances import bot, db, support_admin_bot
from app.test_answers import TEST_2_QUESTIONS

logger = logging.getLogger(__name__)

router = Router(name="course_router")
support_user_router = Router(name="support_user_router")
support_admin_router = Router(name="support_admin_router")

SUPPORT_PROMPT_MARK = "[SUPPORT_PROMPT]"
SUPPORT_REPLY_RE = re.compile(
    rf"{re.escape(SUPPORT_PROMPT_MARK)}\s+UID:(\d+)\s+T:(\d+)"
)
SUPPORT_ADMIN_HINT_RE = re.compile(r"UID:\s*(\d+)")

COURSE_RULES_TEXT = (
    "🔑Чуть меньше часа на прохождение — и вы уже не просто красиво "
    "делаете инфографику, а уверенно увеличиваете выручку селлеру/себе.\n\n"
    "В этом мини-курсе вы узнаете, как создателю инфографики на "
    "сегодняшний день спокойно брать проекты от 18 000 ₽ и не гнаться "
    "за каждым клиентом.\n"
    "(Если вы пришли за дизайном — вам не сюда!!)\n\n"
    "<b>📌Вас ждут 3 информативных урока:</b>\n\n"
    "<b>Урок 1.</b> Золотые?! годы дохода создателя инфографики. Что "
    "реально требует клиент и как ему это давать.\n\n"
    "<b>Урок 2.</b> Моя авторская пошаговая система создания инфографики "
    "с гарантией роста.\n\n"
    "<b>Урок 3.</b> Как расти и стабильно зарабатывать 120–200 тыс. ₽ без "
    "блога.\n\n"
    "<b>🔝 При прохождении вас ожидают:</b>\n\n"
    "— пару бонусов, цена которым — всего то 4 года моего пыхтения 🙄;\n"
    "— практика, чтобы закрепить новые навыки.\n\n"
    "<b>🎁В конце вы получите:</b>\n\n"
    "— сертификат для подтверждения своего нового навыка;\n"
    "— дополнительный подарок для ускорения работы;\n"
    "— дополнительный подарок для успешного закрытия клиентов;\n"
    "— главный бонус, о котором вы узнаете дальше 🤫\n\n"
    "Готовы? Поехали!"
)

SURVEY_TEXT = (
    "Хотите выйти на стабильный поток клиентов, повысить чек / перестать "
    "конкурировать только ценой / повысить эффективность карточки?\n\n"
    "Получите в подарок бесплатный разбор на онлайн-встрече. Я лично "
    "погружусь в вашу ситуацию и помогу найти точки роста.\n\n"
    "Заполните анкету, чтобы я смогла дать более точные рекомендации. "
    "Это не займет больше 5 минут.\n\n"
    "👉 <a href=\"{survey_url}\">Ссылка на анкету</a>\n\n"
    "Заполнив анкету, вас гарантированно ожидают:\n\n"
    "• персональные рекомендации под ваш запрос;\n"
    "• бонусный урок «Ускорение работы» — один из материалов, который "
    "доступен только в платном формате, но не для вас;\n"
    "• информация по заработанным звездам (пока секрет).\n\n"
    "Вдобавок — сертификат о прохождении мини-курса, который подтверждает "
    "наличие у вас нового навыка: «Карточка под ключ. Создание своего ТЗ».\n\n"
    "(Анкета ни к чему не обязывает и нужна только для изучения ваших "
    "потребностей)\n\n"
    "Жми кнопку, как заполнишь."
)

FINAL_SURVEY_TEXT = (
    "✅ Ваша анкета отправлена.\n\n"
    "Выслал тебе бонусный урок по ускорению работы! — один из материалов, "
    "который доступен только в платном формате, но не для вас. "
    "Переходи смотреть.\n\n"
    "В течение ближайшего времени я (автор @yanalobach) изучу ответы и "
    "подготовлю для вас:\n\n"
    "— персональные рекомендации под ваш запрос;\n"
    "— информацию по заработанным звездам (пока секрет).\n\n"
    "А также сертификат о прохождении мини-курса.\n\n"
    "Ожидайте сообщение в телеграме!"
)

BONUS_REMINDER_TEXT = (
    "Возвращайся!\n"
    "Ты еще не забрал:\n"
    "— сертификат для подтверждения своего нового навыка;\n"
    "— платный урок за БЕСПЛАТНО для ускорения работы;\n"
    "— главный бонус, о котором узнаешь дальше 🤫"
)

_bonus_reminder_tasks: dict[int, asyncio.Task[None]] = {}


def _test_result_text(stars: int) -> str:
    if stars <= 0:
        return (
            "Ты заработал 0 звезд⭐\n\n"
            "Не расстраивайся!\n"
            "Советую просто пересмотреть данный урок. В любом случае "
            "переходи дальше — бонусы не заканчиваются!"
        )
    if stars == 1:
        return (
            "Ты заработал 1 звезду ⭐\n\n"
            "Продолжай проходить уроки — в конце узнаешь, на что можно "
            "обменять накопленные звезды 🚀"
        )
    if stars == 2:
        return (
            "Ты заработал 2 звезды ⭐\n\n"
            "Продолжай проходить уроки — в конце узнаешь, на что можно "
            "обменять накопленные звезды 🚀"
        )
    return (
        "Поздравляю! Ты заработал максимум звезд (+3 ⭐)\n\n"
        "Продолжай проходить уроки — в конце узнаешь, на что можно "
        "обменять накопленные звезды 🚀"
    )


async def _send_bonus_reminder_later(user_id: int) -> None:
    try:
        await asyncio.sleep(60 * 60)
        step = await db.get_course_step(user_id)
        if step == CourseStep.LESSON_3_DONE:
            await bot.send_message(user_id, BONUS_REMINDER_TEXT)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception(
            "Не удалось отправить напоминание о бонусах пользователю %s",
            user_id,
        )
    finally:
        _bonus_reminder_tasks.pop(user_id, None)


def _schedule_bonus_reminder(user_id: int) -> None:
    current_task = _bonus_reminder_tasks.get(user_id)
    if current_task is not None and not current_task.done():
        return
    _bonus_reminder_tasks[user_id] = asyncio.create_task(
        _send_bonus_reminder_later(user_id)
    )



async def _remove_inline_keyboard(callback: CallbackQuery) -> None:
    if callback.message is None:
        return
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass


async def _register_user(message: Message, referrer_id: int | None = None) -> None:
    user = message.from_user
    if user is None:
        return
    await db.add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        referrer_id=referrer_id,
    )


async def _is_channel_member(check_bot: Bot, user_id: int) -> bool:
    member = await check_bot.get_chat_member(
        chat_id=COURSE_CHANNEL_ID,
        user_id=user_id,
    )
    return member.status in {"member", "administrator", "creator"}


async def _send_course_intro(message: Message) -> None:
    await message.answer(
        "Перед началом курса обязательно посмотри это "
        f'<a href="{html.escape(COURSE_INTRO_URL, quote=True)}">видео</a>!',
        reply_markup=kb.inline_hello,
    )


async def _send_figma_question(message: Message) -> None:
    await message.answer(
        "Тебе нужен Авторский ГАЙД для новичков в Figma?",
        reply_markup=kb.inline_rookie_guide,
    )


async def _send_course_rules(message: Message) -> None:
    await message.answer(COURSE_RULES_TEXT, reply_markup=kb.inline_ready_to_start)


async def _send_lesson_1(message: Message) -> None:
    await message.answer(
        f'<a href="{html.escape(LESSON_1_URL, quote=True)}">🎥 Урок 1</a>'
    )
    await message.answer(
        "После просмотра нажми кнопку ниже — я выдам тебе свои 4х-летние труды",
        reply_markup=kb.inline_finish_lesson_1,
    )


async def _send_lesson_1_materials(message: Message) -> None:
    await message.answer_document(
        document=FSInputFile(LESSON_1_BRIEF_FILE),
        caption="📄 Бриф для работы",
    )
    await message.answer(
        f'<a href="{html.escape(FIGMA_TEMPLATE_URL, quote=True)}">📎 Шаблон в Figma</a>',
        reply_markup=kb.inline_next_lesson_2,
    )


async def _send_lesson_2(message: Message) -> None:
    await message.answer(
        f'<a href="{html.escape(LESSON_2_URL, quote=True)}">🎥 Урок 2</a>'
    )
    await message.answer_document(
        document=FSInputFile(
            GUIDE_FIGMA_FILE,
            filename="старт в фигме.pdf",
        )
    )
    await message.answer(
        "После просмотра нажми кнопку ниже и пройди короткий тест для "
        "проверки новых знаний",
        reply_markup=kb.inline_start_test_2,
    )


async def _send_test_question_to_message(
    message: Message,
    *,
    attempt: int,
    question_index: int,
    edit_message: bool = False,
) -> None:
    if question_index not in range(len(TEST_2_QUESTIONS)):
        await message.answer("Сохранённое состояние теста повреждено. Нажмите /start.")
        return

    question = TEST_2_QUESTIONS[question_index]
    options = "\n".join(
        f"{index + 1}. {option}"
        for index, option in enumerate(question["options"])
    )
    text = f"Вопрос {question_index + 1}:\n{question['text']}\n\n{options}"
    keyboard = kb.build_answer_keyboard(
        attempt,
        question_index,
        len(question["options"]),
    )

    if edit_message:
        try:
            await message.edit_text(text, reply_markup=keyboard)
            return
        except TelegramBadRequest as error:
            # Повторный двойной callback может попытаться установить тот же текст.
            if "message is not modified" in str(error).lower():
                return
    await message.answer(text, reply_markup=keyboard)


async def _send_test_result_resume(message: Message) -> None:
    progress = await db.get_test_progress(message.chat.id, 2)
    if progress is None:
        await message.answer(
            "Тест ещё не завершён.",
            reply_markup=kb.inline_start_test_2,
        )
        return

    earned_stars = int(progress["rewarded_questions_mask"] or 0).bit_count()
    if progress["is_passed"]:
        # Идемпотентная проверка закрывает редкий случай перезапуска сразу
        # после успешного теста, но до выдачи реферальной награды.
        await db.try_grant_referral_reward(message.chat.id, notification_bot=bot)
    await message.answer(
        _test_result_text(earned_stars),
        reply_markup=kb.inline_next_lesson_3,
    )


async def _send_lesson_3(message: Message) -> None:
    await message.answer(
        f'<a href="{html.escape(LESSON_3_URL, quote=True)}">🎥 Урок 3</a>'
    )
    await message.answer(
        "После просмотра нажми кнопку ниже — я выдам тебе подарок, который "
        "поможет успешно закрывать каждого клиента",
        reply_markup=kb.inline_finish_lesson_3,
    )


async def _send_exclusive_bonus(message: Message) -> None:
    await message.answer_document(
        document=FSInputFile(EXCLUSIVE_BONUS_FILE),
        caption="Прочтите его, затем возвращайтесь за следующими бонусами!",
        reply_markup=kb.inline_next_bonus,
    )
    _schedule_bonus_reminder(message.chat.id)


async def _send_survey(message: Message) -> None:
    escaped_url = html.escape(SURVEY_URL, quote=True)
    await message.answer(
        SURVEY_TEXT.format(survey_url=escaped_url),
        reply_markup=kb.build_survey_keyboard(SURVEY_URL),
        disable_web_page_preview=True,
    )


async def _resume_course(message: Message) -> None:
    user = await db.get_user(message.chat.id)
    if user is None:
        await message.answer("Сначала запустите бота командой /start.")
        return

    if user["course_started"] and not user["course_completed"] and user["lives"] == 0:
        if user["extra_life_used"]:
            bot_info = await bot.get_me()
            referral_link = f"https://t.me/{bot_info.username}?start={message.chat.id}"
            await message.answer(
                EXTRA_LIFE_EXPIRED_MESSAGE.format(referral_link=referral_link)
            )
        else:
            image_name = LIFE_IMAGES.get(0)
            image_path = LIFE_IMAGES_DIR / image_name if image_name else None
            if image_path and image_path.is_file():
                await message.answer_photo(
                    photo=FSInputFile(image_path),
                    caption=LIFE_MESSAGES[0],
                    reply_markup=kb.inline_get_extra_life,
                )
            else:
                await message.answer(
                    LIFE_MESSAGES[0],
                    reply_markup=kb.inline_get_extra_life,
                )
        return

    step = CourseStep(user["course_step"])
    if step in {
        CourseStep.REGISTERED,
        CourseStep.INTRO,
        CourseStep.FIGMA_CHOICE,
    }:
        await db.advance_course_step(
            message.chat.id,
            step,
            CourseStep.READY,
        )
        await _send_course_rules(message)
    elif step == CourseStep.READY:
        await _send_course_rules(message)
    elif step == CourseStep.LESSON_1:
        await _send_lesson_1(message)
    elif step == CourseStep.LESSON_1_DONE:
        await _send_lesson_1_materials(message)
    elif step == CourseStep.LESSON_2:
        await _send_lesson_2(message)
    elif step == CourseStep.TEST_2_ACTIVE:
        progress = await db.get_test_progress(message.chat.id, 2)
        if progress and progress["in_progress"]:
            await message.answer("Продолжаем тест с сохранённого вопроса.")
            await _send_test_question_to_message(
                message,
                attempt=int(progress["attempt"]),
                question_index=int(progress["current_question"]),
            )
        else:
            await message.answer(
                "Тест ожидает запуска.",
                reply_markup=kb.inline_start_test_2,
            )
    elif step == CourseStep.TEST_2_DONE:
        await _send_test_result_resume(message)
    elif step == CourseStep.LESSON_3:
        await _send_lesson_3(message)
    elif step == CourseStep.LESSON_3_DONE:
        await _send_exclusive_bonus(message)
    elif step == CourseStep.SURVEY:
        await _send_survey(message)
    elif step == CourseStep.COMPLETED:
        await message.answer(FINAL_SURVEY_TEXT)


async def _reject_wrong_step(
    callback: CallbackQuery,
    expected: Iterable[CourseStep],
) -> None:
    current = await db.get_course_step(callback.from_user.id)
    expected_values = [int(step) for step in expected]
    if current is not None and int(current) > max(expected_values):
        text = "Этот шаг уже выполнен."
    else:
        text = "Сначала выполните предыдущий шаг курса."
    await callback.answer(text, show_alert=True)


async def _advance_or_reject(
    callback: CallbackQuery,
    expected: CourseStep,
    next_step: CourseStep,
) -> bool:
    if await db.advance_course_step(callback.from_user.id, expected, next_step):
        return True
    await _reject_wrong_step(callback, [expected])
    return False

@router.message(Command("reset"))
async def reset_course_for_testing(message: Message) -> None:
    """Полностью сбрасывает аккаунт администратора и запускает курс заново."""
    if message.from_user is None:
        return

    user_id = message.from_user.id

    if user_id not in SUPPORT_ADMINS:
        await message.answer("Эта команда доступна только администратору.")
        return

    await db.delete_user_completely(user_id)

    await message.answer(
        "🔄 Данные сброшены. Курс начинается заново."
    )

    # Повторно регистрируем пользователя и запускаем обычный сценарий /start.
    await command_start(message)


@router.callback_query(F.data == "life_continue")
async def continue_after_life_warning(callback: CallbackQuery) -> None:
    await callback.answer()
    await _remove_inline_keyboard(callback)
    if callback.message:
        await _resume_course(callback.message)


@router.callback_query(F.data == "get_extra_life")
async def get_extra_life(callback: CallbackQuery) -> None:
    granted = await db.grant_extra_life_once(callback.from_user.id)
    if not granted:
        await callback.answer(
            "Дополнительная жизнь уже была использована.",
            show_alert=True,
        )
        return

    await callback.answer()
    await _remove_inline_keyboard(callback)
    if callback.message:
        await callback.message.answer(
            EXTRA_LIFE_GRANTED_MESSAGE,
            reply_markup=kb.inline_continue_course,
        )


@router.message(CommandStart())
async def command_start(message: Message) -> None:
    if message.from_user is None:
        return

    parts = (message.text or "").split(maxsplit=1)
    referrer_id = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else None
    if referrer_id == message.from_user.id:
        referrer_id = None

    await _register_user(message, referrer_id)

    if not await _is_channel_member(bot, message.from_user.id):
        await message.answer("Не подписан, подпишись 👇", reply_markup=kb.inline_start)
        return

    await _resume_course(message)


@router.message(Command("stars"))
async def show_user_stars(message: Message) -> None:
    if message.from_user is None:
        return
    user = await db.get_user(message.from_user.id)
    if user is None:
        await message.answer("Сначала запустите бота командой /start.")
        return
    await message.answer(f"Твой баланс звёзд: {user['stars']} ⭐️")


@router.message(Command("invite"))
async def invite_command(message: Message) -> None:
    if message.from_user is None:
        return
    bot_info = await bot.get_me()
    referral_link = f"https://t.me/{bot_info.username}?start={message.from_user.id}"
    await message.answer(
        f"👥 Приглашай друзей по ссылке:\n{referral_link}\n\n"
        "Если они пройдут тест курса — ты получишь 1 ⭐️ и 1 ❤️ жизнь!"
    )


@router.callback_query(F.data == "subscribed")
async def subscribed_callback(callback: CallbackQuery) -> None:
    if not await _is_channel_member(bot, callback.from_user.id):
        await callback.answer("Подписка пока не найдена.", show_alert=True)
        return

    step = await db.get_course_step(callback.from_user.id)
    if step == CourseStep.REGISTERED:
        await db.advance_course_step(
            callback.from_user.id,
            CourseStep.REGISTERED,
            CourseStep.INTRO,
        )
    await callback.answer()
    await _remove_inline_keyboard(callback)
    if callback.message:
        await _resume_course(callback.message)


@router.callback_query(F.data == "figma_knowledge_level")
async def ask_figma_knowledge(callback: CallbackQuery) -> None:
    if not await _advance_or_reject(
        callback,
        CourseStep.INTRO,
        CourseStep.READY,
    ):
        return
    await callback.answer()
    await _remove_inline_keyboard(callback)
    if callback.message:
        await _send_course_rules(callback.message)


@router.callback_query(F.data == "rookie_guide_yes")
async def send_rookie_guide(callback: CallbackQuery) -> None:
    if not await _advance_or_reject(
        callback,
        CourseStep.FIGMA_CHOICE,
        CourseStep.READY,
    ):
        return
    await callback.answer()
    await _remove_inline_keyboard(callback)
    if callback.message:
        await _send_course_rules(callback.message)


@router.callback_query(F.data == "rookie_guide_no")
async def show_course_rules(callback: CallbackQuery) -> None:
    if not await _advance_or_reject(
        callback,
        CourseStep.FIGMA_CHOICE,
        CourseStep.READY,
    ):
        return
    await callback.answer()
    await _remove_inline_keyboard(callback)
    if callback.message:
        await _send_course_rules(callback.message)


@router.callback_query(F.data == "ready")
async def first_lesson(callback: CallbackQuery) -> None:
    if not await db.start_course(callback.from_user.id):
        await _reject_wrong_step(callback, [CourseStep.READY])
        return
    await callback.answer()
    await _remove_inline_keyboard(callback)
    if callback.message:
        await _send_lesson_1(callback.message)


@router.callback_query(F.data == "lesson_1_done")
async def finish_first_lesson(callback: CallbackQuery) -> None:
    if not await _advance_or_reject(
        callback,
        CourseStep.LESSON_1,
        CourseStep.LESSON_1_DONE,
    ):
        return
    await callback.answer()
    await _remove_inline_keyboard(callback)
    if callback.message:
        await _send_lesson_1_materials(callback.message)


@router.callback_query(F.data == "second_lesson")
async def show_second_lesson(callback: CallbackQuery) -> None:
    if not await _advance_or_reject(
        callback,
        CourseStep.LESSON_1_DONE,
        CourseStep.LESSON_2,
    ):
        return
    await callback.answer()
    await _remove_inline_keyboard(callback)
    if callback.message:
        await _send_lesson_2(callback.message)


async def _begin_test_two(callback: CallbackQuery, *, edit_message: bool) -> None:
    result = await db.begin_or_resume_test_two(callback.from_user.id)
    status = result["status"]

    if status == "passed":
        await callback.answer("Этот тест уже пройден.", show_alert=True)
        return
    if status == "exhausted":
        await callback.answer("Лимит попыток исчерпан.", show_alert=True)
        return
    if status in {"wrong_step", "unknown"}:
        await _reject_wrong_step(
            callback,
            [CourseStep.LESSON_2, CourseStep.TEST_2_DONE],
        )
        return

    await callback.answer()
    if not edit_message:
        await _remove_inline_keyboard(callback)
    if callback.message:
        await _send_test_question_to_message(
            callback.message,
            attempt=int(result["attempt"]),
            question_index=int(result["question_index"]),
            edit_message=edit_message,
        )


@router.callback_query(F.data == "test_2_start")
async def start_test_two(callback: CallbackQuery) -> None:
    await _begin_test_two(callback, edit_message=True)


@router.callback_query(F.data == "second_test_again")
async def retry_test_two(callback: CallbackQuery) -> None:
    # Результат попытки редактируется в первый вопрос. При двойном клике
    # второе редактирование окажется no-op и не создаст дубликат сообщения.
    await _begin_test_two(callback, edit_message=True)


@router.callback_query(F.data.startswith("test2:"))
async def handle_test_answer(callback: CallbackQuery) -> None:
    try:
        _, attempt_raw, question_raw, answer_raw = callback.data.split(":", 3)
        attempt = int(attempt_raw)
        question_index = int(question_raw)
        answer_index = int(answer_raw)
    except (AttributeError, ValueError):
        await callback.answer("Некорректный ответ.", show_alert=True)
        return

    if question_index not in range(len(TEST_2_QUESTIONS)):
        await callback.answer("Кнопка устарела.", show_alert=True)
        return
    question = TEST_2_QUESTIONS[question_index]
    if answer_index not in range(len(question["options"])):
        await callback.answer("Некорректный ответ.", show_alert=True)
        return

    result = await db.submit_test_two_answer(
        user_id=callback.from_user.id,
        attempt=attempt,
        question_index=question_index,
        answer_index=answer_index,
        correct_index=int(question["correct_index"]),
        total_questions=len(TEST_2_QUESTIONS),
    )

    if result["status"] != "next" and result["status"] != "complete":
        await callback.answer(
            "Этот ответ уже обработан или кнопка устарела.",
            show_alert=True,
        )
        return

    # Не показываем результат конкретного ответа: после нажатия бот сразу
    # открывает следующий вопрос. Начисление звезды остаётся скрытым.
    await callback.answer()
    if callback.message is None:
        return

    if result["status"] == "next":
        await _send_test_question_to_message(
            callback.message,
            attempt=int(result["attempt"]),
            question_index=int(result["question_index"]),
            edit_message=True,
        )
        return

    try:
        await callback.message.delete()
    except TelegramBadRequest:
        await _remove_inline_keyboard(callback)

    if result["passed"]:
        await db.try_grant_referral_reward(
            callback.from_user.id,
            notification_bot=bot,
        )
    await callback.message.answer(
        _test_result_text(int(result["earned_stars"])),
        reply_markup=kb.inline_next_lesson_3,
    )


@router.callback_query(F.data.startswith("answer:"))
async def reject_legacy_test_button(callback: CallbackQuery) -> None:
    await callback.answer(
        "Эта кнопка устарела. Нажмите /start, чтобы продолжить тест.",
        show_alert=True,
    )


@router.callback_query(F.data == "third_lesson")
async def show_third_lesson(callback: CallbackQuery) -> None:
    if not await _advance_or_reject(
        callback,
        CourseStep.TEST_2_DONE,
        CourseStep.LESSON_3,
    ):
        return
    await callback.answer()
    await _remove_inline_keyboard(callback)
    if callback.message:
        await _send_lesson_3(callback.message)


@router.callback_query(F.data == "lesson_3_done")
async def finish_third_lesson(callback: CallbackQuery) -> None:
    if not await _advance_or_reject(
        callback,
        CourseStep.LESSON_3,
        CourseStep.LESSON_3_DONE,
    ):
        return
    await callback.answer()
    await _remove_inline_keyboard(callback)
    if callback.message:
        await _send_exclusive_bonus(callback.message)


@router.callback_query(F.data == "next_bonus")
async def show_survey(callback: CallbackQuery) -> None:
    if not await _advance_or_reject(
        callback,
        CourseStep.LESSON_3_DONE,
        CourseStep.SURVEY,
    ):
        return
    await callback.answer()
    await _remove_inline_keyboard(callback)
    if callback.message:
        await _send_survey(callback.message)


@router.callback_query(F.data == "survey_completed")
async def survey_completed(callback: CallbackQuery) -> None:
    if not await db.confirm_survey_once(callback.from_user.id):
        await _reject_wrong_step(callback, [CourseStep.SURVEY])
        return

    await callback.answer()
    await _remove_inline_keyboard(callback)

    if callback.message:
        await callback.message.answer(
            f'<a href="{html.escape(FINAL_BONUS_VIDEO_URL, quote=True)}">'
            'Бонусный урок "Ускорение работы"</a>'
        )

        await callback.message.answer(FINAL_SURVEY_TEXT)


def _support_is_admin(user_id: int) -> bool:
    return user_id in SUPPORT_ADMINS


async def _forward_support_question(
    user_id: int,
    full_name: str,
    username: str | None,
    text: str,
) -> int:
    safe_name = html.escape(full_name)
    safe_username = html.escape(username or "—")
    safe_text = html.escape(text)
    forwarded = (
        "🆘 Новый запрос в поддержку\n"
        f"UID: {user_id}\n"
        f"Имя: {safe_name} (@{safe_username})\n\n"
        f"{safe_text}"
    )

    delivered = 0
    for admin_id in SUPPORT_ADMINS:
        try:
            await support_admin_bot.send_message(
                chat_id=admin_id,
                text=forwarded,
                reply_markup=kb.support_reply_keyboard(user_id),
            )
            delivered += 1
        except Exception:
            logger.exception("Не удалось переслать вопрос администратору %s", admin_id)
    return delivered


@support_user_router.message(Command("help"))
async def support_help_entry(message: Message) -> None:
    if message.from_user is None:
        return

    text_after_command = (
        message.text.split(" ", 1)[1].strip()
        if message.text and " " in message.text
        else ""
    )
    if text_after_command:
        delivered = await _forward_support_question(
            user_id=message.from_user.id,
            full_name=message.from_user.full_name,
            username=message.from_user.username,
            text=text_after_command,
        )
        if delivered:
            await message.answer(
                "Спасибо! Сообщение отправлено в поддержку. Ответ придёт сюда ✅"
            )
        else:
            await message.answer("Поддержка временно недоступна. Попробуйте позже.")
        return

    token = str(int(time.time()))
    prompt = (
        "Опиши, пожалуйста, свой вопрос и отправь его ответом на это сообщение.\n"
        f"{SUPPORT_PROMPT_MARK} UID:{message.from_user.id} T:{token}"
    )
    await message.answer(prompt, reply_markup=ForceReply(selective=True))


@support_user_router.message()
async def collect_support_reply(message: Message) -> None:
    if message.from_user is None:
        return
    replied_message = message.reply_to_message
    if not replied_message or not replied_message.text:
        return
    if not SUPPORT_REPLY_RE.search(replied_message.text):
        return

    text = message.text or message.caption
    if not text:
        await message.answer("Сейчас поддерживается только текстовый вопрос.")
        return

    delivered = await _forward_support_question(
        user_id=message.from_user.id,
        full_name=message.from_user.full_name,
        username=message.from_user.username,
        text=text,
    )
    if delivered:
        await message.answer(
            "Спасибо! Сообщение отправлено в поддержку. Ответ придёт сюда ✅"
        )
    else:
        await message.answer("Поддержка временно недоступна. Попробуйте позже.")


@support_admin_router.callback_query(F.data.startswith("sup:hint:"))
async def support_admin_reply_hint(callback: CallbackQuery) -> None:
    if not _support_is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    try:
        user_id = int(callback.data.rsplit(":", 1)[1])
    except (AttributeError, ValueError):
        await callback.answer("Некорректный UID.", show_alert=True)
        return

    if callback.message:
        await callback.message.answer(
            "Напишите ответ <b>ОТВЕТОМ</b> на это сообщение.\n"
            f"UID: {user_id}",
            reply_markup=ForceReply(selective=True),
        )
    await callback.answer()


@support_admin_router.message()
async def support_admin_reply(message: Message) -> None:
    if message.from_user is None or not _support_is_admin(message.from_user.id):
        return

    replied_message = message.reply_to_message
    if not replied_message or not replied_message.text:
        return
    match = SUPPORT_ADMIN_HINT_RE.search(replied_message.text)
    if not match:
        return

    text = message.text or message.caption
    if not text:
        await message.answer("Сейчас поддерживается только текстовый ответ.")
        return

    target_user_id = int(match.group(1))
    try:
        await bot.send_message(
            chat_id=target_user_id,
            text=f"✉️ Ответ поддержки:\n\n{html.escape(text)}",
        )
        await message.answer("Ответ отправлен пользователю ✅")
    except Exception as error:
        logger.exception("Не удалось доставить ответ пользователю %s", target_user_id)
        await message.answer(f"Не удалось доставить ответ: {html.escape(str(error))}")
