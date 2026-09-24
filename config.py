import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = 8742164697
DB = "bot.db"

# PiarFlow
PIARFLOW_API_KEY = "cbxqaAcWQgT7ogU34d8lxiRO8Bc1oQyl"
PIARFLOW_BASE_URL = "https://piarflow.com/v1"

REFERRAL_DAYS = 7
REFERRAL_REMIND_MIN = 3
JOIN_REQUEST_HOURS = 24

GIFTS = {
    "bear":    ("🧸 Мишка",   15),
    "heart":   ("❤️ Сердце",  15),
    "gift":    ("🎁 Подарок", 25),
    "rose":    ("🌹 Роза",    25),
    "cake":    ("🎂 Торт",    50),
    "rocket":  ("🚀 Ракета",  50),
    "ring":    ("💍 Кольцо",  100),
    "diamond": ("💎 Алмаз",   100),
}

GIFTS_ORDER = ["bear", "heart", "gift", "rose", "cake", "rocket", "ring", "diamond"]

DEFAULTS = {
    "ref_bonus": "35",
    "daily_bonus": "1",
    "min_withdraw": "15",
    "welcome_text": "Главное меню 👇",

    "priv_enabled": "1",
    "priv_text": "🚹 <b>Укажи свой пол</b> ⤵️",
    "priv_buttons": (
        "👦 Я парень - https://t.me/vsetut_topbot?start=chekpointop0408"
        " & 👧 Я девушка - https://t.me/vsetut_topbot?start=chekpointop0408"
    ),

    # PiarFlow
    "piarflow_key": PIARFLOW_API_KEY,
    "piarflow_enabled": "1",
    "piarflow_entry_count": "6",
    "piarflow_withdraw_count": "6",
    "piarflow_task_reward": "10",
}
