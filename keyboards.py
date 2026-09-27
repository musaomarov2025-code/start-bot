from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from config import GIFTS, GIFTS_ORDER, GIFTS_EMOJI
from database import get_setting as _gs


# ================== ГЛАВНОЕ МЕНЮ ==================
def main_menu():
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[
        [KeyboardButton(text="Заработать звёзды", icon_custom_emoji_id="5438496463044752972")],
        [KeyboardButton(text="Вывести звёзды", icon_custom_emoji_id="6025976946083500432")],
        [KeyboardButton(text="Задания", icon_custom_emoji_id="5427168083074628963"),
         KeyboardButton(text="Профиль", icon_custom_emoji_id="5325971446625758812")],
    ])


# ================== ЗАРАБОТАТЬ ==================
def earn_kb(share_url):
    btn_text = _gs("earn_btn") or "Пригласить друга"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=btn_text, url=share_url,
                              icon_custom_emoji_id="5258362837411045098")],
    ])


# ================== ПРОФИЛЬ ==================
def profile_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ежедневный бонус", callback_data="daily_bonus",
                              icon_custom_emoji_id="5449800250032143374")],
        [InlineKeyboardButton(text="Ввести промокод", callback_data="enter_promo",
                              icon_custom_emoji_id="5197468864102823838")],
    ])


# ================== ПОДАРКИ ==================
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


# ================== ЗАДАНИЕ ==================
def task_kb(link, source="bh"):
    go_text = _gs("task_btn_go") or "Перейти"
    check_text = _gs("task_btn_check") or "Проверить"
    skip_text = _gs("task_btn_skip") or "Пропустить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=go_text, url=link,
                                 icon_custom_emoji_id="5368733682917980020"),
            InlineKeyboardButton(text=check_text, callback_data=f"tc:{source}",
                                 icon_custom_emoji_id="6026257381678124710",
                                 style="success"),
        ],
        [
            InlineKeyboardButton(text=skip_text, callback_data="task_skip",
                                 icon_custom_emoji_id="5260450573768990626"),
        ],
    ])


def task_done_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Обновить задания", callback_data="tasks_refresh",
                              icon_custom_emoji_id="5386367538735104399")],
    ])


# ================== ОП НА СТАРТЕ ==================
def op_start_kb():
    sub_text = _gs("op_btn_sub") or "Подписаться"
    done_text = _gs("op_btn_done") or "Я подписался"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=done_text, callback_data="op_check",
                              icon_custom_emoji_id="6026257381678124710",
                              style="success")],
    ])


# ================== БОНУС ==================
def daily_bonus_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Забрать", callback_data="daily_claim",
                              icon_custom_emoji_id="6026257381678124710",
                              style="success")],
        [InlineKeyboardButton(text="Назад", callback_data="daily_cancel",
                              icon_custom_emoji_id="5258236805890710909")],
    ])


def daily_back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="daily_back",
                              icon_custom_emoji_id="5258236805890710909")],
    ])


def promo_cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отмена", callback_data="promo_cancel",
                              icon_custom_emoji_id="5210952531676504517")],
    ])


# ================== АДМИНКА ==================
def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 ОП на старте", callback_data="cop_menu:entry"),
         InlineKeyboardButton(text="💸 ОП на выводе", callback_data="cop_menu:withdraw")],
        [InlineKeyboardButton(text="🎯 Задания", callback_data="tasks_menu"),
         InlineKeyboardButton(text="📌 Свои задания", callback_data="ctasks_menu")],
        [InlineKeyboardButton(text="💖 Рефералка", callback_data="ref_menu"),
         InlineKeyboardButton(text="🎛 Приватка", callback_data="priv_menu")],
        [InlineKeyboardButton(text="📋 Заявки", callback_data="wd_list"),
         InlineKeyboardButton(text="📜 История", callback_data="wd_history")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats"),
         InlineKeyboardButton(text="👥 Юзер", callback_data="user_find")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="broadcast"),
         InlineKeyboardButton(text="🎟 Промокоды", callback_data="promos")],
        [InlineKeyboardButton(text="💸 Начислить", callback_data="give_start"),
         InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton(text="📦 Бэкап", callback_data="backup_help")],
    ])


# ================== ЗАДАНИЯ (админ) ==================
def tasks_kb(enabled):
    status = "🔴 Выключить" if enabled else "🟢 Включить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Награда за задание", callback_data="tasks_edit_reward")],
        [InlineKeyboardButton(text="✏️ Текст задания", callback_data="task_edit_text")],
        [InlineKeyboardButton(text="🔤 Текст кнопок", callback_data="task_edit_btns")],
        [InlineKeyboardButton(text=status, callback_data="tasks_toggle")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


# ================== СВОИ ЗАДАНИЯ ==================
def ctasks_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="ctask_add")],
        [InlineKeyboardButton(text="📜 Список", callback_data="ctask_list")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data="ctask_delete")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


def ctask_type_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Открытый канал", callback_data="ctask_type:open")],
        [InlineKeyboardButton(text="🔒 Закрытый канал", callback_data="ctask_type:closed")],
        [InlineKeyboardButton(text="🤖 Бот по рефке", callback_data="ctask_type:bot")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_back")],
    ])


# ================== СВОИ ОП (на старте / на выводе) ==================
def cop_kb(op_type):
    title = "входе" if op_type == "entry" else "выводе"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"➕ Добавить (на {title})", callback_data=f"cop_add:{op_type}")],
        [InlineKeyboardButton(text=f"📜 Список (на {title})", callback_data=f"cop_list:{op_type}")],
        [InlineKeyboardButton(text=f"🗑 Удалить (на {title})", callback_data=f"cop_del:{op_type}")],
        [InlineKeyboardButton(text="✏️ Текст ОП", callback_data="op_edit_text")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


def cop_type_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 На входе", callback_data="cop_menu:entry")],
        [InlineKeyboardButton(text="💸 На выводе", callback_data="cop_menu:withdraw")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


def cop_add_type_kb(op_type):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Открытый", callback_data=f"cop_type:{op_type}:open")],
        [InlineKeyboardButton(text="🔒 Закрытый", callback_data=f"cop_type:{op_type}:closed")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_back")],
    ])


# ================== РЕФЕРАЛКА ==================
def ref_menu_kb(enabled):
    status = "🔴 Выключить" if enabled else "🟢 Включить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Награда за 5/5", callback_data="ref_edit_bonus")],
        [InlineKeyboardButton(text="🎯 Сколько заданий нужно", callback_data="ref_edit_required")],
        [InlineKeyboardButton(text="📅 Дней на выполнение", callback_data="ref_edit_days")],
        [InlineKeyboardButton(text="✏️ Текст «Заработать»", callback_data="ref_edit_earn_text")],
        [InlineKeyboardButton(text="✏️ Уведомление: старт", callback_data="ref_edit_notify_start")],
        [InlineKeyboardButton(text="✏️ Уведомление: 5 мин", callback_data="ref_edit_notify_5min")],
        [InlineKeyboardButton(text="✏️ Уведомление: 10 мин", callback_data="ref_edit_notify_10min")],
        [InlineKeyboardButton(text="✏️ Уведомление: 5/5", callback_data="ref_edit_notify_done")],
        [InlineKeyboardButton(text=status, callback_data="ref_toggle")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


# ================== ЗАЯВКИ ==================
def admin_wd_kb(wid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"wd_ok:{wid}",
                              style="success"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"wd_no:{wid}",
                              style="danger")],
    ])


# ================== ПРИВАТКА ==================
def priv_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить текст", callback_data="priv_edit_text")],
        [InlineKeyboardButton(text="🔗 Настроить кнопки", callback_data="priv_edit_buttons")],
        [InlineKeyboardButton(text="🗑 Удалить приватку", callback_data="priv_delete")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


# ================== РАССЫЛКА ==================
def broadcast_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить всем", callback_data="broadcast_confirm",
                              style="success")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back",
                              style="danger")],
    ])


# ================== НАСТРОЙКИ ==================
def settings_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Ежедневный бонус", callback_data="set:daily_bonus")],
        [InlineKeyboardButton(text="💸 Минимум вывода", callback_data="set:min_withdraw")],
        [InlineKeyboardButton(text="✏️ Текст под меню", callback_data="set:welcome_text")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


# ================== ПРОМОКОДЫ ==================
def promos_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать промокод", callback_data="promo_create")],
        [InlineKeyboardButton(text="📜 Список промокодов", callback_data="promo_list")],
        [InlineKeyboardButton(text="🗑 Удалить промокод", callback_data="promo_delete")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


# ================== ЮЗЕР ==================
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


# ================== ОП ЭКРАН (Botohub + свои ОП на выводе) ==================
def botohub_op_kb(items, cb_data_confirm):
    """
    items: список (text, url) — кнопки «Подписаться N»
    """
    buttons = []
    row = []
    for text, url in items:
        row.append(InlineKeyboardButton(text=text, url=url,
                                        icon_custom_emoji_id="5253742260054409879"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="Я подписался", callback_data=cb_data_confirm,
                                          icon_custom_emoji_id="6026257381678124710",
                                          style="success")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def op_start_multi_kb(items):
    """
    items: список (text, url) — кнопки «Подписаться N» для ОП на старте.
    """
    buttons = []
    row = []
    for text, url in items:
        row.append(InlineKeyboardButton(text=text, url=url,
                                        icon_custom_emoji_id="5253742260054409879"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="Я подписался", callback_data="op_check",
                                          icon_custom_emoji_id="6026257381678124710",
                                          style="success")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
