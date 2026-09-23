import asyncio
from urllib.parse import quote

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ChatJoinRequest
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from config import BOT_TOKEN, ADMIN_ID, GIFTS, REFERRAL_DAYS
from database import (
    init_db, get_setting, set_setting,
    get_user, add_user, update_username, add_balance, get_balance,
    get_top, get_place, can_take_bonus, set_bonus_taken,
    get_all_user_ids,
    create_pending_referral, get_pending_refs_count,
    get_confirmed_refs_count, get_user_referrals,
    confirm_referral, expire_old_referrals,
    get_refs_to_remind, mark_reminded,
    create_withdrawal, get_withdrawal, get_pending_withdrawals, set_withdrawal_status,
    get_withdrawal_history,
    get_channels, get_channel_by_id, add_channel, delete_channel, clear_channels,
    track_channel_join, get_channel_joins, get_stats,
    save_join_request, has_recent_join_request, cleanup_join_requests,
    create_promo, get_promo, list_promos, delete_promo, activate_promo,
)
from keyboards import (
    main_menu, sub_kb, withdraw_sub_kb, earn_kb, profile_kb, gifts_kb,
    admin_kb, channels_kb, channels_delete_kb, admin_wd_kb,
    priv_kb, broadcast_kb, settings_kb, promos_kb, user_view_kb, back_admin_kb,
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ============ СОСТОЯНИЯ ============
class AddChannel(StatesGroup):
    waiting_link = State()
    waiting_title = State()
    waiting_id = State()

class PromoCreate(StatesGroup):
    waiting_code = State()
    waiting_amount = State()
    waiting_uses = State()

class PromoDelete(StatesGroup):
    waiting_code = State()

class SetValue(StatesGroup):
    waiting_value = State()

class UserPromo(StatesGroup):
    waiting_code = State()

class WithdrawFlow(StatesGroup):
    waiting_sub = State()

class PrivEdit(StatesGroup):
    waiting_text = State()
    waiting_buttons = State()

class BroadcastFlow(StatesGroup):
    waiting_text = State()

class GiveFlow(StatesGroup):
    waiting_id = State()
    waiting_amount = State()

class UserFind(StatesGroup):
    waiting_id = State()


# ============ ПОДПИСКА ============
async def check_sub(user_id, chat_id, bot_admin=True):
    if not bot_admin:
        return True
    is_numeric = str(chat_id).lstrip("-").isdigit()
    if not is_numeric:
        return True
    try:
        member = await bot.get_chat_member(int(chat_id), user_id)
        if member.status in ("member", "administrator", "creator"):
            return True
    except Exception:
        pass
    if has_recent_join_request(user_id, chat_id):
        return True
    return False


async def check_all_subs(user_id, ch_type):
    channels = get_channels(ch_type)
    if not channels:
        return True, []

    all_green_ok = True
    for ch in channels:
        chat_id = ch[1]
        bot_admin = ch[4] if len(ch) > 4 else 0
        if not bot_admin:
            continue
        ok = await check_sub(user_id, chat_id, True)
        if not ok:
            all_green_ok = False
        else:
            track_channel_join(chat_id, user_id)

    return all_green_ok, channels


def build_priv_buttons():
    """Парсит priv_buttons и возвращает InlineKeyboardMarkup или None"""
    raw = get_setting("priv_buttons")
    if not raw:
        return None
    rows = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        row = []
        for pair in line.split("&"):
            pair = pair.strip()
            if " - " not in pair:
                continue
            parts = pair.split(" - ", 1)
            text = parts[0].strip()
            url = parts[1].strip()
            if text and url:
                row.append(InlineKeyboardButton(text=text, url=url))
        if row:
            rows.append(row)
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============ ЗАЯВКА В КАНАЛ ============
@dp.chat_join_request()
async def on_join_request(request: ChatJoinRequest):
    try:
        save_join_request(request.from_user.id, request.chat.id)
    except Exception:
        pass


# ============ СТАРТ ============
@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    args = message.text.split()
    referrer = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer = int(args[1].split("_")[1])
        except Exception:
            referrer = None

    is_new = add_user(message.from_user.id, message.from_user.username, referrer)
    if not is_new:
        update_username(message.from_user.id, message.from_user.username)

    if is_new and referrer and referrer != message.from_user.id:
        create_pending_referral(message.from_user.id, referrer)
        try:
            await bot.send_message(
                referrer,
                "🎉 По твоей ссылке зашёл новый друг!\n"
                "Он должен зайти в профиль и забрать бонус — тогда ты получишь звёзды."
            )
        except Exception:
            pass

    # Приватка (если включена)
    if get_setting("priv_enabled") == "1":
        priv_text = get_setting("priv_text")
        priv_kb_obj = build_priv_buttons()
        if priv_kb_obj:
            await message.answer(priv_text, reply_markup=priv_kb_obj, parse_mode="HTML")
        else:
            await message.answer(priv_text, parse_mode="HTML")

    # Приветствие + ОП
    ok, channels = await check_all_subs(message.from_user.id, "start")
    if channels and not ok:
        name = message.from_user.first_name or "друг"
        greeting = get_setting("greeting_text").format(name=name)
        await message.answer(
            greeting,
            reply_markup=sub_kb(channels),
            parse_mode="HTML"
        )
        return

    welcome = get_setting("welcome_text")
    await message.answer(welcome, reply_markup=main_menu())


@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(call: CallbackQuery):
    ok, channels = await check_all_subs(call.from_user.id, "start")
    if not ok:
        await call.answer("❌ Ты ещё не подписался на все каналы", show_alert=True)
        return
    try:
        await call.message.delete()
    except Exception:
        pass
    welcome = get_setting("welcome_text")
    await call.message.answer(welcome, reply_markup=main_menu())


# ============ ЗАРАБОТАТЬ ============
@dp.message(F.text == "⭐ Заработать звёзды")
async def earn(message: Message):
    ok, channels = await check_all_subs(message.from_user.id, "start")
    if channels and not ok:
        name = message.from_user.first_name or "друг"
        greeting = get_setting("greeting_text").format(name=name)
        await message.answer(greeting, reply_markup=sub_kb(channels), parse_mode="HTML")
        return

    me = await bot.get_me()
    ref_bonus = get_setting("ref_bonus")
    refs = get_confirmed_refs_count(message.from_user.id)
    ref_link = f"https://t.me/{me.username}?start=ref_{message.from_user.id}"
    share_text = "Заходи в бота, тут раздают звёзды ⭐"
    share_url = (
        f"https://t.me/share/url?url={quote(ref_link, safe='')}"
        f"&text={quote(share_text, safe='')}"
    )

    text = (
        f"Приглашай пользователей в бота и получай по <b>{ref_bonus}</b> 🌟 "
        f"как только они подпишутся на каналы!\n\n"
        f"🔗 <b>Ваша ссылка:</b>\n"
        f"{ref_link}\n\n"
        f"<blockquote>"
        f"❓ <b>Как использовать реферальную ссылку?</b>\n"
        f"• Отправь её друзьям в личные сообщения 👥\n"
        f"• Поделись ссылкой в своём Telegram-канале 📢\n"
        f"• Оставь её в комментариях или чатах 💬\n"
        f"• Распространяй ссылку в соцсетях: TikTok, Instagram, WhatsApp и других 🌐"
        f"</blockquote>\n\n"
        f"👥 Вы пригласили: <b>{refs}</b>"
    )

    await message.answer(text, reply_markup=earn_kb(share_url), parse_mode="HTML")


# ============ ЛИДЕРЫ ============
@dp.message(F.text == "🏆 Лидеры")
async def leaders(message: Message):
    ok, channels = await check_all_subs(message.from_user.id, "start")
    if channels and not ok:
        name = message.from_user.first_name or "друг"
        greeting = get_setting("greeting_text").format(name=name)
        await message.answer(greeting, reply_markup=sub_kb(channels), parse_mode="HTML")
        return
    rows = get_top(10)
    if not rows:
        await message.answer("🏆 Топ пока пуст. Стань первым!")
        return
    text = "🏆 <b>ТОП-10 ПО БАЛАНСУ</b>\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, (username, balance) in enumerate(rows, 1):
        prefix = medals[i - 1] if i <= 3 else f"{i}."
        name = f"@{username}" if username else "аноним"
        text += f"{prefix} {name} — <b>{balance}</b> ⭐\n"
    await message.answer(text, parse_mode="HTML")


# ============ ПРОФИЛЬ ============
@dp.message(F.text == "👤 Профиль")
async def profile(message: Message):
    ok, channels = await check_all_subs(message.from_user.id, "start")
    if channels and not ok:
        name = message.from_user.first_name or "друг"
        greeting = get_setting("greeting_text").format(name=name)
        await message.answer(greeting, reply_markup=sub_kb(channels), parse_mode="HTML")
        return
    u = get_user(message.from_user.id)
    if not u:
        await message.answer("Напиши /start")
        return
    balance = u[2]
    name = message.from_user.first_name or "друг"
    refs = get_confirmed_refs_count(message.from_user.id)
    pending = get_pending_refs_count(message.from_user.id)
    place = get_place(message.from_user.id)

    await message.answer(
        f"👤 <b>ПРОФИЛЬ</b>\n\n"
        f"🧑 {name}\n"
        f"🆔 <code>{message.from_user.id}</code>\n\n"
        f"⭐ Баланс: <b>{balance}</b>\n"
        f"👥 Друзей: <b>{refs}</b>\n"
        f"⏳ Ожидают: <b>{pending}</b>\n"
        f"🏆 Место в топе: <b>#{place}</b>\n\n"
        f"👇 Забирай бонусы и промокоды",
        reply_markup=profile_kb(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "daily_bonus")
async def cb_daily_bonus(call: CallbackQuery):
    if not can_take_bonus(call.from_user.id):
        await call.answer("⏳ Уже забирал сегодня. Возвращайся через 24 часа!", show_alert=True)
        return
    amount = int(get_setting("daily_bonus"))
    add_balance(call.from_user.id, amount)
    set_bonus_taken(call.from_user.id)
    balance = get_balance(call.from_user.id)

    referrer = confirm_referral(call.from_user.id)
    if referrer:
        ref_bonus = int(get_setting("ref_bonus"))
        add_balance(referrer, ref_bonus)
        try:
            await bot.send_message(
                referrer,
                f"🎉 Друг подтвердил реферал!\n💫 Тебе начислено +{ref_bonus} ⭐"
            )
        except Exception:
            pass

    await call.answer(f"🎁 +{amount} ⭐", show_alert=True)
    try:
        await call.message.edit_text(
            f"🎁 <b>Ежедневный бонус получен!</b>\n\n"
            f"💫 +{amount} ⭐\n"
            f"💰 Баланс: <b>{balance}</b> ⭐",
            parse_mode="HTML"
        )
    except Exception:
        pass


@dp.callback_query(F.data == "enter_promo")
async def cb_enter_promo(call: CallbackQuery, state: FSMContext):
    await call.message.answer("🎟 Введи промокод:")
    await state.set_state(UserPromo.waiting_code)


@dp.message(UserPromo.waiting_code)
async def user_promo_check(message: Message, state: FSMContext):
    code = message.text.strip()
    ok, msg, amount = activate_promo(code, message.from_user.id)
    await state.clear()
    if ok:
        balance = get_balance(message.from_user.id)
        await message.answer(f"{msg}\n💰 Баланс: <b>{balance}</b> ⭐", parse_mode="HTML")
    else:
        await message.answer(msg)


# ============ ВЫВОД ============
@dp.message(F.text == "💸 Вывести звёзды")
async def withdraw(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❣️ <b>Выбери подарок</b>",
        reply_markup=gifts_kb(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("gift:"))
async def cb_gift(call: CallbackQuery, state: FSMContext):
    key = call.data.split(":")[1]
    if key not in GIFTS:
        await call.answer("Подарок не найден")
        return
    name, price = GIFTS[key]
    balance = get_balance(call.from_user.id)
    if balance < price:
        need = price - balance
        await call.answer(
            f"❌ Не хватает {need} ⭐\n"
            f"Нужно: {price} ⭐\n"
            f"У тебя: {balance} ⭐",
            show_alert=True
        )
        return

    ok, channels = await check_all_subs(call.from_user.id, "withdraw")
    if channels and not ok:
        await state.update_data(gift_key=key)
        await state.set_state(WithdrawFlow.waiting_sub)
        await call.message.edit_text(
            "✨ Чтобы вывести звёзды, пройди проверку ниже:\n\n"
            "📢 <b>Подпишись на спонсоров:</b>\n\n"
            "<blockquote>После подписки нажмите «✅ Подтвердить»</blockquote>\n\n"
            "Жми на кнопки ниже 👇",
            reply_markup=withdraw_sub_kb(channels),
            parse_mode="HTML"
        )
        return

    await create_order(call, key)


@dp.callback_query(F.data == "wd_confirm_sub")
async def wd_confirm_sub(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    key = data.get("gift_key")
    if not key:
        await call.answer("Сначала выбери подарок", show_alert=True)
        return

    ok, channels = await check_all_subs(call.from_user.id, "withdraw")
    if not ok:
        await call.answer("❌ Ты ещё не подписался на все каналы", show_alert=True)
        return

    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await create_order(call, key)


@dp.callback_query(F.data == "wd_cancel_sub")
async def wd_cancel_sub(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_text(
            "❣️ <b>Выбери подарок</b>",
            reply_markup=gifts_kb(),
            parse_mode="HTML"
        )
    except Exception:
        await call.message.answer(
            "❣️ <b>Выбери подарок</b>",
            reply_markup=gifts_kb(),
            parse_mode="HTML"
        )


async def create_order(call: CallbackQuery, key):
    name, price = GIFTS[key]
    balance = get_balance(call.from_user.id)
    if balance < price:
        await call.answer(f"❌ Нужно {price} ⭐", show_alert=True)
        return

    wid = create_withdrawal(call.from_user.id, price, key)
    uname = f"@{call.from_user.username}" if call.from_user.username else "без username"
    text = (
        f"✅ <b>Заявка #{wid} создана!</b>\n\n"
        f"🎁 Подарок: {name}\n"
        f"💰 Сумма: {price} ⭐\n"
        f"⏳ Ожидай — админ отправит подарок вручную."
    )
    try:
        await call.message.edit_text(text, parse_mode="HTML")
    except Exception:
        try:
            await call.message.answer(text, parse_mode="HTML")
        except Exception:
            pass
    try:
        await bot.send_message(
            ADMIN_ID,
            f"💸 <b>Новая заявка #{wid}</b>\n\n"
            f"👤 {uname}\n"
            f"🆔 <code>{call.from_user.id}</code>\n"
            f"🎁 {name}\n"
            f"💰 {price} ⭐",
            reply_markup=admin_wd_kb(wid),
            parse_mode="HTML"
        )
    except Exception as e:
        print("Ошибка отправки админу:", e)


# ============ АДМИНКА ============
@dp.message(Command("admin"))
async def admin(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    s = get_stats()
    await message.answer(
        f"🛠 <b>АДМИН-ПАНЕЛЬ</b>\n\n"
        f"👥 Пользователей: <b>{s['total']}</b>\n"
        f"📋 Заявок в ожидании: <b>{s['pending']}</b>",
        reply_markup=admin_kb(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "admin_back")
async def admin_back(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await state.clear()
    s = get_stats()
    try:
        await call.message.edit_text(
            f"🛠 <b>АДМИН-ПАНЕЛЬ</b>\n\n"
            f"👥 Пользователей: <b>{s['total']}</b>\n"
            f"📋 Заявок в ожидании: <b>{s['pending']}</b>",
            reply_markup=admin_kb(),
            parse_mode="HTML"
        )
    except Exception:
        await call.message.answer("🛠 Админ-панель", reply_markup=admin_kb())


# --- КАНАЛЫ ---
@dp.callback_query(F.data.startswith("ch_list:"))
async def ch_list(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    ch_type = call.data.split(":")[1]
    title = "📢 Каналы на входе" if ch_type == "start" else "💰 Каналы на вывод"
    rows = get_channels(ch_type)
    if rows:
        lines = []
        for ch in rows:
            t = ch[2]
            bot_admin = ch[4] if len(ch) > 4 else 0
            icon = "🟢" if bot_admin else "🟡"
            lines.append(f"{icon} {t}")
        lst = "\n".join(lines)
    else:
        lst = "<i>пусто</i>"
    await call.message.edit_text(
        f"<b>{title}</b>\n\n"
        f"🟢 — проверка работает\n"
        f"🟡 — без проверки\n\n"
        f"Список:\n{lst}",
        reply_markup=channels_kb(ch_type),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("ch_view:"))
async def ch_view(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    cid = int(call.data.split(":")[1])
    ch = get_channel_by_id(cid)
    if not ch:
        await call.answer("Канал не найден")
        return
    _, chat_id, title, link, ch_type, bot_admin = ch
    joins = get_channel_joins(chat_id)
    status = "🟢 бот админ" if bot_admin else "🟡 без бота-админа"
    await call.message.edit_text(
        f"📢 <b>{title}</b>\n\n"
        f"🔗 Ссылка: {link or '—'}\n"
        f"👥 Зашло по боту: <b>{joins}</b>\n"
        f"🆔 <code>{chat_id}</code>\n"
        f"📍 Тип: {ch_type}\n"
        f"🤖 Статус: {status}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"ch_list:{ch_type}")]
        ]),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("ch_add:"))
async def ch_add(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    ch_type = call.data.split(":")[1]
    await call.message.answer(
        "📢 <b>Как добавить ОП:</b>\n\n"
        "1️⃣ Публичный канал — пришли ссылку:\n"
        "<code>https://t.me/username</code>\n\n"
        "2️⃣ Закрытый канал — пришли ссылку-приглашение:\n"
        "<code>https://t.me/+xxxxx</code>\n\n"
        "3️⃣ Пересланное сообщение из канала\n\n"
        "💡 Для закрытого канала после ссылки пришлёшь название и ID "
        "(вида <code>-100...</code>).\n\n"
        "⚠️ Проверка работает только если бот админ в канале.",
        parse_mode="HTML"
    )
    await state.update_data(ch_type=ch_type)
    await state.set_state(AddChannel.waiting_link)


@dp.message(AddChannel.waiting_link)
async def add_ch_link(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    ch_type = data.get("ch_type", "start")

    if message.forward_from_chat:
        fwd = message.forward_from_chat
        chat_id = str(fwd.id)
        title = fwd.title or f"Канал {chat_id}"
        link = f"https://t.me/{fwd.username}" if fwd.username else ""

        bot_admin = 0
        try:
            member = await bot.get_chat_member(fwd.id, bot.id)
            if member.status in ("administrator", "creator"):
                bot_admin = 1
        except Exception:
            pass

        add_channel(chat_id, title, link, ch_type, bot_admin)
        status = "🟢 проверка работает" if bot_admin else "🟡 без проверки"
        await message.answer(
            f"✅ Канал «{title}» добавлен\n{status}",
            reply_markup=back_admin_kb()
        )
        await state.clear()
        return

    if not message.text:
        await message.answer("⚠️ Пришли ссылку или перешли сообщение.")
        return

    text = message.text.strip()

    if "t.me/+" in text or "t.me/joinchat/" in text:
        await state.update_data(ch_type=ch_type, invite_link=text)
        await message.answer("✏️ Введи название канала (как показывать юзерам):")
        await state.set_state(AddChannel.waiting_title)
        return

    if "t.me/" in text:
        part = text.split("t.me/")[-1].split("?")[0].strip("/")
        if part and not part.startswith("+"):
            text = f"@{part}"

    if text.startswith("@"):
        username = text
        link = f"https://t.me/{username.lstrip('@')}"
        title = username
        chat_id = username
        bot_admin = 0
        try:
            chat = await bot.get_chat(username)
            title = chat.title or username
            chat_id = str(chat.id)
            link = chat.invite_link or (f"https://t.me/{chat.username}" if chat.username else link)
            try:
                member = await bot.get_chat_member(chat.id, bot.id)
                if member.status in ("administrator", "creator"):
                    bot_admin = 1
            except Exception:
                bot_admin = 0
        except Exception:
            pass
        add_channel(chat_id, title, link, ch_type, bot_admin)
        status = "🟢 проверка работает" if bot_admin else "🟡 без проверки"
        await message.answer(
            f"✅ Канал «{title}» добавлен\n{status}",
            reply_markup=back_admin_kb()
        )
        await state.clear()
        return

    await message.answer("⚠️ Не понял. Пришли ссылку https://t.me/...")


@dp.message(AddChannel.waiting_title)
async def add_ch_title(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    title = (message.text or "").strip()[:50] or "Канал"
    await state.update_data(channel_title=title)
    await message.answer(
        "🆔 Пришли ID канала (вида <code>-1001234567890</code>)\n\n"
        "Если нет ID — напиши <code>-</code>",
        parse_mode="HTML"
    )
    await state.set_state(AddChannel.waiting_id)


@dp.message(AddChannel.waiting_id)
async def add_ch_id(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    ch_type = data.get("ch_type", "start")
    link = data.get("invite_link", "")
    title = data.get("channel_title", "Канал")
    text = (message.text or "").strip()

    if text == "-":
        add_channel(link or title, title, link, ch_type, 0)
        await message.answer(
            f"✅ Канал «{title}» добавлен\n🟡 без проверки",
            reply_markup=back_admin_kb()
        )
        await state.clear()
        return

    chat_id = text
    bot_admin = 0
    if text.lstrip("-").isdigit():
        try:
            member = await bot.get_chat_member(int(text), bot.id)
            if member.status in ("administrator", "creator"):
                bot_admin = 1
        except Exception:
            bot_admin = 0

    add_channel(chat_id, title, link, ch_type, bot_admin)
    status = "🟢 проверка работает" if bot_admin else "🟡 без проверки"
    await message.answer(
        f"✅ Канал «{title}» добавлен\n{status}",
        reply_markup=back_admin_kb()
    )
    await state.clear()


@dp.callback_query(F.data.startswith("ch_del_list:"))
async def ch_del_list(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    ch_type = call.data.split(":")[1]
    await call.message.edit_text(
        "🗑 Выбери канал для удаления:",
        reply_markup=channels_delete_kb(ch_type)
    )


@dp.callback_query(F.data.startswith("ch_del:"))
async def ch_del(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    parts = call.data.split(":")
    cid = int(parts[1])
    ch_type = parts[2]
    delete_channel(cid)
    await call.answer("✅ Удалено")
    rows = get_channels(ch_type)
    if rows:
        lst = "\n".join([f"• {ch[2]}" for ch in rows])
    else:
        lst = "<i>пусто</i>"
    title = "📢 Каналы на входе" if ch_type == "start" else "💰 Каналы на вывод"
    await call.message.edit_text(
        f"<b>{title}</b>\n\nСписок:\n{lst}",
        reply_markup=channels_kb(ch_type),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("ch_clear:"))
async def ch_clear(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    ch_type = call.data.split(":")[1]
    clear_channels(ch_type)
    await call.answer("🧹 Очищено")
    await call.message.edit_text(
        "🧹 Все каналы удалены",
        reply_markup=back_admin_kb()
    )


# --- ЗАЯВКИ ---
@dp.callback_query(F.data == "wd_list")
async def wd_list(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    rows = get_pending_withdrawals()
    if not rows:
        await call.message.edit_text("📭 Нет активных заявок", reply_markup=back_admin_kb())
        return
    await call.message.edit_text(f"📋 Активных заявок: {len(rows)}", reply_markup=back_admin_kb())
    for wid, user_id, amount, gift_key in rows:
        name = GIFTS.get(gift_key, ("—", 0))[0]
        u = get_user(user_id)
        uname = f"@{u[1]}" if u and u[1] else "без username"
        await call.message.answer(
            f"💸 <b>Заявка #{wid}</b>\n"
            f"👤 {uname}\n"
            f"🆔 <code>{user_id}</code>\n"
            f"🎁 {name}\n"
            f"💰 {amount} ⭐",
            reply_markup=admin_wd_kb(wid),
            parse_mode="HTML"
        )


@dp.callback_query(F.data.startswith("wd_ok:"))
async def wd_ok(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    wid = int(call.data.split(":")[1])
    row = get_withdrawal(wid)
    if not row:
        await call.answer("Заявка не найдена")
        return
    _, user_id, amount, gift_key, status = row
    if status != "pending":
        await call.answer("Уже обработана")
        return
    set_withdrawal_status(wid, "completed")
    name = GIFTS.get(gift_key, ("подарок", 0))[0]
    try:
        await bot.send_message(
            user_id,
            f"✅ <b>Заявка #{wid} одобрена!</b>\n\n"
            f"🎁 {name} отправлен тебе.\n"
            f"Проверь Telegram!",
            parse_mode="HTML"
        )
    except Exception:
        pass
    try:
        await call.message.edit_text(call.message.text + "\n\n✅ ВЫПОЛНЕНО", parse_mode="HTML")
    except Exception:
        pass


@dp.callback_query(F.data.startswith("wd_no:"))
async def wd_no(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    wid = int(call.data.split(":")[1])
    row = get_withdrawal(wid)
    if not row:
        await call.answer("Заявка не найдена")
        return
    _, user_id, amount, gift_key, status = row
    if status != "pending":
        await call.answer("Уже обработана")
        return
    set_withdrawal_status(wid, "rejected")
    add_balance(user_id, amount)
    try:
        await bot.send_message(
            user_id,
            f"❌ Заявка #{wid} отклонена.\n{amount} ⭐ возвращены на баланс."
        )
    except Exception:
        pass
    try:
        await call.message.edit_text(call.message.text + "\n\n❌ ОТКЛОНЕНО", parse_mode="HTML")
    except Exception:
        pass


@dp.callback_query(F.data == "wd_history")
async def wd_history(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    rows = get_withdrawal_history(50)
    if not rows:
        await call.message.edit_text("📭 История пуста", reply_markup=back_admin_kb())
        return
    text = "📜 <b>История (последние 50)</b>\n\n"
    for wid, uid, amount, gift_key, status, created in rows:
        icon = "✅" if status == "completed" else "❌"
        name = GIFTS.get(gift_key, ("—", 0))[0]
        date = (created or "")[:16].replace("T", " ")
        text += f"{icon} #{wid} — {name} — {amount}⭐ — ID<code>{uid}</code> — {date}\n"
    if len(text) > 4000:
        text = text[:4000] + "\n...обрезано"
    await call.message.edit_text(text, reply_markup=back_admin_kb(), parse_mode="HTML")


# --- ПРИВАТКА ---
@dp.callback_query(F.data == "priv_menu")
async def priv_menu(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    enabled = get_setting("priv_enabled") == "1"
    text = (
        f"🎛 <b>Приватка</b>\n\n"
        f"Статус: {'🟢 включена' if enabled else '🔴 выключена'}\n\n"
        f"<b>Текст:</b>\n<i>{get_setting('priv_text')}</i>\n\n"
        f"<b>Кнопки:</b>\n<code>{get_setting('priv_buttons')}</code>"
    )
    await call.message.edit_text(text, reply_markup=priv_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "priv_edit_text")
async def priv_edit_text(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer(
        "✏️ Пришли новый текст приватки:\n\n"
        "Можно использовать HTML: <code>&lt;b&gt;жирный&lt;/b&gt;</code>, "
        "<code>&lt;i&gt;курсив&lt;/i&gt;</code>, эмодзи."
    )
    await state.set_state(PrivEdit.waiting_text)


@dp.message(PrivEdit.waiting_text)
async def priv_save_text(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    set_setting("priv_text", message.text)
    set_setting("priv_enabled", "1")
    await state.clear()
    await message.answer("✅ Текст приватки сохранён", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "priv_edit_buttons")
async def priv_edit_buttons(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer(
        "🔗 Пришли кнопки в таком формате:\n\n"
        "<b>Столбиком (по 1 в ряд):</b>\n"
        "<code>Кнопка 1 - https://t.me/xxx\n"
        "Кнопка 2 - https://t.me/yyy</code>\n\n"
        "<b>В ряд (по 2+):</b>\n"
        "<code>Кнопка 1 - https://t.me/xxx & Кнопка 2 - https://t.me/yyy</code>\n\n"
        "<b>Смешанно:</b>\n"
        "<code>Я парень - https://t.me/bot1 & Я девушка - https://t.me/bot2\n"
        "Другое - https://t.me/bot3</code>\n\n"
        "Каждая строка — новый ряд. <code>&amp;</code> разделяет кнопки внутри ряда.",
        parse_mode="HTML"
    )
    await state.set_state(PrivEdit.waiting_buttons)


@dp.message(PrivEdit.waiting_buttons)
async def priv_save_buttons(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.strip()
    # Проверка формата
    ok = False
    for line in text.split("\n"):
        for pair in line.split("&"):
            pair = pair.strip()
            if " - " in pair:
                parts = pair.split(" - ", 1)
                if len(parts) == 2 and parts[0].strip() and parts[1].strip().startswith("http"):
                    ok = True
    if not ok:
        await message.answer(
            "⚠️ Неверный формат. Пример:\n"
            "<code>Я парень - https://t.me/bot1 & Я девушка - https://t.me/bot2</code>",
            parse_mode="HTML"
        )
        return
    set_setting("priv_buttons", text)
    set_setting("priv_enabled", "1")
    await state.clear()
    await message.answer("✅ Кнопки сохранены", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "priv_delete")
async def priv_delete(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    set_setting("priv_enabled", "0")
    await call.answer("🗑 Приватка удалена")
    await call.message.edit_text(
        "🗑 Приватка удалена. При /start бот сразу показывает ОП.",
        reply_markup=back_admin_kb()
    )


# --- РАССЫЛКА ---
@dp.callback_query(F.data == "broadcast")
async def broadcast(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("📢 Пришли текст рассылки:")
    await state.set_state(BroadcastFlow.waiting_text)


@dp.message(BroadcastFlow.waiting_text)
async def broadcast_preview(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.update_data(bc_text=message.text)
    users = get_all_user_ids()
    await message.answer(
        f"📢 <b>Предпросмотр:</b>\n\n{message.text}\n\n"
        f"<i>Получателей: {len(users)}</i>\n\n"
        f"Отправить?",
        reply_markup=broadcast_kb(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "broadcast_confirm")
async def broadcast_confirm(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    text = data.get("bc_text")
    if not text:
        await call.answer("Текст потерян, попробуй заново")
        return
    await state.clear()
    users = get_all_user_ids()
    await call.message.edit_text(f"📢 Рассылка началась... (0/{len(users)})")

    sent = 0
    for i, uid in enumerate(users, 1):
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
            sent += 1
        except Exception:
            pass
        if i % 20 == 0:
            try:
                await call.message.edit_text(f"📢 Рассылка... ({i}/{len(users)})")
            except Exception:
                pass
        await asyncio.sleep(0.05)

    await call.message.edit_text(
        f"✅ Рассылка завершена!\n\nОтправлено: {sent}/{len(users)}",
        reply_markup=back_admin_kb()
    )


# --- НАЧИСЛИТЬ ---
@dp.callback_query(F.data == "give_start")
async def give_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("💸 Пришли ID юзера:")
    await state.set_state(GiveFlow.waiting_id)


@dp.message(GiveFlow.waiting_id)
async def give_get_id(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.strip()
    if not text.lstrip("-").isdigit():
        await message.answer("⚠️ ID должен быть числом. Попробуй ещё.")
        return
    uid = int(text)
    u = get_user(uid)
    if not u:
        await message.answer("⚠️ Юзер с таким ID не найден.")
        return
    await state.update_data(give_uid=uid)
    await message.answer(
        f"👤 @{u[1] or 'без username'} — баланс: {u[2]} ⭐\n\n"
        f"Пришли сумму для начисления. Можно отрицательное: <code>-50</code>",
        parse_mode="HTML"
    )
    await state.set_state(GiveFlow.waiting_amount)


@dp.message(GiveFlow.waiting_amount)
async def give_amount(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        amount = int(message.text.strip())
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    data = await state.get_data()
    uid = data.get("give_uid")
    if not uid:
        await state.clear()
        await message.answer("⚠️ Что-то пошло не так.")
        return
    add_balance(uid, amount)
    new_balance = get_balance(uid)
    await state.clear()
    await message.answer(
        f"✅ Начислено: {amount:+d} ⭐\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"💰 Новый баланс: <b>{new_balance}</b> ⭐",
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )


# --- ЮЗЕР ---
@dp.callback_query(F.data == "user_find")
async def user_find(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("👥 Пришли ID юзера:")
    await state.set_state(UserFind.waiting_id)


@dp.message(UserFind.waiting_id)
async def user_show(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.strip()
    if not text.lstrip("-").isdigit():
        await message.answer("⚠️ ID должен быть числом.")
        return
    uid = int(text)
    u = get_user(uid)
    if not u:
        await message.answer("⚠️ Юзер не найден.")
        return
    balance = u[2]
    refs = get_confirmed_refs_count(uid)
    pending = get_pending_refs_count(uid)
    reg = (u[6] or "")[:16].replace("T", " ")
    await state.clear()
    await message.answer(
        f"👤 <b>Юзер</b>\n\n"
        f"🧑 @{u[1] or 'без username'}\n"
        f"🆔 <code>{uid}</code>\n"
        f"⭐ Баланс: <b>{balance}</b>\n"
        f"👥 Друзей: <b>{refs}</b>\n"
        f"⏳ Ожидают: <b>{pending}</b>\n"
        f"📅 Регистрация: {reg}",
        reply_markup=user_view_kb(uid),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("user_refs:"))
async def user_refs(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    uid = int(call.data.split(":")[1])
    rows = get_user_referrals(uid, 100)
    if not rows:
        await call.answer("Список пуст", show_alert=True)
        return
    text = f"👥 <b>Рефералы юзера <code>{uid}</code></b>\n\n"
    icons = {"confirmed": "✅", "pending": "⏳", "expired": "❌"}
    for r_uid, r_name, r_date, r_status in rows:
        icon = icons.get(r_status, "•")
        date = (r_date or "")[:10]
        name = f"@{r_name}" if r_name else "аноним"
        text += f"{icon} {name} — <code>{r_uid}</code> — {date}\n"
    if len(text) > 4000:
        text = text[:4000] + "\n...обрезано"
    await call.message.answer(text, parse_mode="HTML")


# --- ПРОМОКОДЫ ---
@dp.callback_query(F.data == "promos")
async def promos(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text("🎟 <b>Промокоды</b>", reply_markup=promos_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "promo_create")
async def promo_create(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("🎟 Введи название промокода (например, SAVIK1):")
    await state.set_state(PromoCreate.waiting_code)


@dp.message(PromoCreate.waiting_code)
async def promo_code_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    code = message.text.strip().upper()
    if not code.isalnum() or len(code) < 3:
        await message.answer("⚠️ Только буквы/цифры, минимум 3 символа.")
        return
    await state.update_data(code=code)
    await message.answer(f"Код: <b>{code}</b>\n\nСколько звёзд давать?", parse_mode="HTML")
    await state.set_state(PromoCreate.waiting_amount)


@dp.message(PromoCreate.waiting_amount)
async def promo_amount_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        amount = int(message.text)
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    await state.update_data(amount=amount)
    await message.answer(f"Звёзд: <b>{amount}</b>\n\nСколько всего активаций?", parse_mode="HTML")
    await state.set_state(PromoCreate.waiting_uses)


@dp.message(PromoCreate.waiting_uses)
async def promo_uses_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        uses = int(message.text)
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    data = await state.get_data()
    create_promo(data["code"], data["amount"], uses)
    await state.clear()
    await message.answer(
        f"✅ <b>Промокод создан!</b>\n\n"
        f"🎟 Код: <code>{data['code']}</code>\n"
        f"💰 Награда: {data['amount']} ⭐\n"
        f"👥 Активаций: {uses}",
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "promo_list")
async def promo_list_cb(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    rows = list_promos()
    if not rows:
        await call.answer("Промокодов нет", show_alert=True)
        return
    text = "📜 <b>Промокоды</b>\n\n"
    for code, amount, mx, used, active in rows:
        status = "🟢" if active and used < mx else "🔴"
        text += f"{status} <code>{code}</code> — {amount} ⭐ | {used}/{mx}\n"
    await call.message.answer(text, parse_mode="HTML")


@dp.callback_query(F.data == "promo_delete")
async def promo_delete_cb(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("🗑 Введи код для удаления:")
    await state.set_state(PromoDelete.waiting_code)


@dp.message(PromoDelete.waiting_code)
async def promo_delete_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    code = message.text.strip().upper()
    if not get_promo(code):
        await message.answer("⚠️ Такого промокода нет.")
        return
    delete_promo(code)
    await state.clear()
    await message.answer(f"🗑 Промокод <code>{code}</code> удалён.", parse_mode="HTML")


# --- СТАТИСТИКА ---
@dp.callback_query(F.data == "stats")
async def stats(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    s = get_stats()
    channels_start = get_channels("start")
    channels_wd = get_channels("withdraw")
    ch_lines = ""
    for ch in channels_start[:5]:
        ch_lines += f"  • {ch[2]} — {get_channel_joins(ch[1])} 👥\n"
    await call.message.edit_text(
        f"📊 <b>СТАТИСТИКА</b>\n\n"
        f"👥 Всего юзеров: <b>{s['total']}</b>\n"
        f"📅 Сегодня: <b>{s['today']}</b>\n\n"
        f"📋 Заявок в ожидании: <b>{s['pending']}</b>\n"
        f"✅ Выполнено: <b>{s['done']}</b>\n"
        f"💫 Выдано звёзд: <b>{s['total_stars']}</b>\n\n"
        f"📢 Каналов на входе: <b>{len(channels_start)}</b>\n"
        f"💰 Каналов на вывод: <b>{len(channels_wd)}</b>\n\n"
        f"<b>Топ каналов:</b>\n{ch_lines or '  —'}",
        reply_markup=back_admin_kb(),
        parse_mode="HTML"
    )


# --- НАСТРОЙКИ ---
@dp.callback_query(F.data == "settings")
async def settings(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text(
        f"⚙️ <b>НАСТРОЙКИ</b>\n\n"
        f"👥 Бонус за реферала: <b>{get_setting('ref_bonus')}</b> ⭐\n"
        f"🎁 Ежедневный бонус: <b>{get_setting('daily_bonus')}</b> ⭐\n"
        f"💸 Минимум вывода: <b>{get_setting('min_withdraw')}</b> ⭐\n"
        f"✏️ Текст под меню: <i>{get_setting('welcome_text')}</i>\n"
        f"💚 Текст с ОП: <i>{get_setting('greeting_text')[:60]}...</i>",
        reply_markup=settings_kb(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("set:"))
async def set_value_ask(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    key = call.data.split(":")[1]
    prompts = {
        "ref_bonus": "👥 Введи новый бонус за реферала (число):",
        "daily_bonus": "🎁 Введи новый ежедневный бонус (число):",
        "min_withdraw": "💸 Введи новый минимум для вывода (число):",
        "welcome_text": "✏️ Введи новый текст под меню (можно с эмодзи):",
        "greeting_text": (
            "💚 Введи новый текст с ОП.\n\n"
            "Можно использовать <code>{name}</code> — подставится имя юзера.\n"
            "HTML: <code>&lt;b&gt;жирный&lt;/b&gt;</code>, <code>&lt;i&gt;курсив&lt;/i&gt;</code>."
        ),
    }
    await state.update_data(set_key=key)
    await call.message.answer(prompts[key], parse_mode="HTML")
    await state.set_state(SetValue.waiting_value)


@dp.message(SetValue.waiting_value)
async def set_value_save(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    key = data.get("set_key")
    value = message.text.strip()
    if key in ("ref_bonus", "daily_bonus", "min_withdraw"):
        try:
            int(value)
        except Exception:
            await message.answer("⚠️ Нужно число. Попробуй ещё раз.")
            return
    set_setting(key, value)
    await state.clear()
    await message.answer(f"✅ Сохранено: {key} = {value[:80]}", reply_markup=back_admin_kb())


# ============ ФОНОВЫЕ ЗАДАЧИ ============
async def referral_watcher():
    while True:
        try:
            for rid, user_id, referrer_id in get_refs_to_remind():
                u = get_user(user_id)
                uname = f"@{u[1]}" if u and u[1] else "друг"
                try:
                    await bot.send_message(
                        referrer_id,
                        f"⏳ {uname} зашёл по твоей ссылке, но не забрал бонус.\n"
                        f"Напомни ему зайти в профиль и нажать «🎁 Ежедневный бонус»."
                    )
                except Exception:
                    pass
                mark_reminded(rid)

            expired = expire_old_referrals()
            if expired:
                grouped = {}
                for user_id, referrer_id in expired:
                    grouped.setdefault(referrer_id, []).append(user_id)
                for referrer_id, users in grouped.items():
                    lines = "\n".join([f"• ID <code>{uid}</code>" for uid in users])
                    try:
                        await bot.send_message(
                            referrer_id,
                            f"⏰ Прошло {REFERRAL_DAYS} дней. "
                            f"Друзья не забрали бонус, рефералы не засчитаны:\n{lines}",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass

            cleanup_join_requests()
        except Exception as e:
            print("Watcher error:", e)
        await asyncio.sleep(60)


# ============ ЗАПУСК ============
async def main():
    init_db()
    asyncio.create_task(referral_watcher())
    print("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
