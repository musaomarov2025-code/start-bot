from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from config import GIFTS, GIFTS_ORDER, GIFTS_EMOJI


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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пригласить друга", url=share_url,
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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Перейти", url=link,
                              icon_custom_emoji_id="5368733682917980020"),
         InlineKeyboardButton(text="Пропустить", callback_data="task_skip",
                              icon_custom_emoji_id="5260450573768990626")],
        [InlineKeyboardButton(text="Подтвердить", callback_data=f"tc:{source}",
                              icon_custom_emoji_id="6026257381678124710")],
    ])


# ================== БОНУС ==================
def daily_bonus_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Забрать", callback_data="daily_claim",
                              icon_custom_emoji_id="6026257381678124710")],
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


# ================== ОП-ЭКРАН (Botohub + свои) ==================
def op_screen_kb(items, confirm_callback="op_check"):
    """
    items: список кортежей (op_key, title, url, passed)
    confirm_callback: 'op_check' (вход в бот) или 'op_check_wd' (вывод)
    """
    buttons = []
    row = []
    for i, (op_key, title, url, passed) in enumerate(items, 1):
        prefix = "✅ " if passed else ""
        row.append(InlineKeyboardButton(
            text=f"{prefix}{title} {i}",
            url=url,
            icon_custom_emoji_id="5253742260054409879"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(
        text="Я подписался", callback_data=confirm_callback,
        icon_custom_emoji_id="6026257381678124710")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ================== АДМИНКА ==================
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
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="broadcast_menu"),
         InlineKeyboardButton(text="🎟 Промокоды", callback_data="promos")],
        [InlineKeyboardButton(text="📊 Реклама", callback_data="ad_menu"),
         InlineKeyboardButton(text="💸 Начислить", callback_data="give_start")],
        [InlineKeyboardButton(text="👥 Юзер", callback_data="user_find"),
         InlineKeyboardButton(text="📢 Автопост", callback_data="autopost_menu")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings"),
         InlineKeyboardButton(text="📦 Бэкап", callback_data="backup_help")],
    ])


# ================== BOTOHUB ОП ==================
def bh_kb(enabled):
    status = "🔴 Выключить" if enabled else "🟢 Включить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Текст сообщения", callback_data="bh_edit_text"),
         InlineKeyboardButton(text="🔤 Текст кнопок", callback_data="bh_edit_btn")],
        [InlineKeyboardButton(text="📥 ОП на входе (кол-во)", callback_data="bh_edit_entry"),
         InlineKeyboardButton(text="💸 ОП на выводе", callback_data="bh_edit_wd")],
        [InlineKeyboardButton(text="📌 Свои ОП (кол-во)", callback_data="bh_edit_custom")],
        [InlineKeyboardButton(text=status, callback_data="bh_toggle")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


# ================== ЗАДАНИЯ BOTOHUB ==================
def tasks_kb(enabled):
    status = "🔴 Выключить" if enabled else "🟢 Включить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Награда за задание", callback_data="tasks_edit_reward")],
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


# ================== СВОИ ОП ==================
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


# ================== ЗАЯВКИ ==================
def admin_wd_kb(wid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"wd_ok:{wid}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"wd_no:{wid}")]
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
def broadcast_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Текст", callback_data="bc_edit_text")],
        [InlineKeyboardButton(text="🖼 Фото", callback_data="bc_edit_photo"),
         InlineKeyboardButton(text="🗑 Убрать фото", callback_data="bc_del_photo")],
        [InlineKeyboardButton(text="🔗 Кнопки", callback_data="bc_edit_buttons")],
        [InlineKeyboardButton(text="👥 Количество", callback_data="bc_edit_count")],
        [InlineKeyboardButton(text="👁 Предпросмотр", callback_data="bc_preview")],
        [InlineKeyboardButton(text="✅ Отправить", callback_data="bc_send")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


def broadcast_confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Начать", callback_data="bc_start"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="admin_back")],
    ])


def broadcast_preview_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Текст", callback_data="bc_edit_text")],
        [InlineKeyboardButton(text="🖼 Фото", callback_data="bc_edit_photo"),
         InlineKeyboardButton(text="🗑 Убрать фото", callback_data="bc_del_photo")],
        [InlineKeyboardButton(text="🔗 Кнопки", callback_data="bc_edit_buttons")],
        [InlineKeyboardButton(text="👥 Количество", callback_data="bc_edit_count")],
        [InlineKeyboardButton(text="✅ Отправить", callback_data="bc_send")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="broadcast_menu")],
    ])


# ================== НАСТРОЙКИ ==================
def settings_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Бонус за реферала", callback_data="set:ref_bonus")],
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


def promo_type_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💫 Обычный", callback_data="pcreate_type:normal")],
        [InlineKeyboardButton(text="📢 За ОП", callback_data="pcreate_type:op")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_back")],
    ])


def promo_op_select_kb(all_ops, selected, code):
    buttons = []
    for op_key, label in all_ops:
        mark = "✅ " if op_key in selected else "⬜ "
        buttons.append([InlineKeyboardButton(
            text=f"{mark}{label}",
            callback_data=f"pcreate_toggle:{code}:{op_key}"
        )])
    buttons.append([InlineKeyboardButton(
        text="✅ Готово", callback_data=f"pcreate_done:{code}")])
    buttons.append([InlineKeyboardButton(
        text="⬅️ Отмена", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ================== РЕКЛАМА ==================
def ad_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить метку", callback_data="ad_add")],
        [InlineKeyboardButton(text="📜 Список меток", callback_data="ad_list")],
        [InlineKeyboardButton(text="🗑 Удалить метку", callback_data="ad_del")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


# ================== АВТОПОСТ ==================
def autopost_kb(enabled):
    status = "🔴 Выключить" if enabled else "🟢 Включить"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Тексты поста", callback_data="ap_texts"),
         InlineKeyboardButton(text="🆔 Чаты", callback_data="ap_chats")],
        [InlineKeyboardButton(text="🖼 Медиа (фото/видео)", callback_data="ap_edit_media"),
         InlineKeyboardButton(text="🗑 Убрать медиа", callback_data="ap_del_media")],
        [InlineKeyboardButton(text="🔗 Кнопки", callback_data="ap_edit_buttons")],
        [InlineKeyboardButton(text="⏱ Интервал (минуты)", callback_data="ap_edit_interval")],
        [InlineKeyboardButton(text=status, callback_data="ap_toggle")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")],
    ])


def autopost_texts_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить текст", callback_data="ap_text_add")],
        [InlineKeyboardButton(text="📜 Показать все", callback_data="ap_text_show")],
        [InlineKeyboardButton(text="🗑 Удалить текст", callback_data="ap_text_del")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="autopost_menu")],
    ])


def autopost_chats_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить чат", callback_data="ap_chat_add")],
        [InlineKeyboardButton(text="📜 Показать все", callback_data="ap_chat_show")],
        [InlineKeyboardButton(text="🗑 Удалить чат", callback_data="ap_chat_del")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="autopost_menu")],
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
