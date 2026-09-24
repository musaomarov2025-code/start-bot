import os

# ============ НАСТРОЙКИ БОТА ============
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = 8742164697

DB = "bot.db"

# Flyer — дефолтный ключ (можно менять из админки)
FLYER_KEY = "FL-EzEoBC-PzGpeD-seLIsD-kHEwfN"

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
    # Экономика
    "ref_bonus": "35",
    "daily_bonus": "1",
    "min_withdraw": "15",

    # Меню
    "welcome_text": "Главное меню 👇",

    # Приватка (первое сообщение после /start)
    "priv_enabled": "1",
    "priv_text": "🚹 <b>Укажи свой пол</b> ⤵️",
    "priv_buttons": (
        "👦 Я парень - https://t.me/vsetut_topbot?start=chekpointop0408"
        " & 👧 Я девушка - https://t.me/vsetut_topbot?start=chekpointop0408"
    ),

    # Flyer
    "flyer_key": FLYER_KEY,
    "flyer_enabled": "1",
    "flyer_text": "📢 <b>Подпишись на спонсоров ниже</b> ⤵️",
    "flyer_button_text": "📢 Подпишись",
    "flyer_rows": "2",
}
