from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from config import GIFTS, GIFTS_ORDER, GIFTS_EMOJI


def main_menu():
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text="Заработать звёзды", icon_custom_emoji_id="5438496463044752972")],
        [KeyboardButton(text="Вывести звёзды", icon_custom_emoji_id="6025976946083500432")],
        [KeyboardButton(text="Задания", icon_custom_emoji_id="5427168083074628963"),
         KeyboardButton(text="Профиль", icon_custom_emoji_id="5325971446625758812")],
    ])


def earn_kb(share_url):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пригласить друга", url=share_url, icon_custom_emoji_id="5258362837411045098")],
    ])


def profile_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ежедневный бонус", callback_data="daily_bonus", icon_custom_emoji_id="5449800250032143374")],
        [InlineKeyboardButton(text="Ввести промокод", callback_data="enter_promo", icon_custom_emoji_id="5197468864102823838")],
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
            callback_data=f"gift:{key}",
            icon_custom_emoji_id=GIFTS_EMOJI.get(key)
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def task_kb(link, source="bh"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Перейти", url=link, icon_custom_emoji_id="5368733682917980020"),
         InlineKeyboardButton(text="Пропустить", callback_data="task_skip", icon_custom_emoji_id="5260450573768990626")],
        [InlineKeyboardButton(text="Подтвердить", callback_data=f"tc:{source}", icon_custom_emoji_id="6026257381678124710")],
    ])


def daily_bonus_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Забрать", callback_data="daily_claim", icon_custom_emoji_id="6026257381678124710")],
        [InlineKeyboardButton(text="Назад", callback_data="daily_cancel", icon_custom_emoji_id="5258236805890710909")],
    ])


def daily_back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="daily_back", icon_custom_emoji_id="5258236805890710909")],
    ])


def promo_cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отмена", callback_data="promo_cancel", icon_custom_emoji_id="5210952531676504517")],
    ])


def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Botohub ОП", callback_data="bh_menu"),
         InlineKeyboardButton(text="📋 Заявки", callback_data="wd_list")],
        [InlineKeyboardButton(text="📜 История", callback_data="wd_history"),
         InlineKeyboardButton(text="🎛 Приватка", callback_data="priv_menu")],
        [InlineKeyboardButton(text="🎯 Задания Botohub", callback_data="tasks_menu"),
         InlineKeyboardButton(text="📌 Свои задания", callback_data="ctasks_menu")],
        [InlineKeyboardButton(text="📌 Свои ОП", callback_data="cop_menu"),
         InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="broadcast"),
         InlineKeyboardButton(text="🎟 Промокоды", callback_data="promos")],
        [InlineKeyboardButton(text="💸 Начислить", callback_data="give_start"),
         InlineKeyboardButton(text="👥 Юзер", callback_data="user_find")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings"),
         InlineKeyboardButton(text="📦 Бэкап", callback_data="backup_help")],
    ])


def bh_kb(enabled):
    status = "🔴 Выключить" if enabled else "🟢 Включить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Текст сообщения", callback_data="bh_edit_text"),
         InlineKeyboardButton(text="🔤 Текст кнопок", callback_data="bh_edit_btn")],
        [InlineKeyboardButton(text="📥 ОП на входе", callback_data="bh_edit_entry"),
         InlineKeyboardButton(text="💸 ОП на выводе", callback_data="bh_edit_wd")],
        [InlineKeyboardButton(text=status, callback_data="bh_toggle")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


def tasks_kb(enabled):
    status = "🔴 Выключить" if enabled else "🟢 Включить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Награда за задание", callback_data="tasks_edit_reward")],
        [InlineKeyboardButton(text=status, callback_data="tasks_toggle")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


def ctasks_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="ctask_add")],
        [InlineKeyboardButton(text="📜 Список", callback_data="ctask_list")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data="ctask_delete")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


def cop_kb(op_type):
    title = "входе" if op_type == "entry" else "выводе"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"➕ Добавить (на {title})", callback_data=f"cop_add:{op_type}")],
        [InlineKeyboardButton(text=f"📜 Список (на {title})", callback_data=f"cop_list:{op_type}")],
        [InlineKeyboardButton(text=f"🗑 Удалить", callback_data=f"cop_del:{op_type}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


def cop_type_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 На входе", callback_data="cop_menu:entry")],
        [InlineKeyboardButton(text="💸 На выводе", callback_data="cop_menu:withdraw")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


def admin_wd_kb(wid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"wd_ok:{wid}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"wd_no:{wid}")]
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


def user_view_kb(uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Список рефералов", callback_data=f"user_refs:{uid}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


def back_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


def stats_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="stats")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])
