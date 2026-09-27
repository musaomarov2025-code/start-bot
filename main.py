import asyncio
import json
import os
from datetime import datetime, timedelta
from urllib.parse import quote

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile,
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from config import (
    BOT_TOKEN, ADMIN_ID, GIFTS, GIFTS_EMOJI, REFERRAL_DAYS, DB,
    BOTOHUB_TOKEN, BOTOHUB_URL, BOTOHUB_TASKS_URL,
)
from database import (
    init_db, get_setting, set_setting,
    get_user, add_user, update_username, add_balance, get_balance,
    get_place, can_take_bonus, set_bonus_taken, get_user_display,
    get_all_user_ids,
    create_pending_referral, get_pending_refs_count,
    get_confirmed_refs_count, get_user_referrals,
    create_ref_progress, get_ref_progress, increment_ref_tasks,
    set_ref_notified, mark_ref_paid,
    get_refs_to_notify_5min, get_refs_to_notify_10min,
    expire_old_ref_progress,
    create_withdrawal, get_withdrawal, get_pending_withdrawals, set_withdrawal_status,
    get_withdrawal_history,
    get_stats, get_top_balance, get_top_refs,
    create_promo, get_promo, list_promos, delete_promo, activate_promo,
    add_custom_op, list_custom_ops, delete_custom_op,
    bh_reward_mark, bh_reward_was_given,
    add_custom_task, list_custom_tasks, get_custom_task, delete_custom_task,
    get_next_custom_task, mark_custom_task_done,
    get_total_tasks_done,
)
from keyboards import (
    main_menu, earn_kb, profile_kb, gifts_kb, task_kb, task_done_kb,
    daily_bonus_kb, daily_back_kb, promo_cancel_kb,
    admin_kb, admin_wd_kb, priv_kb, broadcast_kb, settings_kb,
    promos_kb, user_view_kb, back_admin_kb,
    bh_kb, tasks_kb, ctasks_kb, ctask_type_kb, cop_kb, cop_type_kb, stats_kb,
    op_menu_kb, ref_menu_kb,
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

BOT_ID = int(BOT_TOKEN.split(":")[0]) if BOT_TOKEN else 0


# ================== FSM ==================
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

class BHEdit(StatesGroup):
    waiting_text = State()
    waiting_btn = State()
    waiting_entry = State()
    waiting_wd = State()

class TasksEdit(StatesGroup):
    waiting_reward = State()
    waiting_text = State()
    waiting_btn_go = State()
    waiting_btn_check = State()
    waiting_btn_skip = State()

class CTaskAdd(StatesGroup):
    waiting_type = State()
    waiting_title = State()
    waiting_link = State()
    waiting_chat_id = State()

class CTaskDel(StatesGroup):
    waiting_id = State()

class CopAdd(StatesGroup):
    waiting_title = State()
    waiting_link = State()

class CopDel(StatesGroup):
    waiting_id = State()

class OpEdit(StatesGroup):
    waiting_text = State()
    waiting_link = State()
    waiting_target = State()

class RefEdit(StatesGroup):
    waiting_bonus = State()
    waiting_required = State()
    waiting_days = State()
    waiting_earn_text = State()
    waiting_notify_start = State()
    waiting_notify_5min = State()
    waiting_notify_10min = State()
    waiting_notify_done = State()


# ============ BOTOHUB ОП ============
def bh_enabled():
    return get_setting("botohub_enabled") == "1"


async def bh_get_tasks(chat_id, count):
    if not BOTOHUB_TOKEN:
        return {"tasks": [], "completed": True, "skip": True}
    payload = {"chat_id": chat_id, "max_op": count}
    headers = {"Auth": BOTOHUB_TOKEN, "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(BOTOHUB_URL, json=payload, headers=headers,
                              timeout=aiohttp.ClientTimeout(total=15)) as r:
                return await r.json()
    except Exception as e:
        print("Botohub ОП error:", e)
        return {"tasks": [], "completed": True, "skip": True}


# ============ BOTOHUB ЗАДАНИЯ ============
def tasks_enabled():
    return get_setting("tasks_enabled") == "1"


async def bh_get_task(chat_id, skip=False):
    if not BOTOHUB_TOKEN:
        return None
    payload = {"chat_id": chat_id, "is_task": True, "skip": skip}
    headers = {"Auth": BOTOHUB_TOKEN, "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(BOTOHUB_TASKS_URL, json=payload, headers=headers,
                              timeout=aiohttp.ClientTimeout(total=15)) as r:
                return await r.json()
    except Exception as e:
        print("Botohub tasks error:", e)
        return None


async def bh_check_link(user_id):
    if not BOTOHUB_TOKEN:
        return False
    payload = {"chat_id": user_id, "is_task": True, "skip": False}
    headers = {"Auth": BOTOHUB_TOKEN, "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(BOTOHUB_TASKS_URL, json=payload, headers=headers,
                              timeout=aiohttp.ClientTimeout(total=15)) as r:
                data = await r.json()
                return bool(data.get("prev_success"))
    except Exception as e:
        print("bh_check_link error:", e)
        return False


# ============ ПРОВЕРКА СВОИХ ЗАДАНИЙ ============
async def check_custom_task(user_id, check_type, check_target):
    """True — подписан / без проверки; False — не подписан."""
    if not check_type or check_type == "bot" or not check_target:
        return True
    target = check_target
    if isinstance(target, str) and target.lstrip("-").isdigit():
        target = int(target)
    try:
        m = await bot.get_chat_member(target, user_id)
        return m.status in ("member", "administrator", "creator")
    except Exception as e:
        print(f"check_custom_task {check_target}: {e}")
        return True


# ============ ПРОВЕРКА ОП НА СТАРТЕ ============
def op_enabled():
    return get_setting("op_enabled") == "1"


async def op_check_sub(user_id):
    """Проверка ОП. True — пропускаем. Если target пусто — на доверии (всегда True)."""
    if not op_enabled():
        return True
    target = (get_setting("op_check_target") or "").strip()
    if not target:
        return True  # на доверии
    t = target
    if t.lstrip("-").isdigit():
        t = int(t)
    try:
        m = await bot.get_chat_member(t, user_id)
        return m.status in ("member", "administrator", "creator")
    except Exception as e:
        print(f"op_check_sub {target}: {e}")
        return True


def op_kb():
    sub = get_setting("op_btn_sub") or "Подписаться"
    done = get_setting("op_btn_done") or "Я подписался"
    link = get_setting("op_link") or "https://t.me/"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=sub, url=link,
                              icon_custom_emoji_id="6026034017608930629")],
        [InlineKeyboardButton(text=done, callback_data="op_check",
                              icon_custom_emoji_id="6026257381678124710",
                              style="success")],
    ])


async def send_op_screen(message):
    text = get_setting("op_text")
    try:
        await message.answer(text, reply_markup=op_kb(), parse_mode="HTML")
    except Exception as e:
        print("send_op_screen error:", e)


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


# ============ БЭКАП ============
def export_users_to_json():
    import sqlite3
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, balance, last_bonus, referrer_id, registered_at FROM users")
    users = [{"user_id": r[0], "username": r[1], "balance": r[2],
              "last_bonus": r[3], "referrer_id": r[4], "registered_at": r[5]}
             for r in cur.fetchall()]
    cur.execute("SELECT user_id, referrer_id, tasks_done, started_at, status, paid FROM ref_progress")
    ref_progress = [{"user_id": r[0], "referrer_id": r[1], "tasks_done": r[2],
                     "started_at": r[3], "status": r[4], "paid": r[5]}
                    for r in cur.fetchall()]
    cur.execute("SELECT code, amount, max_uses, used, active FROM promos")
    promos = [{"code": r[0], "amount": r[1], "max_uses": r[2], "used": r[3], "active": r[4]}
              for r in cur.fetchall()]
    cur.execute("SELECT user_id, amount, gift, status, created_at FROM withdrawals")
    withdrawals = [{"user_id": r[0], "amount": r[1], "gift": r[2], "status": r[3], "created_at": r[4]}
                   for r in cur.fetchall()]
    cur.execute("SELECT key, value FROM settings")
    settings = {r[0]: r[1] for r in cur.fetchall()}
    cur.execute("SELECT id, title, link, type, active FROM custom_ops")
    custom_ops = [{"id": r[0], "title": r[1], "link": r[2], "type": r[3], "active": r[4]}
                  for r in cur.fetchall()]
    cur.execute("SELECT id, title, link, reward, active, check_type, check_target FROM custom_tasks")
    custom_tasks = [{"id": r[0], "title": r[1], "link": r[2], "reward": r[3], "active": r[4],
                     "check_type": r[5], "check_target": r[6]}
                    for r in cur.fetchall()]
    conn.close()
    return {"exported_at": datetime.now().isoformat(),
            "users": users, "ref_progress": ref_progress, "promos": promos,
            "withdrawals": withdrawals, "settings": settings,
            "custom_ops": custom_ops, "custom_tasks": custom_tasks}


def import_users_from_json(data):
    import sqlite3
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    count = 0
    for u in data.get("users", []):
        cur.execute("INSERT OR REPLACE INTO users (user_id, username, balance, last_bonus, referrer_id, registered_at) VALUES (?,?,?,?,?,?)",
                    (u["user_id"], u.get("username"), u.get("balance", 0),
                     u.get("last_bonus"), u.get("referrer_id"), u.get("registered_at")))
        count += 1
    cur.execute("DELETE FROM ref_progress")
    for rp in data.get("ref_progress", []):
        cur.execute(
            "INSERT INTO ref_progress (user_id, referrer_id, tasks_done, started_at, status, paid) "
            "VALUES (?,?,?,?,?,?)",
            (rp["user_id"], rp.get("referrer_id"), rp.get("tasks_done", 0),
             rp.get("started_at"), rp.get("status", "active"), rp.get("paid", 0)),
        )
    for p in data.get("promos", []):
        cur.execute("INSERT OR REPLACE INTO promos (code, amount, max_uses, used, active) VALUES (?,?,?,?,?)",
                    (p["code"], p["amount"], p["max_uses"], p.get("used", 0), p.get("active", 1)))
    cur.execute("DELETE FROM withdrawals")
    for w in data.get("withdrawals", []):
        cur.execute("INSERT INTO withdrawals (user_id, amount, gift, status, created_at) VALUES (?,?,?,?,?)",
                    (w["user_id"], w["amount"], w.get("gift"), w.get("status", "pending"), w.get("created_at")))
    cur.execute("DELETE FROM custom_ops")
    for co in data.get("custom_ops", []):
        cur.execute("INSERT INTO custom_ops (title, link, type, active) VALUES (?,?,?,?)",
                    (co["title"], co["link"], co["type"], co.get("active", 1)))
    cur.execute("DELETE FROM custom_tasks")
    for ct in data.get("custom_tasks", []):
        cur.execute("INSERT INTO custom_tasks (title, link, reward, active, check_type, check_target) VALUES (?,?,?,?,?,?)",
                    (ct["title"], ct["link"], ct.get("reward", 0), ct.get("active", 1),
                     ct.get("check_type", "bot"), ct.get("check_target", "")))
    conn.commit()
    conn.close()
    return count


# ============ ЭКРАН ОП (на выводе) ============
async def show_op_screen(chat_id, user_id, op_type, cb_data_confirm):
    count_key = "botohub_entry_count" if op_type == "entry" else "botohub_withdraw_count"
    try:
        count = int(get_setting(count_key))
    except Exception:
        count = 6

    buttons = []
    row = []
    btn_text = get_setting("botohub_btn_text")
    EMOJI_SUB = "5253742260054409879"
    EMOJI_OK = "6026257381678124710"

    customs = list_custom_ops(op_type)
    for i, (cid, title, link) in enumerate(customs, 1):
        row.append(InlineKeyboardButton(
            text=f"{btn_text} {i}", url=link, icon_custom_emoji_id=EMOJI_SUB))
        if len(row) == 2:
            buttons.append(row)
            row = []

    data = await bh_get_tasks(user_id, count)
    tasks = data.get("tasks", [])
    not_done = [t for t in tasks if not t.get("completed")]
    for i, t in enumerate(not_done, 1):
        link = t.get("url")
        if not link:
            continue
        row.append(InlineKeyboardButton(
            text=f"{btn_text} {i + len(customs)}", url=link, icon_custom_emoji_id=EMOJI_SUB))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(
        text="Я подписался", callback_data=cb_data_confirm, icon_custom_emoji_id=EMOJI_OK)])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = get_setting("botohub_text")
    await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")


# ============ ХЕЛПЕРЫ РЕФЕРАЛКИ ============
async def _notify_referrer(referrer_id, key, **kwargs):
    """Отправить рефереру сообщение из настроек key с подстановкой."""
    if not referrer_id:
        return
    template = get_setting(key)
    if not template:
        return
    try:
        text = template.format(**kwargs)
    except Exception as e:
        print(f"notify format error {key}: {e}")
        return
    try:
        await bot.send_message(referrer_id, text, parse_mode="HTML")
    except Exception as e:
        print(f"notify send error {key}: {e}")


async def _handle_task_done(user_id):
    """Инкремент прогресса реферала + награда рефереру при 5/5."""
    if get_setting("ref_tasks_enabled") != "1":
        return
    try:
        need = int(get_setting("ref_tasks_required") or 5)
    except Exception:
        need = 5
    try:
        bonus = float(get_setting("ref_tasks_bonus") or 3)
    except Exception:
        bonus = 3.0

    new_done, referrer_id, _ = increment_ref_tasks(user_id)
    if referrer_id is None:
        return

    if new_done is not None and new_done >= need:
        # награда рефереру
        add_balance(referrer_id, bonus)
        mark_ref_paid(user_id)
        display = get_user_display(user_id)
        await _notify_referrer(
            referrer_id, "ref_notify_done",
            username=display.lstrip("@"),
            bonus=f"{bonus:g}",
        )
        set_ref_notified(user_id, "notified_done")


# ============ ЗАДАНИЯ: ПОКАЗ ============
async def _show_next_task_or_done(message_or_call, user_id, delete_first=False):
    """Показывает следующее задание или экран 'всё выполнено'.
       message_or_call: Message для отправки нового, либо (msg, chat_id) кортеж."""
    # для случая удаления старого сообщения
    if isinstance(message_or_call, tuple):
        msg_obj, chat_id = message_or_call
        send_msg = msg_obj
    else:
        send_msg = message_or_call
        chat_id = message_or_call.chat.id

    # 1) Botohub
    data = await bh_get_task(user_id, skip=False)
    if data and not data.get("fake"):
        tasks = data.get("tasks", [])
        if tasks:
            await _send_task(send_msg, tasks[0], source="bh")
            return

    # 2) Свои
    custom = get_next_custom_task(user_id)
    if custom:
        tid, title, link, reward_db, ctype, ctarget = custom
        await _send_task(send_msg, link, source=f"ct:{tid}")
        return

    # 3) Всё выполнено
    try:
        bonus = float(get_setting("ref_tasks_bonus") or 3)
    except Exception:
        bonus = 3.0
    text = get_setting("task_done_text").format(bonus=f"{bonus:g}")
    await send_msg.answer(text, reply_markup=task_done_kb(), parse_mode="HTML")


async def _send_task(message, link, source="bh"):
    try:
        reward = float(get_setting("task_reward") or 0.45)
    except Exception:
        reward = 0.45
    text = get_setting("task_text").format(reward=f"{reward:g}")
    kb = task_kb(link, source)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


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

    # реферал засчитывается только новым юзерам и только если это не сам себя
    if is_new and referrer and referrer != message.from_user.id:
        create_pending_referral(message.from_user.id, referrer)
        create_ref_progress(message.from_user.id, referrer)
        display = message.from_user.username or f"ID {message.from_user.id}"
        await _notify_referrer(referrer, "ref_notify_start",
                               username=display.lstrip("@"))

    # приватка (всегда)
    if get_setting("priv_enabled") == "1":
        priv_text = get_setting("priv_text")
        kb = build_priv_buttons()
        if kb:
            await message.answer(priv_text, reply_markup=kb, parse_mode="HTML")
        else:
            await message.answer(priv_text, parse_mode="HTML")

    # пауза и ОП
    await asyncio.sleep(5)

    if op_enabled():
        if not await op_check_sub(message.from_user.id):
            await send_op_screen(message)
            return
        # на ОП подписан — дальше Botohub ОП, если есть
    # Botohub ОП (на старте всё ещё актуально для botohub_enabled)
    if bh_enabled() and BOTOHUB_TOKEN:
        try:
            count = int(get_setting("botohub_entry_count"))
        except Exception:
            count = 6
        data = await bh_get_tasks(message.from_user.id, count)
        tasks = data.get("tasks", [])
        customs = list_custom_ops("entry")
        not_done = [t for t in tasks if not t.get("completed")]
        if not_done or customs:
            await show_op_screen(message.chat.id, message.from_user.id, "entry", "bh_entry_check")
            return

    welcome = get_setting("welcome_text")
    await message.answer(welcome, reply_markup=main_menu())


@dp.callback_query(F.data == "op_check")
async def op_check_cb(call: CallbackQuery):
    await call.answer()
    if op_enabled():
        target = (get_setting("op_check_target") or "").strip()
        if target and not await op_check_sub(call.from_user.id):
            try:
                await call.message.answer("❌ Ты ещё не подписался. Попробуй снова.")
            except Exception:
                pass
            return
    # ОП пройден — идём в меню (или на Botohub ОП)
    try:
        await call.message.delete()
    except Exception:
        pass

    if bh_enabled() and BOTOHUB_TOKEN:
        try:
            count = int(get_setting("botohub_entry_count"))
        except Exception:
            count = 6
        data = await bh_get_tasks(call.from_user.id, count)
        tasks = data.get("tasks", [])
        customs = list_custom_ops("entry")
        not_done = [t for t in tasks if not t.get("completed")]
        if not_done or customs:
            await show_op_screen(call.from_user.id, call.from_user.id, "entry", "bh_entry_check")
            return

    await call.message.answer(get_setting("welcome_text"), reply_markup=main_menu())


@dp.callback_query(F.data == "bh_entry_check")
async def bh_entry_check(call: CallbackQuery):
    await call.answer()
    try:
        count = int(get_setting("botohub_entry_count"))
    except Exception:
        count = 6
    try:
        msg = await call.message.answer("⏳ Проверяю подписку, подожди...")
    except Exception:
        msg = None

    passed = False
    for i in range(3):
        data = await bh_get_tasks(call.from_user.id, count)
        tasks = data.get("tasks", [])
        not_done = [t for t in tasks if not t.get("completed")]
        if data.get("completed") or data.get("skip") or not not_done:
            passed = True
            break
        if i < 2:
            await asyncio.sleep(7)

    if not passed:
        if msg:
            try:
                await msg.edit_text("❌ Ты ещё не подписался. Попробуй ещё раз.")
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
    await call.message.answer(get_setting("welcome_text"), reply_markup=main_menu())


# ============ ЗАРАБОТАТЬ ============
@dp.message(F.text == "Заработать звёзды")
async def earn(message: Message):
    me = await bot.get_me()
    ref_link = f"https://t.me/{me.username}?start=ref_{message.from_user.id}"
    share_text = "Заходи в бота, тут раздают звёзды ⭐"
    share_url = (f"https://t.me/share/url?url={quote(ref_link, safe='')}"
                 f"&text={quote(share_text, safe='')}")

    try:
        bonus = float(get_setting("ref_tasks_bonus") or 3)
    except Exception:
        bonus = 3.0
    count = get_confirmed_refs_count(message.from_user.id)

    text = get_setting("earn_text").format(
        bonus=f"{bonus:g}",
        link=ref_link,
        count=count,
    )
    await message.answer(text, reply_markup=earn_kb(share_url), parse_mode="HTML")


# ============ ПРОФИЛЬ ============
def _profile_text(uid: int, first_name: str) -> str:
    u = get_user(uid)
    balance = u[2] if u else 0
    name = first_name or "друг"
    refs = get_confirmed_refs_count(uid)
    pending = get_pending_refs_count(uid)
    place = get_place(uid)
    return (
        f'<tg-emoji emoji-id="5260399854500191689">👤</tg-emoji> <b>ПРОФИЛЬ</b>\n\n'
        f'<tg-emoji emoji-id="5389099588906922686">🧑</tg-emoji> {name}\n'
        f'<tg-emoji emoji-id="6030656587830399914">🆔</tg-emoji> <code>{uid}</code>\n\n'
        f'<tg-emoji emoji-id="6030656914247914196">⭐</tg-emoji> Баланс: <b>{balance:.2f}</b>\n'
        f'<tg-emoji emoji-id="5258513401784573443">👥</tg-emoji> Друзей: <b>{refs}</b>\n'
        f'<tg-emoji emoji-id="5386367538735104399">⌛</tg-emoji> Ожидают: <b>{pending}</b>\n'
        f'<tg-emoji emoji-id="5474419165781597383">🏆</tg-emoji> Место в топе: <b>#{place}</b>\n\n'
        f'<tg-emoji emoji-id="5231102735817918643">👇</tg-emoji> Забирай бонусы и промокоды'
    )


async def _render_profile(call: CallbackQuery):
    if not get_user(call.from_user.id):
        try:
            await call.message.delete()
        except Exception:
            pass
        return
    text = _profile_text(call.from_user.id, call.from_user.first_name)
    try:
        await call.message.edit_text(text, reply_markup=profile_kb(), parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=profile_kb(), parse_mode="HTML")


@dp.message(F.text == "Профиль")
async def profile(message: Message):
    if not get_user(message.from_user.id):
        await message.answer("Напиши /start")
        return
    text = _profile_text(message.from_user.id, message.from_user.first_name)
    await message.answer(text, reply_markup=profile_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "daily_bonus")
async def cb_daily_bonus(call: CallbackQuery):
    balance = get_balance(call.from_user.id)
    try:
        bal_str = f"{float(balance):g}"
    except Exception:
        bal_str = str(balance)

    if not can_take_bonus(call.from_user.id):
        await call.message.edit_text(
            f'<tg-emoji emoji-id="5784964035929707157">🎁</tg-emoji> <b>Ежедневные бонусы</b>\n\n'
            f'<tg-emoji emoji-id="5449449325434266744">❄️</tg-emoji> Бонус уже получен сегодня!\n\n'
            f'<tg-emoji emoji-id="5920108570627544286">⭐️</tg-emoji> Твой баланс: {bal_str} '
            f'<tg-emoji emoji-id="5895708410447401643">🌟</tg-emoji>',
            reply_markup=daily_back_kb(), parse_mode="HTML")
        return
    await call.message.edit_text(
        f'<tg-emoji emoji-id="5784964035929707157">🎁</tg-emoji> <b>Ежедневные бонусы</b>\n\n'
        f'<tg-emoji emoji-id="5449449325434266744">❄️</tg-emoji> Собирай ежедневный бонус каждый день!\n\n'
        f'<tg-emoji emoji-id="5920108570627544286">⭐️</tg-emoji> Твой баланс: {bal_str} '
        f'<tg-emoji emoji-id="5895708410447401643">🌟</tg-emoji>',
        reply_markup=daily_bonus_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "daily_claim")
async def daily_claim(call: CallbackQuery):
    if not can_take_bonus(call.from_user.id):
        await call.answer("⏳ Уже забирал сегодня!", show_alert=True)
        return
    try:
        amount = float(get_setting("daily_bonus") or 1)
    except Exception:
        amount = 1.0
    add_balance(call.from_user.id, amount)
    set_bonus_taken(call.from_user.id)
    balance = get_balance(call.from_user.id)

    await call.answer()
    try:
        await call.message.edit_text(
            f'<tg-emoji emoji-id="5784964035929707157">🎁</tg-emoji> <b>Ежедневный бонус получен!</b>\n\n'
            f'<tg-emoji emoji-id="6025976946083500432">💰</tg-emoji> +{amount:g}'
            f'<tg-emoji emoji-id="5895708410447401643">🌟</tg-emoji>\n'
            f'<tg-emoji emoji-id="5920281855378068765">⭐️</tg-emoji> Баланс: {float(balance):g} '
            f'<tg-emoji emoji-id="5897501460509234625">⭐️</tg-emoji>',
            reply_markup=daily_back_kb(), parse_mode="HTML")
    except Exception:
        pass


@dp.callback_query(F.data == "daily_back")
async def daily_back(call: CallbackQuery):
    await _render_profile(call)


@dp.callback_query(F.data == "daily_cancel")
async def daily_cancel(call: CallbackQuery):
    await _render_profile(call)


# ============ ПРОМОКОД ============
@dp.callback_query(F.data == "enter_promo")
async def cb_enter_promo(call: CallbackQuery, state: FSMContext):
    text = (
        f'<tg-emoji emoji-id="5197468864102823838">🎟</tg-emoji> <b>Промокоды</b>\n\n'
        f'Введите промокод для активации:'
    )
    try:
        await call.message.edit_text(text, reply_markup=promo_cancel_kb(), parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=promo_cancel_kb(), parse_mode="HTML")
    await state.set_state(UserPromo.waiting_code)


@dp.callback_query(F.data == "promo_cancel")
async def promo_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await _render_profile(call)


@dp.message(UserPromo.waiting_code)
async def user_promo_check(message: Message, state: FSMContext):
    code = message.text.strip()
    ok, msg, amount = activate_promo(code, message.from_user.id)
    await state.clear()
    if ok:
        balance = get_balance(message.from_user.id)
        await message.answer(
            f"✅ <b>Промокод активирован!</b>\n\n"
            f"💰 +{float(amount):g} ⭐\n⭐️ Баланс: <b>{float(balance):g}</b>",
            parse_mode="HTML")
    else:
        await message.answer(
            f'<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> '
            f'<b>Промокод не найден</b>\n\n'
            f'Проверьте правильность написания и попробуйте снова',
            parse_mode="HTML")


# ============ ЗАДАНИЯ ============
@dp.message(F.text == "Задания")
async def tasks_menu(message: Message):
    if not tasks_enabled():
        await message.answer("❌ Задания временно недоступны.")
        return
    await _show_next_task_or_done(message, message.from_user.id)


@dp.callback_query(F.data == "tasks_refresh")
async def tasks_refresh(call: CallbackQuery):
    await call.answer()
    try:
        await call.message.delete()
    except Exception:
        pass
    await _show_next_task_or_done(call.message, call.from_user.id)


@dp.callback_query(F.data == "task_skip")
async def task_skip(call: CallbackQuery):
    await call.answer()
    try:
        await call.message.delete()
    except Exception:
        pass
    # сначала попробуем bh с skip=True
    data = await bh_get_task(call.from_user.id, skip=True)
    if data and not data.get("fake"):
        tasks = data.get("tasks", [])
        if tasks:
            await _send_task(call.message, tasks[0], source="bh")
            return
    # иначе — обычная логика (custom или done)
    custom = get_next_custom_task(call.from_user.id)
    if custom:
        tid, title, link, reward_db, ctype, ctarget = custom
        await _send_task(call.message, link, source=f"ct:{tid}")
        return
    try:
        bonus = float(get_setting("ref_tasks_bonus") or 3)
    except Exception:
        bonus = 3.0
    text = get_setting("task_done_text").format(bonus=f"{bonus:g}")
    await call.message.answer(text, reply_markup=task_done_kb(), parse_mode="HTML")


@dp.callback_query(F.data.startswith("tc:"))
async def task_check(call: CallbackQuery):
    user_id = call.from_user.id
    await call.answer()
    source = call.data.split(":", 1)[1]

    try:
        msg = await call.message.answer("⏳ Проверяю подписку, подожди...")
    except Exception:
        msg = None

    # --- свои задания ---
    if source.startswith("ct:"):
        try:
            tid = int(source.split(":")[1])
        except Exception:
            tid = 0
        t = get_custom_task(tid)
        if not t:
            if msg:
                try:
                    await msg.edit_text("❌ Задание не найдено")
                except Exception:
                    pass
            return
        _, title, link, reward_db, active, check_type, check_target = t
        ok = await check_custom_task(user_id, check_type, check_target)
        if ok is False:
            if msg:
                try:
                    await msg.edit_text("❌ Ты ещё не подписался. Попробуй ещё раз.")
                except Exception:
                    pass
            return

        # защита от повторного выполнения
        if get_custom_task(tid) is None:
            pass
        mark_custom_task_done(user_id, tid)

        try:
            reward = float(get_setting("task_reward") or 0.45)
        except Exception:
            reward = 0.45
        add_balance(user_id, reward)
        balance = get_balance(user_id)

        # прогресс реферала
        await _handle_task_done(user_id)

        # удаляем сообщение-задание и показываем результат
        if msg:
            try:
                await msg.delete()
            except Exception:
                pass
        try:
            await call.message.delete()
        except Exception:
            pass

        text = get_setting("task_reward_text").format(
            reward=f"{reward:g}",
            balance=f"{float(balance):g}",
        )
        await call.message.answer(text, parse_mode="HTML")
        await _show_next_task_or_done(call.message, user_id)
        return

    # --- Botohub задание ---
    data = None
    for i in range(3):
        data = await bh_get_task(user_id, skip=False)
        if data and data.get("prev_success"):
            break
        if i < 2:
            await asyncio.sleep(7)

    if not data:
        if msg:
            try:
                await msg.edit_text("❌ Ошибка сервера. Попробуй позже.")
            except Exception:
                pass
        return

    if data.get("fake"):
        if msg:
            try:
                await msg.edit_text("🚫 Задания недоступны для этого аккаунта")
            except Exception:
                pass
        return

    if not data.get("prev_success"):
        if msg:
            try:
                await msg.edit_text("❌ Ты ещё не подписался. Попробуй ещё раз.")
            except Exception:
                pass
        return

    # успех
    try:
        reward = float(get_setting("task_reward") or 0.45)
    except Exception:
        reward = 0.45
    add_balance(user_id, reward)
    balance = get_balance(user_id)

    # прогресс реферала
    await _handle_task_done(user_id)

    if msg:
        try:
            await msg.delete()
        except Exception:
            pass
    try:
        await call.message.delete()
    except Exception:
        pass

    text = get_setting("task_reward_text").format(
        reward=f"{reward:g}",
        balance=f"{float(balance):g}",
    )
    await call.message.answer(text, parse_mode="HTML")
    await _show_next_task_or_done(call.message, user_id)


# ============ ВЫВОД ============
@dp.message(F.text == "Вывести звёзды")
async def withdraw(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        '<tg-emoji emoji-id="5427236501903655352">❣️</tg-emoji> <b>Выбери подарок</b>',
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
        await call.answer(f"❌ Не хватает {need:.2f} ⭐\nНужно: {price} ⭐\nУ тебя: {balance:.2f} ⭐",
                          show_alert=True)
        return

    if bh_enabled() and BOTOHUB_TOKEN:
        try:
            count = int(get_setting("botohub_withdraw_count"))
        except Exception:
            count = 6
        data = await bh_get_tasks(call.from_user.id, count)
        tasks = data.get("tasks", [])
        customs = list_custom_ops("withdraw")
        not_done = [t for t in tasks if not t.get("completed")]
        if not_done or customs:
            await state.update_data(gift_key=key)
            try:
                await call.message.delete()
            except Exception:
                pass
            await show_op_screen(call.from_user.id, call.from_user.id, "withdraw", "bh_wd_check")
            return

    await create_order(call, key)


@dp.callback_query(F.data == "bh_wd_check")
async def bh_wd_check(call: CallbackQuery, state: FSMContext):
    await call.answer()
    try:
        count = int(get_setting("botohub_withdraw_count"))
    except Exception:
        count = 6

    try:
        msg = await call.message.answer("⏳ Проверяю подписку, подожди...")
    except Exception:
        msg = None

    passed = False
    for i in range(3):
        data = await bh_get_tasks(call.from_user.id, count)
        tasks = data.get("tasks", [])
        not_done = [t for t in tasks if not t.get("completed")]
        if data.get("completed") or data.get("skip") or not not_done:
            passed = True
            break
        if i < 2:
            await asyncio.sleep(7)

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
    gift_emoji_id = GIFTS_EMOJI.get(key, "")
    balance = get_balance(call.from_user.id)
    if balance < price:
        await call.answer(f"❌ Нужно {price} ⭐", show_alert=True)
        return
    wid = create_withdrawal(call.from_user.id, price, key)
    uname = f"@{call.from_user.username}" if call.from_user.username else "без username"

    text = (
        f'<tg-emoji emoji-id="6026257381678124710">✅</tg-emoji> <b>Заявка #{wid} создана!</b>\n\n'
        f'<tg-emoji emoji-id="5449800250032143374">🎁</tg-emoji> Подарок: '
        f'<tg-emoji emoji-id="{gift_emoji_id}">🎁</tg-emoji> {name}\n'
        f'<tg-emoji emoji-id="5224257782013769471">💰</tg-emoji> Сумма: {price} '
        f'<tg-emoji emoji-id="5386367538735104399">⭐</tg-emoji>\n'
        f'<tg-emoji emoji-id="5920433463428650761">⌛</tg-emoji> Ожидай — админ отправит подарок вручную.'
    )

    try:
        await bot.send_message(call.from_user.id, text, parse_mode="HTML")
    except Exception as e:
        print("Ошибка отправки юзеру:", e)
        try:
            await bot.send_message(
                call.from_user.id,
                f"✅ Заявка #{wid} создана!\n\n"
                f"🎁 Подарок: {name}\n"
                f"💰 Сумма: {price} ⭐\n"
                f"⌛ Ожидай — админ отправит подарок вручную."
            )
        except Exception as e2:
            print("Ошибка отправки юзеру (fallback):", e2)

    try:
        await bot.send_message(ADMIN_ID,
            f"💸 <b>Новая заявка #{wid}</b>\n\n👤 {uname}\n"
            f"🆔 <code>{call.from_user.id}</code>\n🎁 {name}\n💰 {price} ⭐",
            reply_markup=admin_wd_kb(wid), parse_mode="HTML")
    except Exception as e:
        print("Ошибка отправки админу:", e)
        # ================== АДМИНКА ==================
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
        reply_markup=admin_kb(), parse_mode="HTML")


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
            reply_markup=admin_kb(), parse_mode="HTML")
    except Exception:
        await call.message.answer("🛠 Админ-панель", reply_markup=admin_kb())


# ---------- BOTOHUB ОП ----------
def bh_menu_text():
    enabled = bh_enabled()
    return (
        f"🎯 <b>Botohub ОП</b>\n\n"
        f"Статус: {'🟢 включен' if enabled else '🔴 выключен'}\n"
        f"🔑 Токен: <code>{BOTOHUB_TOKEN[:20]}...</code>\n\n"
        f"📥 ОП на входе: <b>{get_setting('botohub_entry_count')}</b>\n"
        f"💸 ОП на выводе: <b>{get_setting('botohub_withdraw_count')}</b>\n"
        f"🔤 Текст кнопок: <code>{get_setting('botohub_btn_text')}</code>\n\n"
        f"📝 Текст:\n<i>{get_setting('botohub_text')[:80]}...</i>"
    )


@dp.callback_query(F.data == "bh_menu")
async def bh_menu(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text(bh_menu_text(), reply_markup=bh_kb(bh_enabled()), parse_mode="HTML")


@dp.callback_query(F.data == "bh_toggle")
async def bh_toggle(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    current = get_setting("botohub_enabled") == "1"
    set_setting("botohub_enabled", "0" if current else "1")
    await call.answer("✅ Изменено")
    await call.message.edit_text(bh_menu_text(), reply_markup=bh_kb(not current), parse_mode="HTML")


@dp.callback_query(F.data == "bh_edit_text")
async def bh_edit_text(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("✏️ Пришли новый текст для ОП (можно HTML + tg-emoji):")
    await state.set_state(BHEdit.waiting_text)


@dp.message(BHEdit.waiting_text)
async def bh_save_text(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    set_setting("botohub_text", message.text)
    await state.clear()
    await message.answer("✅ Текст сохранён", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "bh_edit_btn")
async def bh_edit_btn(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("🔤 Пришли текст для кнопок (например, «Подписаться»):")
    await state.set_state(BHEdit.waiting_btn)


@dp.message(BHEdit.waiting_btn)
async def bh_save_btn(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    set_setting("botohub_btn_text", message.text.strip())
    await state.clear()
    await message.answer("✅ Сохранено", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "bh_edit_entry")
async def bh_edit_entry(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("📥 Сколько спонсоров на входе?")
    await state.set_state(BHEdit.waiting_entry)


@dp.message(BHEdit.waiting_entry)
async def bh_save_entry(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        val = int(message.text.strip())
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    set_setting("botohub_entry_count", val)
    await state.clear()
    await message.answer(f"✅ Сохранено: {val}", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "bh_edit_wd")
async def bh_edit_wd(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("💸 Сколько спонсоров на выводе?")
    await state.set_state(BHEdit.waiting_wd)


@dp.message(BHEdit.waiting_wd)
async def bh_save_wd(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        val = int(message.text.strip())
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    set_setting("botohub_withdraw_count", val)
    await state.clear()
    await message.answer(f"✅ Сохранено: {val}", reply_markup=back_admin_kb())


# ---------- ЗАДАНИЯ ----------
def tasks_menu_text():
    enabled = tasks_enabled()
    return (
        f"🎯 <b>Задания (Botohub + свои)</b>\n\n"
        f"Статус: {'🟢 включены' if enabled else '🔴 выключены'}\n\n"
        f"💰 Награда за задание: <b>{get_setting('task_reward')}</b> ⭐\n"
        f"🔤 Кнопки: "
        f"<code>{get_setting('task_btn_go')} / {get_setting('task_btn_check')} / {get_setting('task_btn_skip')}</code>"
    )


@dp.callback_query(F.data == "tasks_menu")
async def tasks_admin_menu(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text(tasks_menu_text(), reply_markup=tasks_kb(tasks_enabled()), parse_mode="HTML")


@dp.callback_query(F.data == "tasks_toggle")
async def tasks_toggle(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    current = get_setting("tasks_enabled") == "1"
    set_setting("tasks_enabled", "0" if current else "1")
    await call.answer("✅ Изменено")
    await call.message.edit_text(tasks_menu_text(), reply_markup=tasks_kb(not current), parse_mode="HTML")


@dp.callback_query(F.data == "tasks_edit_reward")
async def tasks_edit_reward(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("💰 Сколько звёзд давать за задание? (можно дробное, например 0.45)")
    await state.set_state(TasksEdit.waiting_reward)


@dp.message(TasksEdit.waiting_reward)
async def tasks_save_reward(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        val = float(message.text.strip().replace(",", "."))
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    set_setting("task_reward", f"{val:g}")
    await state.clear()
    await message.answer(f"✅ Награда: {val:g} ⭐", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "task_edit_text")
async def task_edit_text(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer(
        "✏️ Пришли новый текст задания.\n\n"
        "Плейсхолдер <code>{reward}</code> — подставится сумма награды.\n"
        "Можно HTML и tg-emoji.",
        parse_mode="HTML")
    await state.set_state(TasksEdit.waiting_text)


@dp.message(TasksEdit.waiting_text)
async def task_save_text(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    set_setting("task_text", message.text)
    await state.clear()
    await message.answer("✅ Текст сохранён", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "task_edit_btns")
async def task_edit_btns(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer(
        "🔤 Пришли через <code>;</code> три текста кнопок:\n"
        "<code>Перейти;Проверить;Пропустить</code>",
        parse_mode="HTML")
    await state.set_state(TasksEdit.waiting_btn_go)


@dp.message(TasksEdit.waiting_btn_go)
async def task_save_btns(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    parts = [p.strip() for p in message.text.split(";")]
    if len(parts) != 3 or not all(parts):
        await message.answer("⚠️ Нужно ровно 3 значения через <code>;</code>", parse_mode="HTML")
        return
    set_setting("task_btn_go", parts[0])
    set_setting("task_btn_check", parts[1])
    set_setting("task_btn_skip", parts[2])
    await state.clear()
    await message.answer(f"✅ Сохранено: {parts}", reply_markup=back_admin_kb())


# ---------- СВОИ ЗАДАНИЯ ----------
@dp.callback_query(F.data == "ctasks_menu")
async def ctasks_menu(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text(
        "📌 <b>Свои задания</b>\n\n"
        "Добавляй задания, которые будут показываться юзерам после Botohub-заданий.",
        reply_markup=ctasks_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "ctask_add")
async def ctask_add(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer(
        "📌 <b>Выбери тип задания:</b>\n\n"
        "📢 <b>Открытый канал</b> — есть @username\n"
        "🔒 <b>Закрытый канал</b> — invite-ссылка + chat_id\n"
        "🤖 <b>Бот по рефке</b> — без проверки",
        reply_markup=ctask_type_kb(), parse_mode="HTML")
    await state.set_state(CTaskAdd.waiting_type)


@dp.callback_query(F.data.startswith("ctask_type:"), CTaskAdd.waiting_type)
async def ctask_type_chosen(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    ct = call.data.split(":")[1]
    if ct not in ("open", "closed", "bot"):
        await call.answer("Неизвестный тип")
        return
    await state.update_data(ct_type=ct)
    names = {"open": "📢 Открытый канал", "closed": "🔒 Закрытый канал", "bot": "🤖 Бот по рефке"}
    try:
        await call.message.edit_text(f"{names[ct]}\n\n📝 Название задания (для себя):")
    except Exception:
        await call.message.answer(f"{names[ct]}\n\n📝 Название задания (для себя):")
    await state.set_state(CTaskAdd.waiting_title)
    await call.answer()


@dp.message(CTaskAdd.waiting_title)
async def ctask_title(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.update_data(ct_title=message.text.strip())
    data = await state.get_data()
    ct = data.get("ct_type")
    if ct == "open":
        await message.answer("🔗 Пришли @username канала или ссылку <code>t.me/username</code>",
                             parse_mode="HTML")
    elif ct == "closed":
        await message.answer("🔗 Пришли invite-ссылку канала (<code>t.me/+xxxxx</code>)",
                             parse_mode="HTML")
    else:
        await message.answer("🔗 Пришли ссылку на бота (<code>t.me/xxxbot?start=yyy</code>)",
                             parse_mode="HTML")
    await state.set_state(CTaskAdd.waiting_link)


@dp.message(CTaskAdd.waiting_link)
async def ctask_link(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    raw = message.text.strip()
    data = await state.get_data()
    ct = data.get("ct_type")

    if ct == "open":
        target = raw
        if "t.me/" in target:
            target = target.split("t.me/")[-1].split("?")[0].strip("/")
        target = target.lstrip("@")
        if not target:
            await message.answer("⚠️ Не могу разобрать username.")
            return
        check_target = "@" + target
        link = f"https://t.me/{target}"
        try:
            await bot.get_chat(check_target)
        except Exception as e:
            await message.answer(
                f"⚠️ Не могу получить инфо о канале <code>{check_target}</code>:\n"
                f"<code>{e}</code>\n\n"
                f"Добавлю всё равно — проверь, что бот добавлен админом в канал.",
                parse_mode="HTML")
        await state.update_data(ct_link=link, ct_check_type="open", ct_check_target=check_target)
        await _ctask_finish(message, state)
        return

    if ct == "closed":
        if not raw.startswith("http"):
            await message.answer("⚠️ Ссылка должна начинаться с http.")
            return
        await state.update_data(ct_link=raw, ct_check_type="closed")
        await message.answer("🆔 Пришли chat_id канала (например, <code>-1001234567890</code>)",
                             parse_mode="HTML")
        await state.set_state(CTaskAdd.waiting_chat_id)
        return

    # bot
    if not raw.startswith("http"):
        await message.answer("⚠️ Ссылка должна начинаться с http.")
        return
    await state.update_data(ct_link=raw, ct_check_type="bot", ct_check_target="")
    await _ctask_finish(message, state)


@dp.message(CTaskAdd.waiting_chat_id)
async def ctask_chat_id(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    raw = message.text.strip()
    if not raw.lstrip("-").isdigit():
        await message.answer("⚠️ chat_id должен быть числом (например, -1001234567890).")
        return
    try:
        await bot.get_chat(int(raw))
    except Exception as e:
        await message.answer(
            f"⚠️ Не могу получить инфо о канале <code>{raw}</code>:\n"
            f"<code>{e}</code>\n\n"
            f"Добавлю всё равно — проверь, что бот добавлен админом в канал.",
            parse_mode="HTML")
    await state.update_data(ct_check_target=raw)
    await _ctask_finish(message, state)


async def _ctask_finish(message: Message, state: FSMContext):
    data = await state.get_data()
    add_custom_task(
        data["ct_title"],
        data["ct_link"],
        data.get("ct_check_type", "bot"),
        data.get("ct_check_target", ""),
    )
    await state.clear()
    await message.answer("✅ Задание добавлено", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "ctask_list")
async def ctask_list(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    rows = list_custom_tasks()
    if not rows:
        await call.answer("Пусто", show_alert=True)
        return
    type_names = {"open": "📢 Открытый", "closed": "🔒 Закрытый", "bot": "🤖 Бот"}
    text = "📜 <b>Свои задания</b>\n\n"
    for tid, title, link, reward, active, ctype, ctarget in rows:
        tname = type_names.get(ctype or "bot", "🤖 Бот")
        text += f"#{tid} — {tname} — {title}\n"
        text += f"   {link}\n"
        if ctarget:
            text += f"   🔎 <code>{ctarget}</code>\n"
        text += "\n"
    if len(text) > 4000:
        text = text[:4000] + "\n...обрезано"
    await call.message.answer(text, parse_mode="HTML")


@dp.callback_query(F.data == "ctask_delete")
async def ctask_delete(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("🗑 Пришли ID задания для удаления:")
    await state.set_state(CTaskDel.waiting_id)


@dp.message(CTaskDel.waiting_id)
async def ctask_delete_id(message: Message, state: FSMContext):
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


# ---------- СВОИ ОП ----------
@dp.callback_query(F.data == "cop_menu")
async def cop_menu(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text(
        "📌 <b>Свои ОП</b>\n\nВыбери, куда добавить:",
        reply_markup=cop_type_kb(), parse_mode="HTML")


@dp.callback_query(F.data.startswith("cop_menu:"))
async def cop_menu_type(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    op_type = call.data.split(":")[1]
    title = "входе" if op_type == "entry" else "выводе"
    await call.message.edit_text(
        f"📌 <b>Свои ОП (на {title})</b>",
        reply_markup=cop_kb(op_type), parse_mode="HTML")


@dp.callback_query(F.data.startswith("cop_add:"))
async def cop_add(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    op_type = call.data.split(":")[1]
    await state.update_data(op_type=op_type)
    await call.message.answer("📝 Название (для себя):")
    await state.set_state(CopAdd.waiting_title)


@dp.message(CopAdd.waiting_title)
async def cop_add_title(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.update_data(cop_title=message.text.strip())
    await message.answer("🔗 Ссылка (https://t.me/...):")
    await state.set_state(CopAdd.waiting_link)


@dp.message(CopAdd.waiting_link)
async def cop_add_link(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    link = message.text.strip()
    if not link.startswith("http"):
        await message.answer("⚠️ Ссылка должна начинаться с http.")
        return
    data = await state.get_data()
    add_custom_op(data["cop_title"], link, data.get("op_type", "entry"))
    await state.clear()
    await message.answer("✅ Добавлено", reply_markup=back_admin_kb())


@dp.callback_query(F.data.startswith("cop_list:"))
async def cop_list(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    op_type = call.data.split(":")[1]
    rows = list_custom_ops(op_type)
    if not rows:
        await call.answer("Пусто", show_alert=True)
        return
    text = "📜 <b>Свои ОП</b>\n\n"
    for cid, title, link in rows:
        text += f"#{cid} — {title}\n{link}\n\n"
    if len(text) > 4000:
        text = text[:4000] + "\n...обрезано"
    await call.message.answer(text, parse_mode="HTML")


@dp.callback_query(F.data.startswith("cop_del:"))
async def cop_del(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("🗑 Пришли ID для удаления:")
    await state.set_state(CopDel.waiting_id)


@dp.message(CopDel.waiting_id)
async def cop_del_id(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        cid = int(message.text.strip())
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    delete_custom_op(cid)
    await state.clear()
    await message.answer("🗑 Удалено", reply_markup=back_admin_kb())


# ---------- ОП НА СТАРТЕ ----------
def op_menu_text():
    enabled = op_enabled()
    link = get_setting("op_link") or "—"
    target = get_setting("op_check_target") or "— (без проверки, на доверии)"
    return (
        f"🔒 <b>ОП на старте</b>\n\n"
        f"Статус: {'🟢 включён' if enabled else '🔴 выключен'}\n\n"
        f"🔗 Ссылка: {link}\n"
        f"🔎 Проверка: <code>{target}</code>\n\n"
        f"📝 Текст:\n<i>{get_setting('op_text')[:80]}...</i>"
    )


@dp.callback_query(F.data == "op_menu")
async def op_menu(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text(op_menu_text(), reply_markup=op_menu_kb(op_enabled()), parse_mode="HTML")


@dp.callback_query(F.data == "op_toggle")
async def op_toggle(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    current = op_enabled()
    set_setting("op_enabled", "0" if current else "1")
    await call.answer("✅ Изменено")
    await call.message.edit_text(op_menu_text(), reply_markup=op_menu_kb(not current), parse_mode="HTML")


@dp.callback_query(F.data == "op_edit_text")
async def op_edit_text(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("✏️ Пришли новый текст для ОП на старте:")
    await state.set_state(OpEdit.waiting_text)


@dp.message(OpEdit.waiting_text)
async def op_save_text(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    set_setting("op_text", message.text)
    await state.clear()
    await message.answer("✅ Сохранено", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "op_edit_link")
async def op_edit_link(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("🔗 Пришли ссылку на канал (https://t.me/...):")
    await state.set_state(OpEdit.waiting_link)


@dp.message(OpEdit.waiting_link)
async def op_save_link(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    link = message.text.strip()
    if not link.startswith("http"):
        await message.answer("⚠️ Ссылка должна начинаться с http.")
        return
    set_setting("op_link", link)
    await state.clear()
    await message.answer("✅ Сохранено", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "op_edit_target")
async def op_edit_target(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer(
        "🔎 Пришли @username канала или chat_id (<code>-100xxx</code>) для проверки подписки.\n\n"
        "Или напиши <code>-</code>, чтобы отключить проверку (на доверии).",
        parse_mode="HTML")
    await state.set_state(OpEdit.waiting_target)


@dp.message(OpEdit.waiting_target)
async def op_save_target(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    val = message.text.strip()
    if val == "-":
        set_setting("op_check_target", "")
        await state.clear()
        await message.answer("✅ Проверка выключена (на доверии)", reply_markup=back_admin_kb())
        return
    set_setting("op_check_target", val)
    # предупредим, если не можем проверить
    try:
        t = int(val) if val.lstrip("-").isdigit() else val
        await bot.get_chat(t)
    except Exception as e:
        await message.answer(
            f"⚠️ Не могу получить инфо о канале:\n<code>{e}</code>\n\n"
            f"Сохранил всё равно. Проверь, что бот админ в этом канале.",
            parse_mode="HTML")
    await state.clear()
    await message.answer("✅ Сохранено", reply_markup=back_admin_kb())


# ---------- РЕФЕРАЛКА (5 заданий) ----------
def ref_menu_text():
    enabled = get_setting("ref_tasks_enabled") == "1"
    return (
        f"💖 <b>Рефералка (5 заданий)</b>\n\n"
        f"Статус: {'🟢 включена' if enabled else '🔴 выключена'}\n\n"
        f"🎯 Заданий нужно: <b>{get_setting('ref_tasks_required')}</b>\n"
        f"💰 Награда рефереру: <b>{get_setting('ref_tasks_bonus')}</b> ⭐\n"
        f"📅 Дней на выполнение: <b>{get_setting('ref_deadline_days')}</b>"
    )


@dp.callback_query(F.data == "ref_menu")
async def ref_menu(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    enabled = get_setting("ref_tasks_enabled") == "1"
    await call.message.edit_text(ref_menu_text(), reply_markup=ref_menu_kb(enabled), parse_mode="HTML")


@dp.callback_query(F.data == "ref_toggle")
async def ref_toggle(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    current = get_setting("ref_tasks_enabled") == "1"
    set_setting("ref_tasks_enabled", "0" if current else "1")
    await call.answer("✅ Изменено")
    await call.message.edit_text(ref_menu_text(), reply_markup=ref_menu_kb(not current), parse_mode="HTML")


@dp.callback_query(F.data == "ref_edit_bonus")
async def ref_edit_bonus(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("💰 Сколько звёзд получает реферер за 5/5? (можно дробное)")
    await state.set_state(RefEdit.waiting_bonus)


@dp.message(RefEdit.waiting_bonus)
async def ref_save_bonus(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        val = float(message.text.strip().replace(",", "."))
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    set_setting("ref_tasks_bonus", f"{val:g}")
    await state.clear()
    await message.answer(f"✅ Награда: {val:g} ⭐", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "ref_edit_required")
async def ref_edit_required(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("🎯 Сколько заданий должен выполнить реферал?")
    await state.set_state(RefEdit.waiting_required)


@dp.message(RefEdit.waiting_required)
async def ref_save_required(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        val = int(message.text.strip())
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    set_setting("ref_tasks_required", val)
    await state.clear()
    await message.answer(f"✅ Нужно заданий: {val}", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "ref_edit_days")
async def ref_edit_days(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("📅 Сколько дней даётся рефералу на выполнение?")
    await state.set_state(RefEdit.waiting_days)


@dp.message(RefEdit.waiting_days)
async def ref_save_days(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        val = int(message.text.strip())
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    set_setting("ref_deadline_days", val)
    await state.clear()
    await message.answer(f"✅ Дней: {val}", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "ref_edit_earn_text")
async def ref_edit_earn_text(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer(
        "✏️ Текст экрана «Заработать звёзды».\n\n"
        "Плейсхолдеры: <code>{bonus}</code>, <code>{link}</code>, <code>{count}</code>",
        parse_mode="HTML")
    await state.set_state(RefEdit.waiting_earn_text)


@dp.message(RefEdit.waiting_earn_text)
async def ref_save_earn_text(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    set_setting("earn_text", message.text)
    await state.clear()
    await message.answer("✅ Сохранено", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "ref_edit_notify_start")
async def ref_edit_notify_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer(
        "✏️ Текст уведомления рефереру «старт».\n\n"
        "Плейсхолдер: <code>{username}</code>",
        parse_mode="HTML")
    await state.set_state(RefEdit.waiting_notify_start)


@dp.message(RefEdit.waiting_notify_start)
async def ref_save_notify_start(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    set_setting("ref_notify_start", message.text)
    await state.clear()
    await message.answer("✅ Сохранено", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "ref_edit_notify_5min")
async def ref_edit_notify_5min(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer(
        "✏️ Текст уведомления «через 5 минут».\n\n"
        "Плейсхолдер: <code>{username}</code>",
        parse_mode="HTML")
    await state.set_state(RefEdit.waiting_notify_5min)


@dp.message(RefEdit.waiting_notify_5min)
async def ref_save_notify_5min(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    set_setting("ref_notify_5min", message.text)
    await state.clear()
    await message.answer("✅ Сохранено", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "ref_edit_notify_10min")
async def ref_edit_notify_10min(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer(
        "✏️ Текст уведомления «через 10 минут».\n\n"
        "Плейсхолдеры: <code>{username}</code>, <code>{done}</code>, <code>{need}</code>",
        parse_mode="HTML")
    await state.set_state(RefEdit.waiting_notify_10min)


@dp.message(RefEdit.waiting_notify_10min)
async def ref_save_notify_10min(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    set_setting("ref_notify_10min", message.text)
    await state.clear()
    await message.answer("✅ Сохранено", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "ref_edit_notify_done")
async def ref_edit_notify_done(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer(
        "✏️ Текст уведомления «5/5».\n\n"
        "Плейсхолдеры: <code>{username}</code>, <code>{bonus}</code>",
        parse_mode="HTML")
    await state.set_state(RefEdit.waiting_notify_done)


@dp.message(RefEdit.waiting_notify_done)
async def ref_save_notify_done(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    set_setting("ref_notify_done", message.text)
    await state.clear()
    await message.answer("✅ Сохранено", reply_markup=back_admin_kb())


# ---------- ЗАЯВКИ ----------
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
            f"🎁 {name}\n💰 {amount:g} ⭐",
            reply_markup=admin_wd_kb(wid), parse_mode="HTML")


@dp.callback_query(F.data.startswith("wd_ok:"))
async def wd_ok(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    wid = int(call.data.split(":")[1])
    row = get_withdrawal(wid)
    if not row:
        await call.answer("Не найдена")
        return
    _, user_id, amount, gift_key, status = row
    if status != "pending":
        await call.answer("Уже обработана")
        return
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
        await call.answer("Не найдена")
        return
    _, user_id, amount, gift_key, status = row
    if status != "pending":
        await call.answer("Уже обработана")
        return
    set_withdrawal_status(wid, "rejected")
    add_balance(user_id, amount)
    try:
        await bot.send_message(user_id, f"❌ Заявка #{wid} отклонена.\n{amount:g} ⭐ возвращены.")
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
        text += f"{icon} #{wid} — {name} — {amount:g}⭐ — ID<code>{uid}</code> — {date}\n"
    if len(text) > 4000:
        text = text[:4000] + "\n...обрезано"
    await call.message.edit_text(text, reply_markup=back_admin_kb(), parse_mode="HTML")


# ---------- ПРИВАТКА ----------
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


# ---------- РАССЫЛКА ----------
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
        await call.answer("Текст потерян")
        return
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
    await call.message.edit_text(
        f"✅ Готово!\n\nОтправлено: {sent}/{len(users)}",
        reply_markup=back_admin_kb())


# ---------- НАЧИСЛИТЬ ----------
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
        await message.answer("⚠️ ID — число.")
        return
    uid = int(text)
    u = get_user(uid)
    if not u:
        await message.answer("⚠️ Не найден.")
        return
    await state.update_data(give_uid=uid)
    await message.answer(f"👤 @{u[1] or '—'} — баланс: {float(u[2]):g} ⭐\n\nПришли сумму (+ или −):")
    await state.set_state(GiveFlow.waiting_amount)


@dp.message(GiveFlow.waiting_amount)
async def give_amount(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        amount = float(message.text.strip().replace(",", "."))
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    data = await state.get_data()
    uid = data.get("give_uid")
    if not uid:
        await state.clear()
        return
    add_balance(uid, amount)
    new_balance = get_balance(uid)
    await state.clear()
    await message.answer(
        f"✅ {amount:+g} ⭐\n🆔 <code>{uid}</code>\n💰 Баланс: <b>{float(new_balance):g}</b> ⭐",
        reply_markup=back_admin_kb(), parse_mode="HTML")


# ---------- ЮЗЕР ----------
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
        await message.answer("⚠️ ID — число.")
        return
    uid = int(text)
    u = get_user(uid)
    if not u:
        await message.answer("⚠️ Не найден.")
        return
    balance = u[2]
    refs = get_confirmed_refs_count(uid)
    pending = get_pending_refs_count(uid)
    reg = (u[5] or "")[:16].replace("T", " ")
    rp = get_ref_progress(uid)
    rp_line = ""
    if rp:
        _, ref_id, done, _, _, _, _, paid, st = rp
        rp_line = f"\n💖 Прогресс рефа: <b>{done}</b> / 5 — статус <b>{st}</b>"
    await state.clear()
    await message.answer(
        f"👤 <b>Юзер</b>\n\n🧑 @{u[1] or '—'}\n🆔 <code>{uid}</code>\n"
        f"⭐ Баланс: <b>{float(balance):g}</b>\n👥 Друзей: <b>{refs}</b>\n"
        f"⏳ Ожидают: <b>{pending}</b>\n📅 Регистрация: {reg}{rp_line}",
        reply_markup=user_view_kb(uid), parse_mode="HTML")


@dp.callback_query(F.data.startswith("user_refs:"))
async def user_refs(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    uid = int(call.data.split(":")[1])
    rows = get_user_referrals(uid, 100)
    if not rows:
        await call.answer("Пусто")
        return
    text = f"👥 <b>Рефералы <code>{uid}</code></b>\n\n"
    icons = {"done": "✅", "active": "⏳", "expired": "❌", "confirmed": "✅", "pending": "⏳"}
    for r_uid, r_name, r_date, r_status in rows:
        icon = icons.get(r_status, "•")
        date = (r_date or "")[:10]
        name = f"@{r_name}" if r_name else f"ID {r_uid}"
        text += f"{icon} {name} — <code>{r_uid}</code> — {date}\n"
    if len(text) > 4000:
        text = text[:4000] + "\n...обрезано"
    await call.message.answer(text, parse_mode="HTML")


# ---------- ПРОМОКОДЫ ----------
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
        await message.answer("⚠️ Только буквы/цифры, минимум 3.")
        return
    await state.update_data(code=code)
    await message.answer(f"Код: <b>{code}</b>\n\nСколько звёзд?", parse_mode="HTML")
    await state.set_state(PromoCreate.waiting_amount)


@dp.message(PromoCreate.waiting_amount)
async def promo_amount_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        amount = float(message.text.replace(",", "."))
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    await state.update_data(amount=amount)
    await message.answer(f"Звёзд: <b>{amount:g}</b>\n\nСколько активаций?", parse_mode="HTML")
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
        f"✅ Промокод <code>{data['code']}</code> создан "
        f"({data['amount']:g} ⭐, {uses} активаций)", parse_mode="HTML")


@dp.callback_query(F.data == "promo_list")
async def promo_list_cb(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    rows = list_promos()
    if not rows:
        await call.answer("Пусто")
        return
    text = "📜 <b>Промокоды</b>\n\n"
    for code, amount, mx, used, active in rows:
        status = "🟢" if active and used < mx else "🔴"
        text += f"{status} <code>{code}</code> — {amount:g} ⭐ | {used}/{mx}\n"
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
        await message.answer("⚠️ Нет такого.")
        return
    delete_promo(code)
    await state.clear()
    await message.answer(f"🗑 Удалён <code>{code}</code>", parse_mode="HTML")


# ---------- СТАТИСТИКА ----------
@dp.callback_query(F.data == "stats")
async def stats(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    s = get_stats()
    top_bal = get_top_balance(10)
    top_refs = get_top_refs(10)

    medals = ["🥇", "🥈", "🥉"]
    bal_lines = ""
    for i, (uid, uname, bal) in enumerate(top_bal, 1):
        prefix = medals[i - 1] if i <= 3 else f"{i}."
        name = f"@{uname}" if uname else f"ID{uid}"
        try:
            bal_str = f"{float(bal):g}"
        except Exception:
            bal_str = str(bal)
        bal_lines += f"{prefix} {name} — <b>{bal_str}</b> ⭐\n"

    ref_lines = ""
    for i, (uid, uname, refs) in enumerate(top_refs, 1):
        prefix = medals[i - 1] if i <= 3 else f"{i}."
        name = f"@{uname}" if uname else f"ID{uid}"
        ref_lines += f"{prefix} {name} — <b>{refs}</b> 👥\n"

    text = (
        f"📊 <b>СТАТИСТИКА</b>\n\n"
        f"👥 Всего юзеров: <b>{s['total']}</b>\n"
        f"📅 Новых сегодня: <b>{s['today']}</b>\n"
        f"💰 Общий баланс: <b>{float(s['total_balance']):g}</b> ⭐\n"
        f"💖 Прошли 5/5: <b>{s['total_refs']}</b>\n\n"
        f"📋 <b>Заявки на вывод:</b>\n"
        f"   ⏳ В ожидании: <b>{s['pending']}</b>\n"
        f"   ✅ Выполнено: <b>{s['done']}</b>\n"
        f"   ❌ Отклонено: <b>{s['rejected']}</b>\n"
        f"   💫 Выдано звёзд: <b>{float(s['total_stars']):g}</b>\n\n"
        f"🏆 <b>Топ-10 по балансу:</b>\n{bal_lines or '   —'}\n"
        f"👥 <b>Топ-10 по рефералам:</b>\n{ref_lines or '   —'}"
    )
    if len(text) > 4000:
        text = text[:4000] + "\n...обрезано"
    await call.message.edit_text(text, reply_markup=stats_kb(), parse_mode="HTML")


# ---------- НАСТРОЙКИ ----------
@dp.callback_query(F.data == "settings")
async def settings(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text(
        f"⚙️ <b>НАСТРОЙКИ</b>\n\n"
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
        "daily_bonus": "🎁 Ежедневный бонус (число, можно дробное):",
        "min_withdraw": "💸 Минимум вывода (число):",
        "welcome_text": "✏️ Текст под меню:",
    }
    if key not in prompts:
        return
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
    if key in ("daily_bonus", "min_withdraw"):
        try:
            float(value.replace(",", "."))
        except Exception:
            await message.answer("⚠️ Нужно число.")
            return
    set_setting(key, value)
    await state.clear()
    await message.answer(f"✅ Сохранено: {key}", reply_markup=back_admin_kb())


# ---------- БЭКАП ----------
@dp.callback_query(F.data == "backup_help")
async def backup_help(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text(
        "📦 <b>Бэкап</b>\n\n"
        "📤 <b>Выгрузка:</b> команда <code>/backup</code>.\n\n"
        "📥 <b>Загрузка:</b> просто отправь боту JSON-файл.\n\n"
        "🤖 Авто-бэкап: каждый день в 8:00 и 20:00 (МСК).",
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
        await message.answer_document(file, caption=(
            f"📦 <b>Бэкап</b>\n\n"
            f"👥 Юзеров: <b>{len(data['users'])}</b>\n"
            f"💖 Реф-прогрессов: <b>{len(data['ref_progress'])}</b>\n"
            f"🎟 Промокодов: <b>{len(data['promos'])}</b>\n"
            f"💸 Заявок: <b>{len(data['withdrawals'])}</b>"), parse_mode="HTML")
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
        await message.answer(
            f"✅ <b>Восстановлено</b>\n\n👥 Юзеров: <b>{count}</b>",
            parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


# ================== ФОН: РЕФЕРАЛЬНЫЙ ВОРКЕР ==================
async def ref_worker():
    """Каждые 60 секунд:
       - через 5 мин — уведомление рефереру (если не подписался на ОП/не начал)
       - через 10 мин — уведомление с прогрессом X/5
       - expire через N дней
    """
    while True:
        try:
            # 5 минут
            for uid, ref_id, done in get_refs_to_notify_5min():
                if not ref_id:
                    set_ref_notified(uid, "notified_5min")
                    continue
                display = get_user_display(uid).lstrip("@")
                await _notify_referrer(ref_id, "ref_notify_5min", username=display)
                set_ref_notified(uid, "notified_5min")

            # 10 минут
            for uid, ref_id, done in get_refs_to_notify_10min():
                if not ref_id:
                    set_ref_notified(uid, "notified_10min")
                    continue
                # если уже 5/5 — не шлём (там другое уведомление)
                try:
                    need = int(get_setting("ref_tasks_required") or 5)
                except Exception:
                    need = 5
                if done >= need:
                    set_ref_notified(uid, "notified_10min")
                    continue
                display = get_user_display(uid).lstrip("@")
                await _notify_referrer(ref_id, "ref_notify_10min",
                                       username=display, done=done, need=need)
                set_ref_notified(uid, "notified_10min")

            # истечение через N дней
            try:
                days = int(get_setting("ref_deadline_days") or 7)
            except Exception:
                days = 7
            expired = expire_old_ref_progress(days)
            # уведомлять реферера об истечении не просили, молчим
        except Exception as e:
            print("ref_worker error:", e)
        await asyncio.sleep(60)


# ================== ФОН: АВТО-БЭКАП ==================
async def daily_backup():
    while True:
        try:
            now = datetime.now()
            targets = [
                now.replace(hour=8, minute=0, second=0, microsecond=0),
                now.replace(hour=20, minute=0, second=0, microsecond=0),
            ]
            next_run = None
            for t in targets:
                if t > now:
                    next_run = t
                    break
            if next_run is None:
                next_run = now.replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=1)

            wait_seconds = (next_run - now).total_seconds()
            print(f"Авто-бэкап: следующий через {int(wait_seconds)} сек ({next_run.strftime('%H:%M')})")
            await asyncio.sleep(wait_seconds)

            data = export_users_to_json()
            fname = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(fname, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            try:
                file = FSInputFile(fname)
                await bot.send_document(
                    ADMIN_ID, file,
                    caption=(f"📦 <b>Авто-бэкап</b>\n"
                             f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                             f"👥 Юзеров: <b>{len(data['users'])}</b>\n"
                             f"💖 Реф-прогрессов: <b>{len(data['ref_progress'])}</b>\n"
                             f"💸 Заявок: <b>{len(data['withdrawals'])}</b>"),
                    parse_mode="HTML")
                print("Авто-бэкап отправлен")
            except Exception as e:
                print("Backup send error:", e)
            try:
                os.remove(fname)
            except Exception:
                pass
        except Exception as e:
            print("daily_backup error:", e)
            await asyncio.sleep(3600)


# ================== ЗАПУСК ==================
async def main():
    init_db()
    asyncio.create_task(ref_worker())
    asyncio.create_task(daily_backup())
    print("Бот запущен")
    print(f"BOT_ID: {BOT_ID}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
