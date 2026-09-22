from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import asyncpg
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.course_steps import CourseStep

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, dsn: str, schema_file: Path):
        self.dsn = dsn
        self.schema_file = schema_file
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                dsn=self.dsn,
                min_size=1,
                max_size=5,
            )
            logger.info("Подключение к PostgreSQL установлено")

    async def initialize_schema(self) -> None:
        schema = self.schema_file.read_text(encoding="utf-8")
        async with self._pool().acquire() as connection:
            await connection.execute(schema)
        logger.info("Структура базы данных проверена")

    async def disconnect(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None
            logger.info("Подключение к PostgreSQL закрыто")

    def _pool(self) -> asyncpg.Pool:
        if self.pool is None:
            raise RuntimeError("База данных ещё не подключена")
        return self.pool

    async def add_user(
        self,
        user_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        referrer_id: int | None = None,
    ) -> None:
        async with self._pool().acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO users (user_id, username, first_name, last_name)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (user_id) DO UPDATE SET
                        username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name,
                        last_activity = NOW()
                    """,
                    user_id,
                    username,
                    first_name,
                    last_name,
                )

                # Реферер должен реально существовать в базе. Фиктивные записи
                # пользователей по произвольному start-параметру не создаются.
                if referrer_id and referrer_id != user_id:
                    await connection.execute(
                        """
                        INSERT INTO referrals (referrer_id, referred_id)
                        SELECT $1, $2
                        WHERE EXISTS (
                            SELECT 1 FROM users WHERE user_id = $1
                        )
                        ON CONFLICT (referred_id) DO NOTHING
                        """,
                        referrer_id,
                        user_id,
                    )

    async def user_exists(self, user_id: int) -> bool:
        async with self._pool().acquire() as connection:
            return bool(
                await connection.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM users WHERE user_id = $1)",
                    user_id,
                )
            )

    async def get_user(self, user_id: int) -> asyncpg.Record | None:
        async with self._pool().acquire() as connection:
            return await connection.fetchrow(
                "SELECT * FROM users WHERE user_id = $1",
                user_id,
            )

    async def record_activity(self, user_id: int) -> None:
        """Обновляет аналитику активности, но не продлевает жизни."""
        async with self._pool().acquire() as connection:
            await connection.execute(
                "UPDATE users SET last_activity = NOW() WHERE user_id = $1",
                user_id,
            )

    async def get_course_step(self, user_id: int) -> CourseStep | None:
        async with self._pool().acquire() as connection:
            value = await connection.fetchval(
                "SELECT course_step FROM users WHERE user_id = $1",
                user_id,
            )
        return CourseStep(value) if value is not None else None

    async def advance_course_step(
        self,
        user_id: int,
        expected_step: CourseStep,
        next_step: CourseStep,
    ) -> bool:
        """Атомарно переводит пользователя на строго следующий этап."""
        async with self._pool().acquire() as connection:
            value = await connection.fetchval(
                """
                UPDATE users
                SET course_step = $3,
                    last_activity = NOW(),
                    last_progress_at = NOW(),
                    life_deadline_at = CASE
                        WHEN course_started = TRUE AND course_completed = FALSE
                            THEN NOW() + INTERVAL '12 hours'
                        ELSE life_deadline_at
                    END
                WHERE user_id = $1
                  AND course_step = $2
                RETURNING course_step
                """,
                user_id,
                int(expected_step),
                int(next_step),
            )
            return value is not None

    async def start_course(self, user_id: int) -> bool:
        async with self._pool().acquire() as connection:
            value = await connection.fetchval(
                """
                UPDATE users
                SET course_started = TRUE,
                    course_step = $3,
                    lives = CASE WHEN course_started THEN lives ELSE 3 END,
                    extra_life_used = CASE
                        WHEN course_started THEN extra_life_used
                        ELSE FALSE
                    END,
                    last_activity = NOW(),
                    last_progress_at = NOW(),
                    life_deadline_at = NOW() + INTERVAL '12 hours'
                WHERE user_id = $1
                  AND course_step = $2
                RETURNING course_step
                """,
                user_id,
                int(CourseStep.READY),
                int(CourseStep.LESSON_1),
            )
            return value is not None

    async def get_lives(self, user_id: int) -> int:
        async with self._pool().acquire() as connection:
            value = await connection.fetchval(
                "SELECT lives FROM users WHERE user_id = $1",
                user_id,
            )
            return int(value or 0)

    async def remove_life_from_inactive_users(self) -> list[tuple[int, int, bool]]:
        """Списывает жизнь по 12-часовому таймеру реального прогресса."""
        async with self._pool().acquire() as connection:
            rows = await connection.fetch(
                """
                UPDATE users
                SET lives = GREATEST(lives - 1, 0),
                    life_deadline_at = CASE
                        WHEN lives - 1 > 0 THEN NOW() + INTERVAL '12 hours'
                        ELSE NULL
                    END
                WHERE course_started = TRUE
                  AND course_completed = FALSE
                  AND lives > 0
                  AND life_deadline_at IS NOT NULL
                  AND life_deadline_at <= NOW()
                RETURNING user_id, lives, extra_life_used
                """
            )
            return [
                (row["user_id"], row["lives"], row["extra_life_used"])
                for row in rows
            ]

    async def grant_extra_life_once(self, user_id: int) -> bool:
        """Один раз возвращает одну жизнь после полного исчерпания."""
        async with self._pool().acquire() as connection:
            value = await connection.fetchval(
                """
                UPDATE users
                SET lives = 1,
                    extra_life_used = TRUE,
                    last_activity = NOW(),
                    last_progress_at = NOW(),
                    life_deadline_at = NOW() + INTERVAL '12 hours'
                WHERE user_id = $1
                  AND course_started = TRUE
                  AND course_completed = FALSE
                  AND lives = 0
                  AND extra_life_used = FALSE
                RETURNING user_id
                """,
                user_id,
            )
            return value is not None

    async def get_test_progress(
        self,
        user_id: int,
        lesson_num: int,
    ) -> asyncpg.Record | None:
        async with self._pool().acquire() as connection:
            return await connection.fetchrow(
                """
                SELECT *
                FROM test_progress
                WHERE user_id = $1 AND lesson_num = $2
                """,
                user_id,
                lesson_num,
            )

    async def begin_or_resume_test_two(
        self,
        user_id: int,
        max_attempts: int = 3,
    ) -> dict[str, Any]:
        """Запускает новую попытку либо возвращает сохранённый вопрос."""
        async with self._pool().acquire() as connection:
            async with connection.transaction():
                user = await connection.fetchrow(
                    "SELECT course_step FROM users WHERE user_id = $1 FOR UPDATE",
                    user_id,
                )
                if user is None:
                    return {"status": "unknown"}

                step = CourseStep(user["course_step"])
                progress = await connection.fetchrow(
                    """
                    SELECT * FROM test_progress
                    WHERE user_id = $1 AND lesson_num = 2
                    FOR UPDATE
                    """,
                    user_id,
                )

                if step == CourseStep.TEST_2_ACTIVE:
                    if progress and progress["in_progress"]:
                        return {
                            "status": "resume",
                            "attempt": progress["attempt"],
                            "question_index": progress["current_question"],
                            "errors": progress["current_errors"],
                        }
                    return {"status": "wrong_step", "step": int(step)}

                if step not in (CourseStep.LESSON_2, CourseStep.TEST_2_DONE):
                    return {"status": "wrong_step", "step": int(step)}

                if progress and progress["is_passed"]:
                    return {"status": "passed"}

                previous_attempt = int(progress["attempt"]) if progress else 0
                if previous_attempt >= max_attempts:
                    return {"status": "exhausted"}

                attempt = previous_attempt + 1
                await connection.execute(
                    """
                    INSERT INTO test_progress (
                        user_id, lesson_num, attempt, in_progress,
                        current_question, current_errors, started_at, updated_at
                    )
                    VALUES ($1, 2, $2, TRUE, 0, 0, NOW(), NOW())
                    ON CONFLICT (user_id, lesson_num) DO UPDATE SET
                        attempt = EXCLUDED.attempt,
                        in_progress = TRUE,
                        current_question = 0,
                        current_errors = 0,
                        started_at = NOW(),
                        updated_at = NOW()
                    """,
                    user_id,
                    attempt,
                )
                await connection.execute(
                    """
                    UPDATE users
                    SET course_step = $2,
                        last_activity = NOW(),
                        last_progress_at = NOW(),
                        life_deadline_at = NOW() + INTERVAL '12 hours'
                    WHERE user_id = $1
                    """,
                    user_id,
                    int(CourseStep.TEST_2_ACTIVE),
                )
                return {
                    "status": "started",
                    "attempt": attempt,
                    "question_index": 0,
                    "errors": 0,
                }

    async def submit_test_two_answer(
        self,
        *,
        user_id: int,
        attempt: int,
        question_index: int,
        answer_index: int,
        correct_index: int,
        total_questions: int,
    ) -> dict[str, Any]:
        """Атомарно принимает один ожидаемый ответ и выдаёт звезду за вопрос.

        Каждый из трёх вопросов может принести пользователю не более одной
        звезды за всё время. Повторный правильный ответ, повторный callback или
        новая попытка не начисляют звезду за уже награждённый вопрос.
        """
        async with self._pool().acquire() as connection:
            async with connection.transaction():
                user = await connection.fetchrow(
                    "SELECT course_step FROM users WHERE user_id = $1 FOR UPDATE",
                    user_id,
                )
                if user is None:
                    return {"status": "unknown"}
                if CourseStep(user["course_step"]) != CourseStep.TEST_2_ACTIVE:
                    return {"status": "stale"}

                progress = await connection.fetchrow(
                    """
                    SELECT * FROM test_progress
                    WHERE user_id = $1 AND lesson_num = 2
                    FOR UPDATE
                    """,
                    user_id,
                )
                if (
                    progress is None
                    or not progress["in_progress"]
                    or int(progress["attempt"]) != attempt
                    or int(progress["current_question"]) != question_index
                ):
                    return {"status": "stale"}

                answer_correct = answer_index == correct_index
                errors = int(progress["current_errors"])
                if not answer_correct:
                    errors += 1

                reward_mask = int(progress["rewarded_questions_mask"] or 0)
                question_bit = 1 << question_index
                star_granted = answer_correct and not (reward_mask & question_bit)
                if star_granted:
                    reward_mask |= question_bit

                earned_stars = bin(reward_mask).count("1")
                next_question = question_index + 1

                if next_question < total_questions:
                    await connection.execute(
                        """
                        UPDATE test_progress
                        SET current_question = $2,
                            current_errors = $3,
                            rewarded_questions_mask = $4,
                            updated_at = NOW()
                        WHERE user_id = $1 AND lesson_num = 2
                        """,
                        user_id,
                        next_question,
                        errors,
                        reward_mask,
                    )
                    await connection.execute(
                        """
                        UPDATE users
                        SET stars = stars + $2,
                            last_activity = NOW(),
                            last_progress_at = NOW(),
                            life_deadline_at = NOW() + INTERVAL '12 hours'
                        WHERE user_id = $1
                        """,
                        user_id,
                        1 if star_granted else 0,
                    )
                    return {
                        "status": "next",
                        "attempt": attempt,
                        "question_index": next_question,
                        "errors": errors,
                        "answer_correct": answer_correct,
                        "star_granted": star_granted,
                        "earned_stars": earned_stars,
                    }

                passed = errors == 0
                await connection.execute(
                    """
                    UPDATE test_progress
                    SET correct_answers = $3,
                        total_errors = $4,
                        is_passed = is_passed OR $5,
                        in_progress = FALSE,
                        current_question = $6,
                        current_errors = $4,
                        rewarded_questions_mask = $7,
                        updated_at = NOW()
                    WHERE user_id = $1 AND lesson_num = $2
                    """,
                    user_id,
                    2,
                    total_questions - errors,
                    errors,
                    passed,
                    total_questions,
                    reward_mask,
                )
                await connection.execute(
                    """
                    UPDATE users
                    SET course_step = $2,
                        stars = stars + $3,
                        last_activity = NOW(),
                        last_progress_at = NOW(),
                        life_deadline_at = NOW() + INTERVAL '12 hours'
                    WHERE user_id = $1
                    """,
                    user_id,
                    int(CourseStep.TEST_2_DONE),
                    1 if star_granted else 0,
                )
                return {
                    "status": "complete",
                    "passed": passed,
                    "errors": errors,
                    "answer_correct": answer_correct,
                    "star_granted": star_granted,
                    "earned_stars": earned_stars,
                }

    async def try_grant_referral_reward(
        self,
        referred_id: int,
        notification_bot: Bot,
    ) -> bool:
        referrer_id: int | None = None
        async with self._pool().acquire() as connection:
            async with connection.transaction():
                referral = await connection.fetchrow(
                    """
                    SELECT referrer_id, reward_granted
                    FROM referrals
                    WHERE referred_id = $1
                    FOR UPDATE
                    """,
                    referred_id,
                )
                if not referral or referral["reward_granted"]:
                    return False

                referrer_id = int(referral["referrer_id"])
                await connection.execute(
                    """
                    UPDATE users
                    SET lives = lives + 1,
                        stars = stars + 1,
                        life_deadline_at = CASE
                            WHEN course_started = TRUE
                                 AND course_completed = FALSE
                                 AND life_deadline_at IS NULL
                                THEN NOW() + INTERVAL '12 hours'
                            ELSE life_deadline_at
                        END
                    WHERE user_id = $1
                    """,
                    referrer_id,
                )
                await connection.execute(
                    """
                    UPDATE referrals
                    SET reward_granted = TRUE
                    WHERE referred_id = $1
                    """,
                    referred_id,
                )

        try:
            await notification_bot.send_message(
                referrer_id,
                "🎉 Твой приглашённый прошёл тест! Ты получил 1 ⭐️ и 1 ❤️.",
            )
        except (TelegramForbiddenError, TelegramBadRequest):
            logger.info(
                "Не удалось отправить уведомление о реферальной награде пользователю %s",
                referrer_id,
            )
        return True

    async def delete_user_completely(self, user_id: int) -> bool:
        """Полностью удаляет пользователя и весь его прогресс курса."""
        async with self._pool().acquire() as connection:
            deleted_user_id = await connection.fetchval(
                """
                DELETE FROM users
                WHERE user_id = $1
                RETURNING user_id
                """,
                user_id,
            )

        if deleted_user_id is None:
            return False

        logger.info("Данные пользователя %s полностью сброшены", user_id)
        return True

    async def confirm_survey_once(self, user_id: int) -> bool:
        async with self._pool().acquire() as connection:
            value = await connection.fetchval(
                """
                UPDATE users
                SET survey_confirmed = TRUE,
                    course_completed = TRUE,
                    course_step = $3,
                    last_activity = NOW(),
                    last_progress_at = NOW(),
                    life_deadline_at = NULL
                WHERE user_id = $1
                  AND course_step = $2
                  AND survey_confirmed = FALSE
                RETURNING course_step
                """,
                user_id,
                int(CourseStep.SURVEY),
                int(CourseStep.COMPLETED),
            )
            return value is not None

    async def prepare_one_time_mailing(
        self,
        mailing_key: str,
        recipient_ids: tuple[int, ...],
    ) -> None:
        """Идемпотентно сохраняет список получателей одноразовой рассылки."""
        unique_ids = list(dict.fromkeys(int(user_id) for user_id in recipient_ids))
        if not unique_ids:
            return

        async with self._pool().acquire() as connection:
            await connection.execute(
                """
                INSERT INTO one_time_mailing_deliveries (mailing_key, user_id)
                SELECT $1, recipient_id
                FROM UNNEST($2::BIGINT[]) AS recipient_id
                ON CONFLICT (mailing_key, user_id) DO NOTHING
                """,
                mailing_key,
                unique_ids,
            )

    async def get_pending_one_time_mailing_users(
        self,
        mailing_key: str,
    ) -> list[int]:
        async with self._pool().acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT user_id
                FROM one_time_mailing_deliveries
                WHERE mailing_key = $1
                  AND status = 'pending'
                ORDER BY user_id
                """,
                mailing_key,
            )
        return [int(row["user_id"]) for row in rows]

    async def mark_one_time_mailing_sent(
        self,
        mailing_key: str,
        user_id: int,
    ) -> None:
        async with self._pool().acquire() as connection:
            await connection.execute(
                """
                UPDATE one_time_mailing_deliveries
                SET status = 'sent',
                    attempts = attempts + 1,
                    last_error = NULL,
                    sent_at = NOW(),
                    updated_at = NOW()
                WHERE mailing_key = $1 AND user_id = $2
                """,
                mailing_key,
                user_id,
            )

    async def mark_one_time_mailing_failed(
        self,
        mailing_key: str,
        user_id: int,
        error_text: str,
    ) -> None:
        async with self._pool().acquire() as connection:
            await connection.execute(
                """
                UPDATE one_time_mailing_deliveries
                SET status = 'failed',
                    attempts = attempts + 1,
                    last_error = $3,
                    updated_at = NOW()
                WHERE mailing_key = $1 AND user_id = $2
                """,
                mailing_key,
                user_id,
                error_text[:2000],
            )

    async def record_one_time_mailing_transient_error(
        self,
        mailing_key: str,
        user_id: int,
        error_text: str,
    ) -> None:
        """Оставляет получателя pending, чтобы повторить после сетевой ошибки."""
        async with self._pool().acquire() as connection:
            await connection.execute(
                """
                UPDATE one_time_mailing_deliveries
                SET attempts = attempts + 1,
                    last_error = $3,
                    updated_at = NOW()
                WHERE mailing_key = $1 AND user_id = $2
                """,
                mailing_key,
                user_id,
                error_text[:2000],
            )

    async def get_one_time_mailing_stats(
        self,
        mailing_key: str,
    ) -> dict[str, int]:
        async with self._pool().acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT status, COUNT(*) AS amount
                FROM one_time_mailing_deliveries
                WHERE mailing_key = $1
                GROUP BY status
                """,
                mailing_key,
            )
        return {str(row["status"]): int(row["amount"]) for row in rows}

