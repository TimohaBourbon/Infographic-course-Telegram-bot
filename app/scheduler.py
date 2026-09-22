import asyncio
import logging

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import FSInputFile

from app.config import (
    GOOGLE_SHEETS_DB_SPREADSHEET_ID,
    EXTRA_LIFE_EXPIRED_MESSAGE,
    LIFE_IMAGES,
    LIFE_IMAGES_DIR,
    LIFE_MESSAGES,
    SHEETS_SYNC_INTERVAL_SECONDS,
)
from app.instances import bot, db
import app.keyboards as kb
from app.sheets_sync import sync_full

logger = logging.getLogger(__name__)


async def _send_life_notification(
    user_id: int,
    lives: int,
    extra_life_used: bool,
) -> None:
    if lives == 0 and extra_life_used:
        bot_info = await bot.get_me()
        referral_link = f"https://t.me/{bot_info.username}?start={user_id}"
        text = EXTRA_LIFE_EXPIRED_MESSAGE.format(referral_link=referral_link)
        image_path = None
        reply_markup = None
    else:
        text = LIFE_MESSAGES.get(lives)
        if not text:
            return
        image_name = LIFE_IMAGES.get(lives)
        image_path = LIFE_IMAGES_DIR / image_name if image_name else None
        if lives == 1:
            reply_markup = kb.inline_continue_course
        elif lives == 0:
            reply_markup = kb.inline_get_extra_life
        else:
            reply_markup = None

    try:
        if image_path and image_path.is_file():
            await bot.send_photo(
                chat_id=user_id,
                photo=FSInputFile(image_path),
                caption=text,
                reply_markup=reply_markup,
            )
        else:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=reply_markup,
            )
    except (TelegramForbiddenError, TelegramBadRequest):
        logger.info("Уведомление о жизнях не доставлено пользователю %s", user_id)


async def periodic_life_removal() -> None:
    while True:
        try:
            affected_users = await db.remove_life_from_inactive_users()
            for user_id, lives, extra_life_used in affected_users:
                await _send_life_notification(user_id, lives, extra_life_used)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Ошибка при списании жизней")

        await asyncio.sleep(60)


async def periodic_sheets_sync() -> None:
    if not GOOGLE_SHEETS_DB_SPREADSHEET_ID:
        logger.info("Синхронизация Google Sheets отключена")
        return

    while True:
        try:
            await asyncio.to_thread(
                sync_full,
                GOOGLE_SHEETS_DB_SPREADSHEET_ID,
            )
            logger.info("Данные синхронизированы с Google Sheets")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Ошибка синхронизации Google Sheets")

        await asyncio.sleep(SHEETS_SYNC_INTERVAL_SECONDS)
