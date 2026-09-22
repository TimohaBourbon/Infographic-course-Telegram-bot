from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import COURSE_CHANNEL_URL


inline_start = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Канал", url=COURSE_CHANNEL_URL)],
        [InlineKeyboardButton(text="Подписался", callback_data="subscribed")],
    ]
)

inline_hello = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Далее", callback_data="figma_knowledge_level")]
    ]
)

inline_rookie_guide = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="ДА", callback_data="rookie_guide_yes")],
        [InlineKeyboardButton(text="НЕТ", callback_data="rookie_guide_no")],
    ]
)

inline_ready_to_start = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="НАЧАТЬ", callback_data="ready")]
    ]
)

inline_finish_lesson_1 = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="забрать бонусы", callback_data="lesson_1_done")]
    ]
)

inline_next_lesson_2 = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Перейти ко 2 уроку", callback_data="second_lesson")]
    ]
)

inline_start_test_2 = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="начать тест", callback_data="test_2_start")]
    ]
)

inline_next_lesson_3 = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Перейти к 3 уроку", callback_data="third_lesson")]
    ]
)

inline_finish_lesson_3 = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="забрать подарок", callback_data="lesson_3_done")]
    ]
)

inline_next_bonus = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="К СЛЕДУЮЩЕМУ БОНУСУ", callback_data="next_bonus")]
    ]
)


inline_continue_course = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="ПРОДОЛЖИТЬ КУРС", callback_data="life_continue")]
    ]
)

inline_get_extra_life = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="ПОЛУЧИТЬ ЖИЗНЬ", callback_data="get_extra_life")]
    ]
)


def build_survey_keyboard(survey_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="ЗАПОЛНИТЬ АНКЕТУ", url=survey_url)],
            [InlineKeyboardButton(text="Я ЗАПОЛНИЛ", callback_data="survey_completed")],
        ]
    )


def build_answer_keyboard(
    attempt: int,
    question_index: int,
    num_options: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=str(answer_index + 1),
                    callback_data=(
                        f"test2:{attempt}:{question_index}:{answer_index}"
                    ),
                )
            ]
            for answer_index in range(num_options)
        ]
    )


inline_retry_test_2 = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Начать снова", callback_data="second_test_again")],
        [InlineKeyboardButton(text="Идем далее", callback_data="third_lesson")],
    ]
)


def support_reply_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Ответить", callback_data=f"sup:hint:{user_id}")]
        ]
    )
