import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = 8742164697
DB = "bot.db"

BOTOHUB_TOKEN = "1196d848-7318-4c55-a643-bc0d2e709525"
BOTOHUB_URL = "https://botohub.me/get-tasks-extended"
BOTOHUB_TASKS_URL = "https://botohub.me/get-tasks"

REFERRAL_DAYS = 7
REFERRAL_REMIND_MIN = 3
JOIN_REQUEST_HOURS = 24

GIFTS = {
    "bear":    ("Мишка",   15),
    "heart":   ("Сердце",  15),
    "gift":    ("Подарок", 25),
    "rose":    ("Роза",    25),
    "cake":    ("Торт",    50),
    "rocket":  ("Ракета",  50),
    "ring":    ("Кольцо",  100),
    "diamond": ("Алмаз",   100),
}

GIFTS_EMOJI = {
    "bear":    "5206502842478638898",
    "heart":   "5192879906295397710",
    "gift":    "5449800250032143374",
    "rose":    "5363938656874673963",
    "cake":    "5452055425690123301",
    "rocket":  "5188481279963715781",
    "ring":    "5458839914944672851",
    "diamond": "5427168083074628963",
}

GIFTS_ORDER = ["bear", "heart", "gift", "rose", "cake", "rocket", "ring", "diamond"]

DEFAULTS = {
    "ref_bonus": "6",
    "daily_bonus": "1",
    "min_withdraw": "15",
    "welcome_text": "Главное меню 👇",
    "priv_enabled": "1",
    "priv_text": "🚹 <b>Укажи свой пол</b> ⤵️",
    "priv_buttons": (
        "👦 Я парень - https://t.me/RuletkaMatchBot?start=savikpriv2509\n"
        "👧 Я девушка - https://t.me/RuletkaMatchBot?start=savikpriv2509"
    ),
    "botohub_enabled": "1",
    "botohub_entry_count": "6",
    "botohub_withdraw_count": "6",
    "botohub_text": (
        '<tg-emoji emoji-id="5258093637450866522">🔒</tg-emoji> Для использования бота подпишись на каналы ниже\n\n'
        '<tg-emoji emoji-id="6026034017608930629">👉</tg-emoji> После подписки нажимай на кнопку '
        '"<tg-emoji emoji-id="6026257381678124710">✅</tg-emoji> Я Подписался"'
    ),
    "botohub_btn_text": "Подписаться",
    "tasks_enabled": "1",
    "task_reward": "1",
}
