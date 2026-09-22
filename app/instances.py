from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import ADMIN_BOT_TOKEN, BOT_TOKEN, DATABASE_DSN, SCHEMA_FILE
from app.database import Database


bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML"),
)
dp = Dispatcher(storage=MemoryStorage())

support_admin_bot = Bot(
    token=ADMIN_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML"),
)
support_admin_dp = Dispatcher(storage=MemoryStorage())

db = Database(DATABASE_DSN, SCHEMA_FILE)
