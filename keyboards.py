from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

from config import GIFTS, GIFTS_ORDER, PRIVATKA_URL
from database import get_channels


# ============ ПОЛЬЗОВАТЕЛЬСКИЕ ============
def main_menu():
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text="⭐ Заработать звёзды")],
        [KeyboardButton(text="💸 Вывести звёзды")],
        [KeyboardButton(text="🏆 Лидеры"), KeyboardButton(text="👤 Профиль")],
    ])


def gender_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👦 Я парень", url=PRIVATKA_URL)],
        [InlineKeyboardButton(text="👧 Я девушка", url=PRIVATKA_URL)],
    ])


def sub_kb(channels):
    buttons = []
    for i, ch in enumerate(channels, 1):
        chat_id = ch[1]
        link = ch[3]
        url = link if link else f"https://t.me/{chat_id.lstrip('@')}"
        buttons.append([InlineKeyboardButton(text=f"📢 Подписаться {i}", url=url)])
    buttons.append([InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def withdraw_sub_kb(channels):
    buttons = []
    for i, ch in enumerate(channels, 1):
        chat_id = ch[1]
        link = ch[3]
        url = link if link else f"https://t.me/{chat_id.lstrip('@')}"
        buttons.append([InlineKeyboardButton(text=f"📢 Подписаться {i}", url=url)])
    buttons.append([InlineKeyboardButton(text="✅ Подтвердить", callback_data="wd_confirm_sub")])
    buttons.append([InlineKeyboardButton(text="❌ Отменить", callback_data="wd_cancel_sub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def earn_kb(share_url):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Пригласить друга", url=share_url)],
    ])


def profile_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Ежедневный бонус", callback_data="daily_bonus")],
        [InlineKeyboardButton(text="🎟 Ввести промокод", callback_data="enter_promo")],
    ])


def gifts_kb():
    buttons = []
    row = []
    for key in GIFTS_ORDER:
        if key not in GIFTS:
            continue
        name, price = GIFTS[key]
        row.append(InlineKeyboardButton(
            text=f"{name} · {price}⭐",
            callback_data=f"gift:{key}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ============ АДМИНСКИЕ ============
def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Каналы на входе", callback_data="ch_list:start")],
        [InlineKeyboardButton(text="💰 Каналы на вывод", callback_data="ch_list:withdraw")],
        [InlineKeyboardButton(text="📋 Заявки на вывод", callback_data="wd_list")],
        [InlineKeyboardButton(text="🎟 Промокоды", callback_data="promos")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
    ])


def channels_kb(ch_type):
    rows = get_channels(ch_type)
    buttons = []
    for ch in rows:
        cid = ch[0]
        title = ch[2]
        bot_admin = ch[4] if len(ch) > 4 else 0
        icon = "🟢" if bot_admin else "🟡"
        buttons.append([InlineKeyboardButton(text=f"{icon} {title}", callback_data=f"ch_view:{cid}")])
    buttons.append([InlineKeyboardButton(text="➕ Добавить канал", callback_data=f"ch_add:{ch_type}")])
    if rows:
        buttons.append([InlineKeyboardButton(text="🗑 Удалить канал", callback_data=f"ch_del_list:{ch_type}")])
    buttons.append([InlineKeyboardButton(text="🧹 Очистить все", callback_data=f"ch_clear:{ch_type}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def channels_delete_kb(ch_type):
    rows = get_channels(ch_type)
    buttons = []
    for ch in rows:
        cid = ch[0]
        title = ch[2]
        buttons.append([InlineKeyboardButton(text=f"❌ {title}", callback_data=f"ch_del:{cid}:{ch_type}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"ch_list:{ch_type}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_wd_kb(wid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"wd_ok:{wid}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"wd_no:{wid}"),
        ]
    ])


def settings_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Бонус за реферала", callback_data="set:ref_bonus")],
        [InlineKeyboardButton(text="🎁 Ежедневный бонус", callback_data="set:daily_bonus")],
        [InlineKeyboardButton(text="💸 Минимум вывода", callback_data="set:min_withdraw")],
        [InlineKeyboardButton(text="✏️ Текст под меню", callback_data="set:welcome_text")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


def promos_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать промокод", callback_data="promo_create")],
        [InlineKeyboardButton(text="📜 Список промокодов", callback_data="promo_list")],
        [InlineKeyboardButton(text="🗑 Удалить промокод", callback_data="promo_delete")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


def back_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])
