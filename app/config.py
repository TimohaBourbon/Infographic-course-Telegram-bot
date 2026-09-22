import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Переменная окружения {name} не задана")
    return value


BOT_TOKEN = _required_env("BOT_TOKEN")
ADMIN_BOT_TOKEN = _required_env("ADMIN_BOT_TOKEN")
DATABASE_DSN = _required_env("DATABASE_DSN")
COURSE_CHANNEL_ID = _required_env("COURSE_CHANNEL_ID")
COURSE_CHANNEL_URL = _required_env("COURSE_CHANNEL_URL")
COURSE_INTRO_URL = _required_env("COURSE_INTRO_URL")
SURVEY_URL = _required_env("SURVEY_URL")
LESSON_1_URL = _required_env("LESSON_1_URL")
LESSON_2_URL = _required_env("LESSON_2_URL")
LESSON_3_URL = _required_env("LESSON_3_URL")
FIGMA_TEMPLATE_URL = _required_env("FIGMA_TEMPLATE_URL")
FINAL_BONUS_VIDEO_URL = _required_env("FINAL_BONUS_VIDEO_URL")

SUPPORT_ADMINS = [
    int(value.strip())
    for value in os.getenv("SUPPORT_ADMINS", "").split(",")
    if value.strip().isdigit()
]

GOOGLE_SHEETS_DB_SPREADSHEET_ID = os.getenv(
    "GOOGLE_SHEETS_DB_SPREADSHEET_ID", ""
).strip()
SHEETS_SYNC_INTERVAL_SECONDS = max(
    60,
    int(os.getenv("SHEETS_SYNC_INTERVAL_SECONDS", "3600")),
)

APP_DIR = Path(__file__).resolve().parent
LIFE_IMAGES_DIR = APP_DIR / "life_images"
SCHEMA_FILE = APP_DIR / "schema.sql"

GUIDE_FIGMA_FILE = Path(_required_env("GUIDE_FIGMA_FILE"))
LESSON_1_BRIEF_FILE = Path(_required_env("LESSON_1_BRIEF_FILE"))
EXCLUSIVE_BONUS_FILE = Path(_required_env("EXCLUSIVE_BONUS_FILE"))

LIFE_MESSAGES = {
    2: """Ты куда пропал?

Прошло 12 часов, поэтому одна жизнь сгорает.

❤️❤️🤍 2/3 жизни

Скорей следуй дальше: в следующем уроке я показываю то, что позволяет брать проекты от 18 000 ₽ без бесконечных правок и унижения.
Клиенты платят не за то, что вы привыкли делать!
У тебя есть 12 часов, чтобы продолжить обучение.""",
    1: """😔 Уже начинаю скучать.

Прошла еще одна половина суток, а значит, ты теряешь вторую жизнь.

❤️🤍🤍 1/3 жизни

Самое интересное впереди.
Ты уже близок к пониманию, как вернуться в строй на рынок инфографики в сегодняшние дни, и стать конкурентоспособным, обогнав дизайнеров уровнем выше.

Продолжи с самого интересного места:""",
    0: """Зацени стих:

Уроки ждали, время шло,
Но что-то вновь не повезло.
Последний таймер прозвенел —
И доступ тихо улетел...

Ладно, теперь серьезно:

❤️🤍🤍 → 🤍🤍🤍
Жизни закончились.

А вместе с ними закрылся доступ к курсу, где я показываю систему создания инфографики, которая помогает влиять на CTR и конверсию, а не просто делать красивый дизайн.

Но я готова дать тебе еще один шанс.
Нажми кнопку ниже и получи дополнительную жизнь.
Только один раз.""",
}

EXTRA_LIFE_GRANTED_MESSAGE = """🎉 Дополнительная жизнь начислена!

❤️🤍🤍 1/3 жизни

Доступ к курсу снова открыт.
Но это действительно последний шанс.

Следующие 12 часов решают, останешься ли ты дизайнером, который продает только картинки, или пойдёшь в «специалисты» с точным пониманием, за что клиенты готовы платить больше.

Жду тебя внутри 👇"""

EXTRA_LIFE_EXPIRED_MESSAGE = """Ну вот и всё...
Я дала тебе дополнительную жизнь, но и она закончилась.

🔒 Доступ к курсу закрыт.

Жаль, потому что ты не дошел до материалов о том:
— что на самом деле покупает клиент;
— как создавать инфографику, которая влияет на продажи;
— как выходить на чеки от 18 000 ₽ без блога и огромной аудитории и так далее.

Но выход есть.
Пригласи друга по своей реферальной ссылке, и доступ будет восстановлен.

Твоя ссылка:
{referral_link}"""

LIFE_IMAGES = {
    2: "image2.png",
    0: "image3.png",
}
