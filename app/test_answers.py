import json
import os


raw_questions = os.getenv("TEST_2_QUESTIONS_JSON", "").strip()
if not raw_questions:
    raise RuntimeError("Переменная окружения TEST_2_QUESTIONS_JSON не задана")

TEST_2_QUESTIONS = json.loads(raw_questions)
