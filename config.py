import os

# ============ НАСТРОЙКИ БОТА ============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = 8742164697

DB = "bot.db"

# Приватка (выбор пола)
PRIVATKA_URL = "https://t.me/vsetut_topbot?start=chekpointop0408"

# Рефералы
REFERRAL_DAYS = 7
REFERRAL_REMIND_MIN = 3
JOIN_REQUEST_HOURS = 24

# ============ ПОДАРКИ ============
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

# ============ ДЕФОЛТНЫЕ НАСТРОЙКИ ============
DEFAULTS = {
    "ref_bonus": "35",
    "daily_bonus": "1",
    "min_withdraw": "15",
    "welcome_text": "Главное меню 👇",
}
