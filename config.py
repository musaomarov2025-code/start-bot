import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = 8742164697
DB = "bot.db"

# Botohub — токен бота
BOTOHUB_TOKEN = "1196d848-7318-4c55-a643-bc0d2e709525"
BOTOHUB_URL = "https://botohub.me/get-tasks-extended"

# Flyer — ключ для заданий
FLYER_KEY = "FL-EzEoBC-PzGpeD-seLIsD-kHEwfN"
FLYER_URL = "https://api.flyerhubs.com/check"

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

    # Botohub — ОП
    "botohub_enabled": "1",
    "botohub_entry_count": "6",      # спонсоров на входе
    "botohub_withdraw_count": "6",   # спонсоров на выводе
    "botohub_text": "✨ <b>Подпишись на спонсоров ниже</b>\n\nПосле подписки нажми «✅ Подтвердить» 👇",
    "botohub_btn_text": "📢 Спонсор",

    # Flyer — задания
    "flyer_enabled": "1",
    "flyer_task_reward": "10",       # награда за задание
}
