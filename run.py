import asyncio
import logging

from aiogram.types import BotCommandScopeDefault

from app.commands import BOT_COMMANDS
from app.config import EXCLUSIVE_BONUS_FILE, GUIDE_FIGMA_FILE, LESSON_1_BRIEF_FILE
from app.handlers import router, support_admin_router, support_user_router
from app.instances import bot, db, dp, support_admin_bot, support_admin_dp
from app.middlewares import LifeCheckMiddleware
from app.one_time_mailing import scheduled_legacy_course_mailing
from app.scheduler import periodic_life_removal, periodic_sheets_sync

logger = logging.getLogger(__name__)


def _validate_files() -> None:
    missing = [
        path
        for path in (GUIDE_FIGMA_FILE, LESSON_1_BRIEF_FILE, EXCLUSIVE_BONUS_FILE)
        if not path.is_file()
    ]
    if missing:
        missing_list = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"Не найдены обязательные материалы: {missing_list}")


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    _validate_files()
    await db.connect()
    await db.initialize_schema()

    dp.message.middleware(LifeCheckMiddleware())
    dp.callback_query.middleware(LifeCheckMiddleware())
    dp.include_router(router)
    dp.include_router(support_user_router)
    support_admin_dp.include_router(support_admin_router)

    await bot.set_my_commands(
        commands=BOT_COMMANDS,
        scope=BotCommandScopeDefault(),
    )

    tasks = [
        asyncio.create_task(
            dp.start_polling(bot, handle_signals=False),
            name="main_bot_polling",
        ),
        asyncio.create_task(
            support_admin_dp.start_polling(
                support_admin_bot,
                handle_signals=False,
            ),
            name="support_bot_polling",
        ),
        asyncio.create_task(
            periodic_life_removal(),
            name="life_removal",
        ),
        asyncio.create_task(
            periodic_sheets_sync(),
            name="sheets_sync",
        ),
        asyncio.create_task(
            scheduled_legacy_course_mailing(),
            name="legacy_course_relaunch_mailing",
        ),
    ]

    logger.info("Course Bot запущен")
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        await dp.storage.close()
        await support_admin_dp.storage.close()
        await db.disconnect()
        await bot.session.close()
        await support_admin_bot.session.close()
        logger.info("Course Bot остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
