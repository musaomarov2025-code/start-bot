import asyncio
import json
import os
from datetime import datetime
from urllib.parse import quote

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from config import (
    BOT_TOKEN, ADMIN_ID, GIFTS, REFERRAL_DAYS, DB,
    PIARFLOW_BASE_URL,
)
from database import (
    init_db, get_setting, set_setting,
    get_user, add_user, update_username, add_balance, get_balance,
    get_place, can_take_bonus, set_bonus_taken,
    get_all_user_ids,
    create_pending_referral, get_pending_refs_count,
    get_confirmed_refs_count, get_user_referrals,
    confirm_referral, expire_old_referrals,
    get_refs_to_remind, mark_reminded,
    create_withdrawal, get_withdrawal, get_pending_withdrawals, set_withdrawal_status,
    get_withdrawal_history,
    get_stats, create_promo, get_promo, list_promos, delete_promo, activate_promo,
    piarflow_mark_done, piarflow_is_done,
    create_custom_task, list_custom_tasks, get_custom_task, delete_custom_task,
)
from keyboards import (
    main_menu, earn_kb, profile_kb, gifts_kb, task_kb,
    admin_kb, admin_wd_kb, priv_kb, broadcast_kb, settings_kb,
    promos_kb, tasks_admin_kb, user_view_kb, back_admin_kb, piarflow_kb,
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

BOT_ID = int(BOT_TOKEN.split(":")[0])


# ============ СОСТОЯНИЯ ============
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

class PiarFlowEdit(StatesGroup):
    waiting_key = State()
    waiting_reward = State()
    waiting_entry = State()
    waiting_wd = State()

class TaskAdd(StatesGroup):
    waiting_title = State()
    waiting_link = State()
    waiting_reward = State()

class TaskDelete(StatesGroup):
    waiting_id = State()

class WithdrawFlow(StatesGroup):
    waiting_sub = State()


# ============ PIARFLOW ============
def pf_enabled():
    return get_setting("piarflow_enabled") == "1"


async def pf_get_sponsors(user_id, limit):
    key = get_setting("piarflow_key")
    if not key:
        return []
    payload = {
        "user_id": user_id,
        "chat_id": BOT_ID,
        "max_sponsors": limit,
    }
    headers = {"Authorization": f"Bearer {key}"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{PIARFLOW_BASE_URL}/sponsors",
                              json=payload, headers=headers,
                              timeout=aiohttp.ClientTimeout(total=15)) as r:
                data = await r.json()
                return data.get("sponsors", data.get("offers", []))
    except Exception as e:
        print("PiarFlow sponsors error:", e)
        return []


async def pf_check_links(user_id, links):
    key = get_setting("piarflow_key")
    if not key:
        return {}
    payload = {"user_id": user_id, "chat_id": BOT_ID, "links": links}
    headers = {"Authorization": f"Bearer {key}"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{PIARFLOW_BASE_URL}/sponsors/check",
                              json=payload, headers=headers,
                              timeout=aiohttp.ClientTimeout(total=15)) as r:
                data = await r.json()
                result = {}
                items = data.get("sponsors") or data.get("offers") or data.get("links") or []
                for item in items:
                    if isinstance(item, dict):
                        link = item.get("link") or item.get("url")
                        status = item.get("status") or item.get("subscribed")
                        if link:
                            result[link] = status
                return result
    except Exception as e:
        print("PiarFlow check error:", e)
        return {}


async def pf_check_one(user_id, link):
    result = await pf_check_links(user_id, [link])
    return result.get(link) in ("subscribed", True, "ok", "active")


async def pf_all_passed_once(user_id, links):
    if not links:
        return True
    result = await pf_check_links(user_id, links)
    for link in links:
        if result.get(link) not in ("subscribed", True, "ok", "active"):
            return False
    return True


async def pf_all_passed(user_id, links, retries=3, delay=7):
    """Проверяет с повторами. 3 × 7 = 21 секунда."""
    if not links:
        return True
    for i in range(retries):
        ok = await pf_all_passed_once(user_id, links)
        if ok:
            return True
        if i < retries - 1:
            await asyncio.sleep(delay)
    return False


# ============ БЭКАП ============
def export_users_to_json():
    import sqlite3
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, balance, last_bonus, referrer_id, registered_at FROM users")
    users = [{"user_id": r[0], "username": r[1], "balance": r[2],
              "last_bonus": r[3], "referrer_id": r[4], "registered_at": r[5]}
             for r in cur.fetchall()]
    cur.execute("SELECT user_id, referrer_id, created_at, status FROM referrals")
    referrals = [{"user_id": r[0], "referrer_id": r[1], "created_at": r[2], "status": r[3]}
                 for r in cur.fetchall()]
    cur.execute("SELECT code, amount, max_uses, used, active FROM promos")
    promos = [{"code": r[0], "amount": r[1], "max_uses": r[2], "used": r[3], "active": r[4]}
              for r in cur.fetchall()]
    cur.execute("SELECT user_id, amount, gift, status, created_at FROM withdrawals")
    withdrawals = [{"user_id": r[0], "amount": r[1], "gift": r[2], "status": r[3], "created_at": r[4]}
                   for r in cur.fetchall()]
    cur.execute("SELECT key, value FROM settings")
    settings = {r[0]: r[1] for r in cur.fetchall()}
    cur.execute("SELECT user_id, link, done_at FROM piarflow_done")
    pf_done = [{"user_id": r[0], "link": r[1], "done_at": r[2]} for r in cur.fetchall()]
    cur.execute("SELECT id, title, link, reward, active FROM custom_tasks")
    custom_tasks = [{"id": r[0], "title": r[1], "link": r[2], "reward": r[3], "active": r[4]}
                    for r in cur.fetchall()]
    conn.close()
    return {
        "exported_at": datetime.now().isoformat(),
        "users": users, "referrals": referrals, "promos": promos,
        "withdrawals": withdrawals, "settings": settings,
        "piarflow_done": pf_done, "custom_tasks": custom_tasks,
    }


def import_users_from_json(data):
    import sqlite3
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    count = 0
    for u in data.get("users", []):
        cur.execute("""
            INSERT OR REPLACE INTO users
            (user_id, username, balance, last_bonus, referrer_id, registered_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (u["user_id"], u.get("username"), u.get("balance", 0),
              u.get("last_bonus"), u.get("referrer_id"), u.get("registered_at")))
        count += 1
    cur.execute("DELETE FROM referrals")
    for r in data.get("referrals", []):
        cur.execute("INSERT INTO referrals (user_id, referrer_id, created_at, status) VALUES (?,?,?,?)",
                    (r["user_id"], r["referrer_id"], r.get("created_at"), r.get("status", "pending")))
    for p in data.get("promos", []):
        cur.execute("INSERT OR REPLACE INTO promos (code, amount, max_uses, used, active) VALUES (?,?,?,?,?)",
                    (p["code"], p["amount"], p["max_uses"], p.get("used", 0), p.get("active", 1)))
    cur.execute("DELETE FROM withdrawals")
    for w in data.get("withdrawals", []):
        cur.execute("INSERT INTO withdrawals (user_id, amount, gift, status, created_at) VALUES (?,?,?,?,?)",
                    (w["user_id"], w["amount"], w.get("gift"), w.get("status", "pending"), w.get("created_at")))
    for pd in data.get("piarflow_done", []):
        cur.execute("INSERT OR IGNORE INTO piarflow_done (user_id, link, done_at) VALUES (?,?,?)",
                    (pd["user_id"], pd["link"], pd.get("done_at")))
    cur.execute("DELETE FROM custom_tasks")
    for ct in data.get("custom_tasks", []):
        cur.execute("INSERT INTO custom_tasks (title, link, reward, active) VALUES (?,?,?,?)",
                    (ct["title"], ct["link"], ct["reward"], ct.get("active", 1)))
    conn.commit()
    conn.close()
    return count


# ============ ПРИВАТКА ============
def build_priv_buttons():
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
            await bot.send_message(referrer,
                "🎉 По твоей ссылке зашёл новый друг!\n"
                "Он должен зайти в профиль и забрать бонус — тогда ты получишь звёзды.")
        except Exception:
            pass

    if get_setting("priv_enabled") == "1":
        priv_text = get_setting("priv_text")
        kb = build_priv_buttons()
        if kb:
            await message.answer(priv_text, reply_markup=kb, parse_mode="HTML")
        else:
            await message.answer(priv_text, parse_mode="HTML")

    if pf_enabled():
        try:
            limit = int(get_setting("piarflow_entry_count"))
        except Exception:
            limit = 6
        sponsors = await pf_get_sponsors(message.from_user.id, limit)
        if sponsors:
            links = [s.get("link") or s.get("url") for s in sponsors if (s.get("link") or s.get("url"))]
            passed = await pf_all_passed_once(message.from_user.id, links)
            if not passed:
                await show_pf_sponsors(message, sponsors, "entry")
                return

    welcome = get_setting("welcome_text")
    await message.answer(welcome, reply_markup=main_menu())


async def show_pf_sponsors(message, sponsors, context):
    buttons = []
    row = []
    for s in sponsors:
        link = s.get("link") or s.get("url")
        name = s.get("name") or s.get("title") or "Подписаться"
        if not link:
            continue
        row.append(InlineKeyboardButton(text=f"📢 {name}", url=link))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    if context == "entry":
        buttons.append([InlineKeyboardButton(text="✅ Я подписался", callback_data="pf_entry_check")])
    elif context == "withdraw":
        buttons.append([InlineKeyboardButton(text="✅ Подтвердить", callback_data="pf_wd_check")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = ("✨ <b>Подпишись на спонсоров ниже</b>\n\n"
            "После подписки нажми «✅ Подтвердить» 👇")
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@dp.callback_query(F.data == "pf_entry_check")
async def pf_entry_check(call: CallbackQuery):
    await call.answer()
    limit = int(get_setting("piarflow_entry_count"))
    sponsors = await pf_get_sponsors(call.from_user.id, limit)
    links = [s.get("link") or s.get("url") for s in sponsors if (s.get("link") or s.get("url"))]

    try:
        msg = await call.message.answer("⏳ Проверяю подписку, подожди...")
    except Exception:
        msg = None

    passed = await pf_all_passed(call.from_user.id, links, retries=3, delay=7)

    if not passed:
        if msg:
            try:
                await msg.edit_text("❌ Ты ещё не подписался на все каналы. Попробуй ещё раз.")
            except Exception:
                pass
        return

    if msg:
        try:
            await msg.delete()
        except Exception:
            pass
    try:
        await call.message.delete()
    except Exception:
        pass
    welcome = get_setting("welcome_text")
    await call.message.answer(welcome, reply_markup=main_menu())


# ============ ЗАРАБОТАТЬ ============
@dp.message(F.text == "⭐ Заработать звёзды")
async def earn(message: Message):
    me = await bot.get_me()
    ref_bonus = get_setting("ref_bonus")
    refs = get_confirmed_refs_count(message.from_user.id)
    ref_link = f"https://t.me/{me.username}?start=ref_{message.from_user.id}"
    share_text = "Заходи в бота, тут раздают звёзды ⭐"
    share_url = (f"https://t.me/share/url?url={quote(ref_link, safe='')}"
                 f"&text={quote(share_text, safe='')}")
    text = (
        f"Приглашай пользователей в бота и получай по <b>{ref_bonus}</b> 🌟 "
        f"как только они подпишутся на каналы!\n\n"
        f"🔗 <b>Ваша ссылка:</b>\n{ref_link}\n\n"
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


# ============ ПРОФИЛЬ ============
@dp.message(F.text == "👤 Профиль")
async def profile(message: Message):
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
        reply_markup=profile_kb(), parse_mode="HTML"
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
            await bot.send_message(referrer,
                f"🎉 Друг подтвердил реферал!\n💫 Тебе начислено +{ref_bonus} ⭐")
        except Exception:
            pass
    await call.answer(f"🎁 +{amount} ⭐", show_alert=True)
    try:
        await call.message.edit_text(
            f"🎁 <b>Ежедневный бонус получен!</b>\n\n💫 +{amount} ⭐\n💰 Баланс: <b>{balance}</b> ⭐",
            parse_mode="HTML")
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


# ============ ЗАДАНИЯ ============
@dp.message(F.text == "📋 Задания")
async def tasks_menu(message: Message):
    await message.answer("⏳ Ищу новое задание...")
    task = await get_next_task(message.from_user.id)
    if not task:
        await message.answer("❌ Пока нет доступных заданий. Попробуй позже.")
        return
    await show_task(message, task)


async def get_next_task(user_id):
    if pf_enabled():
        try:
            limit = int(get_setting("piarflow_task_limit") or 20)
        except Exception:
            limit = 20
        sponsors = await pf_get_sponsors(user_id, limit)
        for s in sponsors:
            link = s.get("link") or s.get("url")
            if not link:
                continue
            if piarflow_is_done(user_id, link):
                continue
            status = s.get("status") or s.get("subscribed")
            if status in ("subscribed", True, "ok", "active"):
                piarflow_mark_done(user_id, link)
                continue
            reward = int(get_setting("piarflow_task_reward"))
            return {"type": "pf", "id": link, "link": link, "reward": reward}

    for t in list_custom_tasks():
        tid, title, link, reward, active = t
        if not active:
            continue
        if piarflow_is_done(user_id, f"custom_{tid}"):
            continue
        return {"type": "custom", "id": f"custom_{tid}", "link": link,
                "reward": reward, "title": title}
    return None


async def show_task(message, task):
    reward = task.get("reward", 10)
    text = (
        f"❄️ <b>Собирай Звёзды за простые задания!</b> 👇\n\n"
        f"✅ Подпишись на канал и нажми «Подтвердить»\n\n"
        f"❌ За отписку или блокировку ресурса, вы получите бан\n\n"
        f"<b>Вознаграждение: +{reward} 🌟</b>"
    )
    kb = task_kb(task["link"], str(task["id"]))
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@dp.callback_query(F.data == "task_skip")
async def task_skip(call: CallbackQuery):
    try:
        await call.message.delete()
    except Exception:
        pass
    task = await get_next_task(call.from_user.id)
    if not task:
        await call.message.answer("❌ Больше нет заданий.")
        return
    await show_task(call.message, task)


@dp.callback_query(F.data.startswith("task_check:"))
async def task_check(call: CallbackQuery):
    source = call.data.split(":", 1)[1]
    user_id = call.from_user.id

    if source.startswith("custom_"):
        tid = int(source.replace("custom_", ""))
        t = get_custom_task(tid)
        if not t:
            await call.answer("Задание не найдено", show_alert=True)
            return
        _, title, link, reward, active = t
        key = f"custom_{tid}"
    else:
        link = source
        reward = int(get_setting("piarflow_task_reward"))
        key = link

    await call.answer()
    try:
        msg = await call.message.answer("⏳ Проверяю подписку, подожди...")
    except Exception:
        msg = None

    subscribed = False
    for i in range(3):
        subscribed = await pf_check_one(user_id, link)
        if subscribed:
            break
        if i < 2:
            await asyncio.sleep(7)

    if not subscribed:
        if msg:
            try:
                await msg.edit_text("❌ Ты ещё не подписался. Попробуй ещё раз.")
            except Exception:
                pass
        return

    if piarflow_is_done(user_id, key):
        if msg:
            try:
                await msg.edit_text("✅ Уже засчитано")
            except Exception:
                pass
        return

    piarflow_mark_done(user_id, key)
    add_balance(user_id, reward)

    if msg:
        try:
            await msg.delete()
        except Exception:
            pass
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(f"✅ Задание выполнено! +{reward} ⭐")

    task = await get_next_task(user_id)
    if task:
        await show_task(call.message, task)


# ============ ВЫВОД ============
@dp.message(F.text == "💸 Вывести звёзды")
async def withdraw(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❣️ <b>Выбери подарок</b>",
                         reply_markup=gifts_kb(), parse_mode="HTML")


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
        await call.answer(f"❌ Не хватает {need} ⭐\nНужно: {price} ⭐\nУ тебя: {balance} ⭐",
                          show_alert=True)
        return

    if pf_enabled():
        try:
            limit = int(get_setting("piarflow_withdraw_count"))
        except Exception:
            limit = 6
        sponsors = await pf_get_sponsors(call.from_user.id, limit)
        if sponsors:
            links = [s.get("link") or s.get("url") for s in sponsors if (s.get("link") or s.get("url"))]
            passed = await pf_all_passed_once(call.from_user.id, links)
            if not passed:
                await state.update_data(gift_key=key)
                await state.set_state(WithdrawFlow.waiting_sub)
                await call.message.edit_text(
                    "✨ <b>Чтобы вывести звёзды, пройди проверку ниже:</b>\n\n"
                    "📢 Подпишись на спонсоров и нажми «✅ Подтвердить»",
                    parse_mode="HTML")
                await show_pf_sponsors(call.message, sponsors, "withdraw")
                return

    await create_order(call, key)


@dp.callback_query(F.data == "pf_wd_check")
async def pf_wd_check(call: CallbackQuery, state: FSMContext):
    await call.answer()
    limit = int(get_setting("piarflow_withdraw_count"))
    sponsors = await pf_get_sponsors(call.from_user.id, limit)
    links = [s.get("link") or s.get("url") for s in sponsors if (s.get("link") or s.get("url"))]

    try:
        msg = await call.message.answer("⏳ Проверяю подписку, подожди...")
    except Exception:
        msg = None

    passed = await pf_all_passed(call.from_user.id, links, retries=3, delay=7)

    if not passed:
        if msg:
            try:
                await msg.edit_text("❌ Ты ещё не подписался на все каналы.")
            except Exception:
                pass
        return

    data = await state.get_data()
    key = data.get("gift_key")
    if not key:
        await state.clear()
        if msg:
            try:
                await msg.edit_text("❌ Выбери подарок заново.")
            except Exception:
                pass
        return

    await state.clear()
    if msg:
        try:
            await msg.delete()
        except Exception:
            pass
    try:
        await call.message.delete()
    except Exception:
        pass
    await create_order(call, key)


async def create_order(call: CallbackQuery, key):
    name, price = GIFTS[key]
    balance = get_balance(call.from_user.id)
    if balance < price:
        await call.answer(f"❌ Нужно {price} ⭐", show_alert=True)
        return
    wid = create_withdrawal(call.from_user.id, price, key)
    uname = f"@{call.from_user.username}" if call.from_user.username else "без username"
    text = (f"✅ <b>Заявка #{wid} создана!</b>\n\n🎁 Подарок: {name}\n"
            f"💰 Сумма: {price} ⭐\n⏳ Ожидай — админ отправит подарок вручную.")
    try:
        await call.message.edit_text(text, parse_mode="HTML")
    except Exception:
        await call.message.answer(text, parse_mode="HTML")
    try:
        await bot.send_message(ADMIN_ID,
            f"💸 <b>Новая заявка #{wid}</b>\n\n👤 {uname}\n"
            f"🆔 <code>{call.from_user.id}</code>\n🎁 {name}\n💰 {price} ⭐",
            reply_markup=admin_wd_kb(wid), parse_mode="HTML")
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
        f"🛠 <b>АДМИН-ПАНЕЛЬ</b>\n\n👥 Пользователей: <b>{s['total']}</b>\n"
        f"📋 Заявок в ожидании: <b>{s['pending']}</b>",
        reply_markup=admin_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "admin_back")
async def admin_back(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await state.clear()
    s = get_stats()
    try:
        await call.message.edit_text(
            f"🛠 <b>АДМИН-ПАНЕЛЬ</b>\n\n👥 Пользователей: <b>{s['total']}</b>\n"
            f"📋 Заявок в ожидании: <b>{s['pending']}</b>",
            reply_markup=admin_kb(), parse_mode="HTML")
    except Exception:
        await call.message.answer("🛠 Админ-панель", reply_markup=admin_kb())


# --- PIARFLOW ---
def pf_menu_text():
    enabled = pf_enabled()
    key = get_setting("piarflow_key")
    return (
        f"🎯 <b>PiarFlow</b>\n\n"
        f"Статус: {'🟢 включен' if enabled else '🔴 выключен'}\n"
        f"🔑 Ключ: <code>{key[:20]}...</code>\n"
        f"🆔 Chat ID: <code>{BOT_ID}</code>\n\n"
        f"📥 ОП на входе: <b>{get_setting('piarflow_entry_count')}</b>\n"
        f"💸 ОП на выводе: <b>{get_setting('piarflow_withdraw_count')}</b>\n"
        f"💰 Награда за задание: <b>{get_setting('piarflow_task_reward')}</b> ⭐"
    )


@dp.callback_query(F.data == "piarflow_menu")
async def piarflow_menu(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text(pf_menu_text(),
                                 reply_markup=piarflow_kb(pf_enabled()),
                                 parse_mode="HTML")


@dp.callback_query(F.data == "pf_toggle")
async def pf_toggle(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    current = get_setting("piarflow_enabled") == "1"
    set_setting("piarflow_enabled", "0" if current else "1")
    await call.answer("✅ Изменено")
    await call.message.edit_text(pf_menu_text(),
                                 reply_markup=piarflow_kb(not current),
                                 parse_mode="HTML")


@dp.callback_query(F.data == "pf_edit_key")
async def pf_edit_key(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("🔑 Пришли новый API-ключ PiarFlow:")
    await state.set_state(PiarFlowEdit.waiting_key)


@dp.message(PiarFlowEdit.waiting_key)
async def pf_save_key(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    set_setting("piarflow_key", message.text.strip())
    await state.clear()
    await message.answer("✅ Ключ сохранён", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "pf_edit_reward")
async def pf_edit_reward(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("💰 Сколько звёзд давать за задание PiarFlow?")
    await state.set_state(PiarFlowEdit.waiting_reward)


@dp.message(PiarFlowEdit.waiting_reward)
async def pf_save_reward(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        val = int(message.text.strip())
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    set_setting("piarflow_task_reward", val)
    await state.clear()
    await message.answer(f"✅ Награда: {val} ⭐", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "pf_edit_entry")
async def pf_edit_entry(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("📥 Сколько ОП показывать на входе?")
    await state.set_state(PiarFlowEdit.waiting_entry)


@dp.message(PiarFlowEdit.waiting_entry)
async def pf_save_entry(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        val = int(message.text.strip())
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    set_setting("piarflow_entry_count", val)
    await state.clear()
    await message.answer(f"✅ Сохранено: {val}", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "pf_edit_wd")
async def pf_edit_wd(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("💸 Сколько ОП показывать на выводе?")
    await state.set_state(PiarFlowEdit.waiting_wd)


@dp.message(PiarFlowEdit.waiting_wd)
async def pf_save_wd(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        val = int(message.text.strip())
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    set_setting("piarflow_withdraw_count", val)
    await state.clear()
    await message.answer(f"✅ Сохранено: {val}", reply_markup=back_admin_kb())


# --- СВОИ ЗАДАНИЯ ---
@dp.callback_query(F.data == "tasks_menu")
async def tasks_menu_admin(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text(
        "📌 <b>Свои задания</b>\n\nЗдесь ты создаёшь задания, которые показываются юзерам.",
        reply_markup=tasks_admin_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "task_add")
async def task_add(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("📝 Название задания (например, «Подпишись на канал»):")
    await state.set_state(TaskAdd.waiting_title)


@dp.message(TaskAdd.waiting_title)
async def task_add_title(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.update_data(t_title=message.text.strip())
    await message.answer("🔗 Ссылка на канал (https://t.me/...):")
    await state.set_state(TaskAdd.waiting_link)


@dp.message(TaskAdd.waiting_link)
async def task_add_link(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    link = message.text.strip()
    if not link.startswith("http"):
        await message.answer("⚠️ Ссылка должна начинаться с http.")
        return
    await state.update_data(t_link=link)
    await message.answer("💰 Сколько звёзд за выполнение?")
    await state.set_state(TaskAdd.waiting_reward)


@dp.message(TaskAdd.waiting_reward)
async def task_add_reward(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        reward = int(message.text.strip())
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    data = await state.get_data()
    create_custom_task(data["t_title"], data["t_link"], reward)
    await state.clear()
    await message.answer("✅ Задание создано", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "task_list")
async def task_list_admin(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    rows = list_custom_tasks()
    if not rows:
        await call.answer("Пусто", show_alert=True)
        return
    text = "📜 <b>Свои задания</b>\n\n"
    for tid, title, link, reward, active in rows:
        icon = "🟢" if active else "🔴"
        text += f"{icon} #{tid} — {title} — {reward}⭐\n{link}\n\n"
    await call.message.answer(text, parse_mode="HTML")


@dp.callback_query(F.data == "task_delete")
async def task_delete(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("🗑 Пришли ID задания для удаления:")
    await state.set_state(TaskDelete.waiting_id)


@dp.message(TaskDelete.waiting_id)
async def task_delete_id(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        tid = int(message.text.strip())
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    delete_custom_task(tid)
    await state.clear()
    await message.answer("🗑 Удалено", reply_markup=back_admin_kb())


# --- БЭКАП ---
@dp.callback_query(F.data == "backup_help")
async def backup_help(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text(
        "📦 <b>Бэкап</b>\n\n"
        "📤 <b>Выгрузка:</b> команда <code>/backup</code> — бот пришлёт JSON.\n\n"
        "📥 <b>Загрузка:</b> просто отправь боту JSON-файл.",
        reply_markup=back_admin_kb(), parse_mode="HTML")


@dp.message(Command("backup"))
async def backup_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("📦 Собираю бэкап...")
    data = export_users_to_json()
    fname = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        file = FSInputFile(fname)
        await message.answer_document(file,
            caption=(f"📦 <b>Бэкап</b>\n\n👥 Юзеров: <b>{len(data['users'])}</b>\n"
                     f"👥 Рефералов: <b>{len(data['referrals'])}</b>\n"
                     f"🎟 Промокодов: <b>{len(data['promos'])}</b>\n"
                     f"💸 Заявок: <b>{len(data['withdrawals'])}</b>\n"
                     f"📌 Своих заданий: <b>{len(data['custom_tasks'])}</b>"),
            parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    try:
        os.remove(fname)
    except Exception:
        pass


@dp.message(F.document)
async def restore_doc(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    doc = message.document
    if not doc.file_name.endswith(".json"):
        return
    try:
        file = await bot.get_file(doc.file_id)
        fname = f"restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        await bot.download_file(file.file_path, fname)
        with open(fname, "r", encoding="utf-8") as f:
            data = json.load(f)
        count = import_users_from_json(data)
        try:
            os.remove(fname)
        except Exception:
            pass
        await message.answer(f"✅ <b>Восстановлено</b>\n\n👥 Юзеров: <b>{count}</b>",
                             parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


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
            f"💸 <b>Заявка #{wid}</b>\n👤 {uname}\n🆔 <code>{user_id}</code>\n"
            f"🎁 {name}\n💰 {amount} ⭐",
            reply_markup=admin_wd_kb(wid), parse_mode="HTML")


@dp.callback_query(F.data.startswith("wd_ok:"))
async def wd_ok(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    wid = int(call.data.split(":")[1])
    row = get_withdrawal(wid)
    if not row:
        await call.answer("Не найдена"); return
    _, user_id, amount, gift_key, status = row
    if status != "pending":
        await call.answer("Уже обработана"); return
    set_withdrawal_status(wid, "completed")
    name = GIFTS.get(gift_key, ("подарок", 0))[0]
    try:
        await bot.send_message(user_id,
            f"✅ <b>Заявка #{wid} одобрена!</b>\n\n🎁 {name} отправлен тебе.",
            parse_mode="HTML")
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
        await call.answer("Не найдена"); return
    _, user_id, amount, gift_key, status = row
    if status != "pending":
        await call.answer("Уже обработана"); return
    set_withdrawal_status(wid, "rejected")
    add_balance(user_id, amount)
    try:
        await bot.send_message(user_id, f"❌ Заявка #{wid} отклонена.\n{amount} ⭐ возвращены.")
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
    text = "📜 <b>История (50)</b>\n\n"
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
    text = (f"🎛 <b>Приватка</b>\n\n"
            f"Статус: {'🟢 включена' if enabled else '🔴 выключена'}\n\n"
            f"<b>Текст:</b>\n<i>{get_setting('priv_text')}</i>\n\n"
            f"<b>Кнопки:</b>\n<code>{get_setting('priv_buttons')}</code>")
    await call.message.edit_text(text, reply_markup=priv_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "priv_edit_text")
async def priv_edit_text(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("✏️ Пришли новый текст приватки:")
    await state.set_state(PrivEdit.waiting_text)


@dp.message(PrivEdit.waiting_text)
async def priv_save_text(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    set_setting("priv_text", message.text)
    set_setting("priv_enabled", "1")
    await state.clear()
    await message.answer("✅ Текст сохранён", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "priv_edit_buttons")
async def priv_edit_buttons(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer(
        "🔗 Пришли кнопки:\n\n<b>Столбиком:</b>\n"
        "<code>Кнопка - https://t.me/xxx\nКнопка 2 - https://t.me/yyy</code>\n\n"
        "<b>В ряд:</b>\n<code>К1 - https://t.me/x & К2 - https://t.me/y</code>",
        parse_mode="HTML")
    await state.set_state(PrivEdit.waiting_buttons)


@dp.message(PrivEdit.waiting_buttons)
async def priv_save_buttons(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.strip()
    ok = False
    for line in text.split("\n"):
        for pair in line.split("&"):
            pair = pair.strip()
            if " - " in pair:
                parts = pair.split(" - ", 1)
                if len(parts) == 2 and parts[0].strip() and parts[1].strip().startswith("http"):
                    ok = True
    if not ok:
        await message.answer("⚠️ Неверный формат.")
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
    await call.answer("🗑 Удалено")
    await call.message.edit_text("🗑 Приватка удалена", reply_markup=back_admin_kb())


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
        f"📢 <b>Предпросмотр:</b>\n\n{message.text}\n\n<i>Получателей: {len(users)}</i>",
        reply_markup=broadcast_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "broadcast_confirm")
async def broadcast_confirm(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    text = data.get("bc_text")
    if not text:
        await call.answer("Текст потерян"); return
    await state.clear()
    users = get_all_user_ids()
    await call.message.edit_text(f"📢 Начинаю... (0/{len(users)})")
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
    await call.message.edit_text(f"✅ Готово!\n\nОтправлено: {sent}/{len(users)}",
                                 reply_markup=back_admin_kb())


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
        await message.answer("⚠️ ID — число."); return
    uid = int(text)
    u = get_user(uid)
    if not u:
        await message.answer("⚠️ Не найден."); return
    await state.update_data(give_uid=uid)
    await message.answer(f"👤 @{u[1] or '—'} — баланс: {u[2]} ⭐\n\nПришли сумму (+ или −):")
    await state.set_state(GiveFlow.waiting_amount)


@dp.message(GiveFlow.waiting_amount)
async def give_amount(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        amount = int(message.text.strip())
    except Exception:
        await message.answer("⚠️ Нужно число."); return
    data = await state.get_data()
    uid = data.get("give_uid")
    if not uid:
        await state.clear(); return
    add_balance(uid, amount)
    new_balance = get_balance(uid)
    await state.clear()
    await message.answer(f"✅ {amount:+d} ⭐\n🆔 <code>{uid}</code>\n💰 Баланс: <b>{new_balance}</b> ⭐",
                         reply_markup=back_admin_kb(), parse_mode="HTML")


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
        await message.answer("⚠️ ID — число."); return
    uid = int(text)
    u = get_user(uid)
    if not u:
        await message.answer("⚠️ Не найден."); return
    balance = u[2]
    refs = get_confirmed_refs_count(uid)
    pending = get_pending_refs_count(uid)
    reg = (u[6] or "")[:16].replace("T", " ")
    await state.clear()
    await message.answer(
        f"👤 <b>Юзер</b>\n\n🧑 @{u[1] or '—'}\n🆔 <code>{uid}</code>\n"
        f"⭐ Баланс: <b>{balance}</b>\n👥 Друзей: <b>{refs}</b>\n"
        f"⏳ Ожидают: <b>{pending}</b>\n📅 Регистрация: {reg}",
        reply_markup=user_view_kb(uid), parse_mode="HTML")


@dp.callback_query(F.data.startswith("user_refs:"))
async def user_refs(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    uid = int(call.data.split(":")[1])
    rows = get_user_referrals(uid, 100)
    if not rows:
        await call.answer("Пусто"); return
    text = f"👥 <b>Рефералы <code>{uid}</code></b>\n\n"
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
    await call.message.answer("🎟 Название промокода:")
    await state.set_state(PromoCreate.waiting_code)


@dp.message(PromoCreate.waiting_code)
async def promo_code_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    code = message.text.strip().upper()
    if not code.isalnum() or len(code) < 3:
        await message.answer("⚠️ Только буквы/цифры, минимум 3."); return
    await state.update_data(code=code)
    await message.answer(f"Код: <b>{code}</b>\n\nСколько звёзд?", parse_mode="HTML")
    await state.set_state(PromoCreate.waiting_amount)


@dp.message(PromoCreate.waiting_amount)
async def promo_amount_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        amount = int(message.text)
    except Exception:
        await message.answer("⚠️ Нужно число."); return
    await state.update_data(amount=amount)
    await message.answer(f"Звёзд: <b>{amount}</b>\n\nСколько активаций?", parse_mode="HTML")
    await state.set_state(PromoCreate.waiting_uses)


@dp.message(PromoCreate.waiting_uses)
async def promo_uses_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        uses = int(message.text)
    except Exception:
        await message.answer("⚠️ Нужно число."); return
    data = await state.get_data()
    create_promo(data["code"], data["amount"], uses)
    await state.clear()
    await message.answer(f"✅ Промокод <code>{data['code']}</code> создан ({data['amount']} ⭐, {uses} активаций)",
                         parse_mode="HTML")


@dp.callback_query(F.data == "promo_list")
async def promo_list_cb(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    rows = list_promos()
    if not rows:
        await call.answer("Пусто"); return
    text = "📜 <b>Промокоды</b>\n\n"
    for code, amount, mx, used, active in rows:
        status = "🟢" if active and used < mx else "🔴"
        text += f"{status} <code>{code}</code> — {amount} ⭐ | {used}/{mx}\n"
    await call.message.answer(text, parse_mode="HTML")


@dp.callback_query(F.data == "promo_delete")
async def promo_delete_cb(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("🗑 Код для удаления:")
    await state.set_state(PromoDelete.waiting_code)


@dp.message(PromoDelete.waiting_code)
async def promo_delete_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    code = message.text.strip().upper()
    if not get_promo(code):
        await message.answer("⚠️ Нет такого."); return
    delete_promo(code)
    await state.clear()
    await message.answer(f"🗑 Удалён <code>{code}</code>", parse_mode="HTML")


# --- СТАТИСТИКА ---
@dp.callback_query(F.data == "stats")
async def stats(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    s = get_stats()
    await call.message.edit_text(
        f"📊 <b>СТАТИСТИКА</b>\n\n👥 Всего юзеров: <b>{s['total']}</b>\n"
        f"📅 Сегодня: <b>{s['today']}</b>\n\n📋 Заявок: <b>{s['pending']}</b>\n"
        f"✅ Выполнено: <b>{s['done']}</b>\n💫 Выдано звёзд: <b>{s['total_stars']}</b>",
        reply_markup=back_admin_kb(), parse_mode="HTML")


# --- НАСТРОЙКИ ---
@dp.callback_query(F.data == "settings")
async def settings(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text(
        f"⚙️ <b>НАСТРОЙКИ</b>\n\n👥 Бонус за реферала: <b>{get_setting('ref_bonus')}</b> ⭐\n"
        f"🎁 Ежедневный бонус: <b>{get_setting('daily_bonus')}</b> ⭐\n"
        f"💸 Минимум вывода: <b>{get_setting('min_withdraw')}</b> ⭐\n"
        f"✏️ Текст под меню: <i>{get_setting('welcome_text')}</i>",
        reply_markup=settings_kb(), parse_mode="HTML")


@dp.callback_query(F.data.startswith("set:"))
async def set_value_ask(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    key = call.data.split(":")[1]
    prompts = {
        "ref_bonus": "👥 Бонус за реферала (число):",
        "daily_bonus": "🎁 Ежедневный бонус (число):",
        "min_withdraw": "💸 Минимум вывода (число):",
        "welcome_text": "✏️ Текст под меню:",
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
            await message.answer("⚠️ Нужно число."); return
    set_setting(key, value)
    await state.clear()
    await message.answer(f"✅ Сохранено: {key}", reply_markup=back_admin_kb())


# ============ ФОН ============
async def referral_watcher():
    while True:
        try:
            for rid, user_id, referrer_id in get_refs_to_remind():
                u = get_user(user_id)
                uname = f"@{u[1]}" if u and u[1] else "друг"
                try:
                    await bot.send_message(referrer_id,
                        f"⏳ {uname} зашёл по твоей ссылке, но не забрал бонус.")
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
                        await bot.send_message(referrer_id,
                            f"⏰ Прошло {REFERRAL_DAYS} дней. Друзья не забрали бонус:\n{lines}",
                            parse_mode="HTML")
                    except Exception:
                        pass
        except Exception as e:
            print("Watcher error:", e)
        await asyncio.sleep(60)


# ============ ЗАПУСК ============
async def main():
    init_db()
    asyncio.create_task(referral_watcher())
    print("Бот запущен")
    print(f"BOT_ID: {BOT_ID}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
