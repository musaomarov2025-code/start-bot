from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

from config import GIFTS, GIFTS_ORDER


# ============ ПОЛЬЗОВАТЕЛЬСКИЕ ============
def main_menu():
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text="⭐ Заработать звёзды")],
        [KeyboardButton(text="💸 Вывести звёзды")],
        [KeyboardButton(text="📋 Задания"), KeyboardButton(text="👤 Профиль")],
    ])


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


def task_kb(link, source):
    """source — 'piarflow' или ID своего задания"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Перейти", url=link),
         InlineKeyboardButton(text="⏭ Пропустить", callback_data="task_skip")],
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"task_check:{source}")],
    ])


# ============ АДМИНСКИЕ ============
def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 PiarFlow", callback_data="piarflow_menu"),
         InlineKeyboardButton(text="📋 Заявки", callback_data="wd_list")],
        [InlineKeyboardButton(text="📜 История", callback_data="wd_history"),
         InlineKeyboardButton(text="🎛 Приватка", callback_data="priv_menu")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="broadcast"),
         InlineKeyboardButton(text="🎟 Промокоды", callback_data="promos")],
        [InlineKeyboardButton(text="📌 Свои задания", callback_data="tasks_menu"),
         InlineKeyboardButton(text="💸 Начислить", callback_data="give_start")],
        [InlineKeyboardButton(text="👥 Юзер", callback_data="user_find"),
         InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings"),
         InlineKeyboardButton(text="📦 Бэкап", callback_data="backup_help")],
    ])


def piarflow_kb(enabled):
    status = "🔴 Выключить" if enabled else "🟢 Включить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Ключ", callback_data="pf_edit_key"),
         InlineKeyboardButton(text="💰 Награда за задание", callback_data="pf_edit_reward")],
        [InlineKeyboardButton(text="📥 ОП на входе", callback_data="pf_edit_entry"),
         InlineKeyboardButton(text="💸 ОП на выводе", callback_data="pf_edit_wd")],
        [InlineKeyboardButton(text=status, callback_data="pf_toggle")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


def admin_wd_kb(wid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"wd_ok:{wid}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"wd_no:{wid}"),
        ]
    ])


def priv_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить текст", callback_data="priv_edit_text")],
        [InlineKeyboardButton(text="🔗 Настроить кнопки", callback_data="priv_edit_buttons")],
        [InlineKeyboardButton(text="🗑 Удалить приватку", callback_data="priv_delete")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


def broadcast_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить всем", callback_data="broadcast_confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back")],
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


def tasks_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить задание", callback_data="task_add")],
        [InlineKeyboardButton(text="📜 Список заданий", callback_data="task_list")],
        [InlineKeyboardButton(text="🗑 Удалить задание", callback_data="task_delete")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


def user_view_kb(uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Список рефералов", callback_data=f"user_refs:{uid}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


def back_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])
