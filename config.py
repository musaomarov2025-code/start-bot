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

# ===== ID премиум-эмодзи =====
EMOJI = {
    "earn":      "5438496463044752972",
    "tasks":     "5427168083074628963",
    "withdraw":  "6025976946083500432",
    "profile":   "5325971446625758812",
    "go":        "5368733682917980020",
    "check":     "6026257381678124710",
    "skip":      "5260450573768990626",
    "star":      "5895708410447401643",
    "star2":     "5386367538735104399",
    "gift":      "5449800250032143374",
    "money":     "6025976946083500432",
    "fire":      "5449449325434266744",
    "user":      "5389099588906922686",
    "id":        "6030656587830399914",
    "balance":   "6030656914247914196",
    "friends":   "5258513401784573443",
    "hourglass": "5386367538735104399",
    "trophy":    "5474419165781597383",
    "down":      "5231102735817918643",
    "lock":      "5258093637450866522",
    "point":     "6026034017608930629",
    "palm":      "5470177992950946662",
    "ok":        "5980930633298350051",
    "no":        "5765005318610228026",
    "congrat":   "5350460637182993292",
    "update":    "5920433463428650761",
    "heart":     "5193018401810822951",
    "shine":     "5469744063815102906",
}


def e(key, fallback="⭐"):
    eid = EMOJI.get(key, "")
    if not eid:
        return fallback
    return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'


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
    # --- базовые ---
    "daily_bonus": "1",
    "min_withdraw": "15",
    "welcome_text": "Главное меню 👇",

    # --- приватка ---
    "priv_enabled": "1",
    "priv_text": "🚹 <b>Укажи свой пол</b> ⤵️",
    "priv_buttons": (
        "👦 Я парень - https://t.me/RuletkaMatchBot?start=savikpriv2509\n"
        "👧 Я девушка - https://t.me/RuletkaMatchBot?start=savikpriv2509"
    ),

    # --- Botohub ОП (на выводе) ---
    "botohub_enabled": "1",
    "botohub_entry_count": "6",
    "botohub_withdraw_count": "6",
    "botohub_text": (
        '<tg-emoji emoji-id="5258093637450866522">🔒</tg-emoji> '
        'Для использования бота подпишись на каналы ниже\n\n'
        '<tg-emoji emoji-id="6026034017608930629">👉</tg-emoji> '
        'После подписки нажимай на кнопку '
        '"<tg-emoji emoji-id="6026257381678124710">✅</tg-emoji> Я Подписался"'
    ),
    "botohub_btn_text": "Подписаться",

    # --- ОП на старте (свои каналы) ---
    "op_text": (
        '<tg-emoji emoji-id="5258093637450866522">🔒</tg-emoji> '
        'Для использования бота подпишись на каналы ниже\n\n'
        '<tg-emoji emoji-id="6026034017608930629">👉</tg-emoji> '
        'После подписки нажимай на кнопку '
        '"<tg-emoji emoji-id="6026257381678124710">✅</tg-emoji> Я Подписался"'
    ),
    "op_btn_sub": "Подписаться",
    "op_btn_done": "Я подписался",

    # --- Задания (общие) ---
    "tasks_enabled": "1",
    "task_reward": "0.45",
    "task_text": (
        '<tg-emoji emoji-id="5449449325434266744">❄️</tg-emoji> '
        '<b>Собирай Звёзды за простые задания!</b> '
        '<tg-emoji emoji-id="5470177992950946662">👇</tg-emoji>\n\n'
        '<tg-emoji emoji-id="5980930633298350051">✅</tg-emoji> '
        'Подпишись на канал и нажми «Проверить»\n\n'
        '<tg-emoji emoji-id="5765005318610228026">❌</tg-emoji> '
        'За отписку или блокировку ресурса, вы получите бан\n\n'
        '<b>Вознаграждение: +{reward} '
        '<tg-emoji emoji-id="5386367538735104399">⭐️</tg-emoji></b>'
    ),
    "task_btn_go": "Перейти",
    "task_btn_check": "Проверить",
    "task_btn_skip": "Пропустить",
    "task_done_text": (
        '<tg-emoji emoji-id="5350460637182993292">🎉</tg-emoji> '
        '<b>Ты молодец, выполнены все доступные задания!</b>\n\n'
        '<tg-emoji emoji-id="5920433463428650761">🔄</tg-emoji> '
        'Новые задания скоро появятся…\n\n'
        '<tg-emoji emoji-id="5449800250032143374">💖</tg-emoji> '
        'За друга платим больше — +{bonus} '
        '<tg-emoji emoji-id="5386367538735104399">⭐️</tg-emoji>'
    ),
    "task_reward_text": (
        '<tg-emoji emoji-id="6026257381678124710">✅</tg-emoji> '
        '<b>Задание выполнено!</b>\n\n'
        '<tg-emoji emoji-id="6025976946083500432">💰</tg-emoji> '
        'Награда: <b>+{reward}</b> '
        '<tg-emoji emoji-id="5386367538735104399">⭐️</tg-emoji>\n'
        '<tg-emoji emoji-id="5427168083074628963">💎</tg-emoji> '
        'Баланс: <b>{balance}</b> '
        '<tg-emoji emoji-id="5386367538735104399">⭐️</tg-emoji>'
    ),

    # --- Рефералка за 5 заданий ---
    "ref_tasks_enabled": "1",
    "ref_tasks_required": "5",
    "ref_tasks_bonus": "3",
    "ref_deadline_days": "7",

    # --- Тексты для реферала ---
    "earn_text": (
        '<tg-emoji emoji-id="5386367538735104399">⭐️</tg-emoji> '
        '<b>Получай +{bonus} за каждого приглашенного друга!</b>\n\n'
        '<tg-emoji emoji-id="5260730055880876557">📎</tg-emoji> '
        '<b>Твоя реферальная ссылка:</b>\n{link}\n\n'
        '<blockquote>'
        '<tg-emoji emoji-id="5361948905900635660">✨</tg-emoji> '
        '<b>Как это работает:</b>\n'
        '1️⃣ Отправь свою ссылку другу\n'
        '2️⃣ Друг заходит и выполняет 5 заданий\n'
        '3️⃣ Ты получаешь +{bonus} автоматически!'
        '</blockquote>\n\n'
        '<tg-emoji emoji-id="5258513401784573443">👥</tg-emoji> '
        'Приглашено вами: <b>{count}</b>'
    ),
    "earn_btn": "Пригласить друга",

    # --- Уведомления рефереру ---
    "ref_notify_start": (
        '<tg-emoji emoji-id="5193018401810822951">🎉</tg-emoji> '
        '<b>По твоей ссылке зашёл @{username}!</b>\n\n'
        'Он должен выполнить 5 заданий, чтобы ты получил награду.'
    ),
    "ref_notify_5min": (
        '<tg-emoji emoji-id="5920433463428650761">⏳</tg-emoji> '
        '<b>@{username}</b> зашёл по твоей ссылке, '
        'но пока не начал пользоваться ботом.'
    ),
    "ref_notify_10min": (
        '<tg-emoji emoji-id="5469744063815102906">💪</tg-emoji> '
        '<b>@{username}</b> идёт к цели: '
        '<b>{done}/{need}</b> заданий'
    ),
    "ref_notify_done": (
        '<tg-emoji emoji-id="5193018401810822951">🎉</tg-emoji> '
        '<b>@{username} выполнил 5 заданий!</b>\n\n'
        '<tg-emoji emoji-id="5469744063815102906">💫</tg-emoji> '
        'Тебе начислено <b>+{bonus}</b> '
        '<tg-emoji emoji-id="5386367538735104399">⭐️</tg-emoji>'
    ),
}
