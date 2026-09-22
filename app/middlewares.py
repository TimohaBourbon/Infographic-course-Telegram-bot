from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.instances import db

ALLOWED_WHEN_LOCKED = ("/start", "/invite", "/help", "/reset")


class LifeCheckMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user = getattr(event, "from_user", None)
        if from_user is None:
            return await handler(event, data)

        # Пользовательская часть курса работает только в личной переписке.
        if isinstance(event, Message) and event.chat.type != ChatType.PRIVATE:
            await event.answer("Бот работает только в личных сообщениях.")
            return None
        if isinstance(event, CallbackQuery):
            message = event.message
            if message is None or message.chat.type != ChatType.PRIVATE:
                await event.answer(
                    "Откройте бота в личных сообщениях.",
                    show_alert=True,
                )
                return None

        user_id = from_user.id
        exists = await db.user_exists(user_id)
        if not exists:
            # Единственная разрешённая точка входа неизвестного пользователя — /start.
            if isinstance(event, Message):
                text = (event.text or "").strip()
                command = text.split(maxsplit=1)[0].split("@", 1)[0]
                if command == "/start":
                    return await handler(event, data)
                await event.answer("Сначала запустите бота командой /start.")
                return None

            if isinstance(event, CallbackQuery):
                await event.answer(
                    "Сначала запустите бота командой /start.",
                    show_alert=True,
                )
                return None

        lives = await db.get_lives(user_id)
        if lives == 0:
            if isinstance(event, Message):
                text = (event.text or event.caption or "").strip()
                if text.startswith(ALLOWED_WHEN_LOCKED):
                    await db.record_activity(user_id)
                    return await handler(event, data)
                await event.answer(
                    "Доступ закрыт: закончились жизни. Используйте /invite, чтобы вернуться."
                )
                return None

            if isinstance(event, CallbackQuery):
                if event.data == "get_extra_life":
                    return await handler(event, data)
                await event.answer(
                    "Доступ закрыт: у тебя закончились жизни.",
                    show_alert=True,
                )
                return None

        # Обычная активность учитывается для аналитики, но НЕ переносит
        # дедлайн списания жизни. Дедлайн меняют только реальные этапы курса.
        await db.record_activity(user_id)
        return await handler(event, data)
