import os

# ============ НАСТРОЙКИ БОТА ============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = 8742164697

DB = "bot.db"

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

    # Приватка — первое сообщение после /start
    "priv_enabled": "1",
    "priv_text": "🚹 <b>Укажи свой пол</b> ⤵️",
    "priv_buttons": (
        "👦 Я парень - https://t.me/vsetut_topbot?start=chekpointop0408"
        " & 👧 Я девушка - https://t.me/vsetut_topbot?start=chekpointop0408"
    ),

    # Приветствие + ОП — второе сообщение после /start
    "greeting_text": (
        "💚 <b>Привет, {name}!</b> Тут можно получать подарки 🎁\n\n"
        "✅ Подпишись на спонсоров ниже, чтобы войти в бота "
        "и забрать 🧸 мишку!"
    ),
}
