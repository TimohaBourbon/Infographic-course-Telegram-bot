CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    lives INTEGER NOT NULL DEFAULT 3 CHECK (lives >= 0),
    stars INTEGER NOT NULL DEFAULT 0 CHECK (stars >= 0),
    course_started BOOLEAN NOT NULL DEFAULT FALSE,
    course_completed BOOLEAN NOT NULL DEFAULT FALSE,
    survey_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    course_step SMALLINT NOT NULL DEFAULT 0 CHECK (course_step BETWEEN 0 AND 12),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_activity TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_progress_at TIMESTAMPTZ,
    life_deadline_at TIMESTAMPTZ,
    extra_life_used BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS test_progress (
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    lesson_num INTEGER NOT NULL,
    attempt INTEGER NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    correct_answers INTEGER NOT NULL DEFAULT 0 CHECK (correct_answers >= 0),
    total_errors INTEGER NOT NULL DEFAULT 0 CHECK (total_errors >= 0),
    is_passed BOOLEAN NOT NULL DEFAULT FALSE,
    in_progress BOOLEAN NOT NULL DEFAULT FALSE,
    current_question INTEGER NOT NULL DEFAULT 0 CHECK (current_question >= 0),
    current_errors INTEGER NOT NULL DEFAULT 0 CHECK (current_errors >= 0),
    rewarded_questions_mask INTEGER NOT NULL DEFAULT 0
        CHECK (rewarded_questions_mask BETWEEN 0 AND 7),
    started_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, lesson_num)
);

CREATE TABLE IF NOT EXISTS referrals (
    referred_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    referrer_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    reward_granted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (referrer_id <> referred_id)
);

-- Безопасные миграции для базы, созданной более ранней версией бота.
ALTER TABLE users ADD COLUMN IF NOT EXISTS course_step SMALLINT NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_progress_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS life_deadline_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS extra_life_used BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE test_progress ADD COLUMN IF NOT EXISTS in_progress BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE test_progress ADD COLUMN IF NOT EXISTS current_question INTEGER NOT NULL DEFAULT 0;
ALTER TABLE test_progress ADD COLUMN IF NOT EXISTS current_errors INTEGER NOT NULL DEFAULT 0;
ALTER TABLE test_progress ADD COLUMN IF NOT EXISTS rewarded_questions_mask INTEGER NOT NULL DEFAULT 0;
ALTER TABLE test_progress ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'test_progress_rewarded_questions_mask_check'
          AND conrelid = 'test_progress'::regclass
    ) THEN
        ALTER TABLE test_progress
            ADD CONSTRAINT test_progress_rewarded_questions_mask_check
            CHECK (rewarded_questions_mask BETWEEN 0 AND 7);
    END IF;
END
$$;

-- Пользователи, прошедшие тест в старой версии, уже получили общую награду
-- в 3 звезды. Помечаем все три вопроса награждёнными, чтобы после обновления
-- нельзя было получить эти звёзды повторно.
UPDATE test_progress
SET rewarded_questions_mask = 7
WHERE lesson_num = 2
  AND is_passed = TRUE
  AND rewarded_questions_mask = 0;

-- Для существующих пользователей восстанавливаем разумную стартовую точку.
UPDATE users
SET course_step = CASE
    WHEN course_completed OR survey_confirmed THEN 12
    WHEN course_started AND course_step = 0 THEN 4
    ELSE course_step
END;

UPDATE users u
SET course_step = 7
FROM test_progress t
WHERE t.user_id = u.user_id
  AND t.lesson_num = 2
  AND t.in_progress = TRUE
  AND u.course_completed = FALSE;

UPDATE users u
SET course_step = 8
FROM test_progress t
WHERE t.user_id = u.user_id
  AND t.lesson_num = 2
  AND t.in_progress = FALSE
  AND t.attempt > 0
  AND u.course_completed = FALSE
  AND u.course_step < 8;

UPDATE users
SET last_progress_at = COALESCE(last_progress_at, last_activity)
WHERE course_started = TRUE;

UPDATE users
SET life_deadline_at = last_progress_at + INTERVAL '12 hours'
WHERE course_started = TRUE
  AND course_completed = FALSE
  AND lives > 0
  AND last_progress_at IS NOT NULL
  AND (
      life_deadline_at IS NULL
      OR life_deadline_at > last_progress_at + INTERVAL '12 hours'
  );

CREATE INDEX IF NOT EXISTS idx_users_last_activity
    ON users(last_activity);

CREATE INDEX IF NOT EXISTS idx_users_life_deadline
    ON users(life_deadline_at)
    WHERE course_started = TRUE AND course_completed = FALSE AND lives > 0;

CREATE INDEX IF NOT EXISTS idx_referrals_referrer_id
    ON referrals(referrer_id);

-- Состояние адресной одноразовой рассылки. Таблица не связана внешним ключом
-- с users, потому что получатели взяты из предыдущего запуска курса.
CREATE TABLE IF NOT EXISTS one_time_mailing_deliveries (
    mailing_key TEXT NOT NULL,
    user_id BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'sent', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error TEXT,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (mailing_key, user_id)
);

CREATE INDEX IF NOT EXISTS idx_one_time_mailing_pending
    ON one_time_mailing_deliveries (mailing_key, status);

