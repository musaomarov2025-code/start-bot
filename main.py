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
    create_pending_referral, get_pending_refs_count,
    get_confirmed_refs_count, confirm_referral, expire_old_referrals,
    get_refs_to_remind, mark_reminded,
    create_withdrawal, get_withdrawal, get_pending_withdrawals, set_withdrawal_status,
    get_channels, get_channel_by_id, add_channel, delete_channel, clear_channels,
    track_channel_join, get_channel_joins, get_stats,
    save_join_request, has_recent_join_request, cleanup_join_requests,
    create_promo, get_promo, list_promos, delete_promo, activate_promo,
)
from keyboards import (
    main_menu, gender_kb, sub_kb, withdraw_sub_kb, earn_kb, profile_kb, gifts_kb,
    admin_kb, channels_kb, channels_delete_kb, admin_wd_kb,
    settings_kb, promos_kb, back_admin_kb,
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


# ============ ПОДПИСКА ============
async def check_sub(user_id, chat_id, bot_admin=True):
    if not bot_admin:
        return True
    is_numeric = str(chat_id).lstrip("-").isdigit()
    if not is_numeric:
        return True
    try:
        member = await bot.getChatMember(int(chat_id), user_id)
        if member.status in ("member", "administrator", "creator"):
            return True
    except Exception:
        pass
    if has_recent_join_request(user_id, chat_id):
        return True
    return False


async def check_all_subs(user_id, ch_type, for_confirm=False):
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

    if for_confirm:
        return all_green_ok, channels

    return False, channels


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

    await message.answer(
        "🚹 <b>Укажи свой пол</b> ⤵️",
        reply_markup=gender_kb(),
        parse_mode="HTML"
    )

    ok, channels = await check_all_subs(message.from_user.id, "start")
    if channels and not ok:
        name = message.from_user.first_name or "друг"
        await message.answer(
            f"💚 <b>Привет, {name}!</b> Тут можно получать подарки 🎁\n\n"
            f"✅ Подпишись на спонсоров ниже, чтобы войти в бота "
            f"и забрать 🧸 мишку!",
            reply_markup=sub_kb(channels),
            parse_mode="HTML"
        )
        return

    welcome = get_setting("welcome_text")
    await message.answer(welcome, reply_markup=main_menu())


@dp.callback_query(F.data == "check_sub")
async def cb_check_sub(call: CallbackQuery):
    ok, channels = await check_all_subs(call.from_user.id, "start", for_confirm=True)
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
        await message.answer("📢 Подпишись на каналы:", reply_markup=sub_kb(channels))
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
        await message.answer("📢 Подпишись на каналы:", reply_markup=sub_kb(channels))
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
        await message.answer("📢 Подпишись на каналы:", reply_markup=sub_kb(channels))
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

    ok, channels = await check_all_subs(call.from_user.id, "withdraw", for_confirm=True)
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
        "⚠️ Проверка работает только если бот админ в канале. "
        "Иначе канал добавится, но будет 🟡 без проверки.",
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

    # Пересланное сообщение из канала
    if message.forward_from_chat:
        fwd = message.forward_from_chat
        chat_id = str(fwd.id)
        title = fwd.title or f"Канал {chat_id}"
        link = f"https://t.me/{fwd.username}" if fwd.username else ""

        bot_admin = 0
        debug = (
            f"🔍 <b>ОТЛАДКА (пересылка)</b>\n\n"
            f"📢 Канал: {title}\n"
            f"🆔 ID: <code>{chat_id}</code>\n"
            f"📁 Тип: {fwd.type}\n"
            f"🤖 Bot ID: <code>{bot.id}</code>\n\n"
        )
        try:
            member = await bot.getChatMember(fwd.id, bot.id)
            debug += f"✅ Статус бота: <b>{member.status}</b>"
            if member.status in ("administrator", "creator"):
                bot_admin = 1
        except Exception as e:
            debug += f"❌ Ошибка getChatMember:\n<code>{e}</code>"

        try:
            await bot.send_message(ADMIN_ID, debug, parse_mode="HTML")
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

    # Ссылка-приглашение закрытого канала
    if "t.me/+" in text or "t.me/joinchat/" in text:
        await state.update_data(ch_type=ch_type, invite_link=text)
        await message.answer("✏️ Введи название канала (как показывать юзерам):")
        await state.set_state(AddChannel.waiting_title)
        return

    # Публичный канал
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

        debug = (
            f"🔍 <b>ОТЛАДКА (@username)</b>\n\n"
            f"📢 Юзернейм: {username}\n"
            f"🤖 Bot ID: <code>{bot.id}</code>\n\n"
        )

        try:
            chat = await bot.getChat(username)
            title = chat.title or username
            chat_id = str(chat.id)
            link = chat.invite_link or (f"https://t.me/{chat.username}" if chat.username else link)
            debug += f"🆔 ID: <code>{chat_id}</code>\n"
            try:
                member = await bot.getChatMember(chat.id, bot.id)
                debug += f"✅ Статус бота: <b>{member.status}</b>"
                if member.status in ("administrator", "creator"):
                    bot_admin = 1
            except Exception as e:
                debug += f"❌ Ошибка getChatMember:\n<code>{e}</code>"
        except Exception as e:
            debug += f"❌ Ошибка getChat:\n<code>{e}</code>"

        try:
            await bot.send_message(ADMIN_ID, debug, parse_mode="HTML")
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

    await message.answer(
        "⚠️ Не понял. Пришли ссылку https://t.me/... или перешли сообщение."
    )


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

    debug = (
        f"🔍 <b>ОТЛАДКА (закрытый канал)</b>\n\n"
        f"📢 Канал: {title}\n"
        f"🔗 Ссылка: {link}\n"
        f"🆔 Присланный ID: <code>{text}</code>\n"
        f"🤖 Bot ID: <code>{bot.id}</code>\n\n"
    )

    if text.lstrip("-").isdigit():
        try:
            member = await bot.getChatMember(int(text), bot.id)
            debug += f"✅ Статус бота: <b>{member.status}</b>"
            if member.status in ("administrator", "creator"):
                bot_admin = 1
        except Exception as e:
            debug += f"❌ Ошибка getChatMember:\n<code>{e}</code>"
    else:
        debug += f"⚠️ ID не числовой, проверка невозможна"

    try:
        await bot.send_message(ADMIN_ID, debug, parse_mode="HTML")
    except Exception:
        pass

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


@dp.callback_query(F.data == "settings")
async def settings(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text(
        f"⚙️ <b>НАСТРОЙКИ</b>\n\n"
        f"👥 Бонус за реферала: <b>{get_setting('ref_bonus')}</b> ⭐\n"
        f"🎁 Ежедневный бонус: <b>{get_setting('daily_bonus')}</b> ⭐\n"
        f"💸 Минимум вывода: <b>{get_setting('min_withdraw')}</b> ⭐\n"
        f"✏️ Текст под меню:\n<i>{get_setting('welcome_text')}</i>",
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
    }
    await state.update_data(set_key=key)
    await call.message.answer(prompts[key])
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
    await message.answer(f"✅ Сохранено: {key} = {value}", reply_markup=back_admin_kb())


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
