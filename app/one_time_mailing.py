from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)

from app.instances import bot, db

logger = logging.getLogger(__name__)

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

MESSAGE_TEXT = """За последний год изменилось многое

Изменился рынок маркетплейсов, требования клиентов, условия и правила пребывания.

Что делать создателям инфографики? Для ответа на ваш вопрос я полностью пересобрала свой бесплатный мини-курс по работе с текстом в инфографике, который вы проходили ранее.

Это не просто обнова, а совершенно другой материал.

<tg-emoji emoji-id="5418046259732715493">🤓</tg-emoji> Теперь за 3 коротких урока вы узнаете:

• почему ваш подход к продаже инфографики больше неактуален, и как это исправить;
• мою актуальную систему создания инфографики с гарантией роста, которая только с 1 человека помогла заработать пол 🍋
• как получать согласия от клиентов в 26 году с конкуренцией, комиссиями, налогами?

Внутри вас ждут практика, полезные материалы и эксклюзивный бонус, который я никогда не включала ранее.

Запускайте 👇
/start"""

FALLBACK_MESSAGE_TEXT = MESSAGE_TEXT.replace(
    '<tg-emoji emoji-id="5418046259732715493">🤓</tg-emoji>',
    '🤓',
)


def _recipient_ids() -> tuple[int, ...]:
    return tuple(
        int(value.strip())
        for value in os.getenv("ONE_TIME_MAILING_RECIPIENT_IDS", "").split(",")
        if value.strip().isdigit()
    )


def _send_at() -> datetime | None:
    value = os.getenv("ONE_TIME_MAILING_SEND_AT", "").strip()
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=MOSCOW_TZ)
    return parsed


async def _send_message(user_id: int) -> None:
    for attempt in range(1, 4):
        try:
            await bot.send_message(
                chat_id=user_id,
                text=MESSAGE_TEXT,
                parse_mode="HTML",
            )
            return
        except TelegramRetryAfter as error:
            logger.warning(
                "Telegram просит подождать %s сек. перед отправкой пользователю %s",
                error.retry_after,
                user_id,
            )
            await asyncio.sleep(float(error.retry_after) + 1)
        except TelegramNetworkError:
            if attempt >= 3:
                raise
            await asyncio.sleep(2**attempt)
        except TelegramBadRequest as error:
            error_text = str(error).lower()
            if "emoji" in error_text or "entity" in error_text or "parse" in error_text:
                await bot.send_message(
                    chat_id=user_id,
                    text=FALLBACK_MESSAGE_TEXT,
                    parse_mode="HTML",
                )
                return
            raise

    raise RuntimeError(f"Не удалось отправить сообщение пользователю {user_id}")


async def scheduled_legacy_course_mailing() -> None:
    mailing_key = os.getenv("ONE_TIME_MAILING_KEY", "").strip()
    send_at = _send_at()
    recipient_ids = _recipient_ids()

    if not mailing_key or send_at is None or not recipient_ids:
        logger.info("Одноразовая рассылка отключена")
        return

    try:
        delay = (send_at - datetime.now(send_at.tzinfo)).total_seconds()
        if delay > 0:
            logger.info(
                "Одноразовая рассылка %s запланирована на %s",
                mailing_key,
                send_at.isoformat(),
            )
            await asyncio.sleep(delay)
        else:
            logger.info(
                "Время рассылки %s уже наступило — запускаем проверку сразу",
                mailing_key,
            )

        await db.prepare_one_time_mailing(mailing_key, recipient_ids)

        while True:
            pending_user_ids = await db.get_pending_one_time_mailing_users(
                mailing_key
            )
            if not pending_user_ids:
                stats = await db.get_one_time_mailing_stats(mailing_key)
                logger.info(
                    "Рассылка %s завершена: sent=%s failed=%s total=%s",
                    mailing_key,
                    stats.get("sent", 0),
                    stats.get("failed", 0),
                    sum(stats.values()),
                )
                return

            had_transient_error = False

            for user_id in pending_user_ids:
                try:
                    await _send_message(user_id)
                    await db.mark_one_time_mailing_sent(mailing_key, user_id)
                    logger.info("Рассылка доставлена пользователю %s", user_id)
                except TelegramForbiddenError as error:
                    await db.mark_one_time_mailing_failed(
                        mailing_key,
                        user_id,
                        str(error),
                    )
                    logger.info(
                        "Пользователь %s заблокировал бота или запретил сообщения",
                        user_id,
                    )
                except TelegramBadRequest as error:
                    await db.mark_one_time_mailing_failed(
                        mailing_key,
                        user_id,
                        str(error),
                    )
                    logger.warning(
                        "Рассылка не доставлена пользователю %s: %s",
                        user_id,
                        error,
                    )
                except TelegramNetworkError as error:
                    await db.record_one_time_mailing_transient_error(
                        mailing_key,
                        user_id,
                        str(error),
                    )
                    had_transient_error = True
                    logger.warning(
                        "Временная ошибка Telegram для пользователя %s; повторим позже",
                        user_id,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    await db.mark_one_time_mailing_failed(
                        mailing_key,
                        user_id,
                        repr(error),
                    )
                    logger.exception(
                        "Неожиданная ошибка рассылки пользователю %s",
                        user_id,
                    )

                await asyncio.sleep(0.12)

            if had_transient_error:
                await asyncio.sleep(60)
            else:
                await asyncio.sleep(0)

    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Критическая ошибка одноразовой рассылки %s", mailing_key)
