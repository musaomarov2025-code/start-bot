import asyncio
import json
import os
import random
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
    get_place, can_take_bonus, set_bonus_taken,
    get_all_user_ids,
    is_welcome_bonus_paid, mark_welcome_bonus_paid,
    create_pending_referral, get_pending_refs_count,
    get_confirmed_refs_count, get_user_referrals,
    confirm_referral, expire_old_referrals,
    get_refs_to_remind, mark_reminded,
    create_withdrawal, get_withdrawal, get_pending_withdrawals, set_withdrawal_status,
    get_withdrawal_history,
    get_stats, get_top_balance, get_top_refs,
    create_promo, get_promo, get_promo_op_reqs, list_promos, delete_promo,
    activate_promo, activate_promo_after_op, get_promo_uses_list,
    add_custom_op, list_custom_ops, delete_custom_op,
    bh_reward_mark, bh_reward_was_given,
    add_custom_task, list_custom_tasks, get_custom_task, delete_custom_task,
    get_next_custom_task, mark_custom_task_done,
    mark_op_passed, get_user_passed_ops, has_op_passed,
    add_ad_source, get_ad_source, list_ad_sources, delete_ad_source,
    mark_ad_user, mark_ad_user_op, mark_ad_user_blocked,
    increment_ad_refs, add_ad_stars, get_ad_stats_period,
    increment_ad_click,
    set_waiting_withdraw, get_waiting_withdraw, delete_waiting_withdraw,
)
from keyboards import (
    main_menu, earn_kb, profile_kb, gifts_kb, task_kb,
    daily_bonus_kb, daily_back_kb, promo_cancel_kb,
    admin_kb, admin_wd_kb, priv_kb, settings_kb,
    promos_kb, promo_type_kb, promo_op_select_kb, promo_list_kb, promo_view_kb,
    user_view_kb, back_admin_kb,
    bh_kb, tasks_kb, ctasks_kb, ctask_type_kb, cop_kb, cop_type_kb, stats_kb,
    op_screen_kb, friends_check_kb,
    broadcast_menu_kb, broadcast_confirm_kb, broadcast_preview_kb,
    ad_menu_kb, wd_video_kb,
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

BOT_ID = int(BOT_TOKEN.split(":")[0]) if BOT_TOKEN else 0

PENDING_PROMO = {}
PENDING_WD = {}


# ================== ХЕЛПЕР ==================
def _smart_text(message):
    if message.entities:
        return message.html_text or message.text or ""
    return message.text or ""


# ================== FSM ==================
class PromoCreate(StatesGroup):
    waiting_code = State()
    waiting_amount = State()
    waiting_amount_min = State()
    waiting_uses = State()
    waiting_op_select = State()

class PromoDelete(StatesGroup):
    waiting_code = State()

class SetValue(StatesGroup):
    waiting_value = State()

class UserPromo(StatesGroup):
    waiting_code = State()

class PrivEdit(StatesGroup):
    waiting_text = State()
    waiting_buttons = State()

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
    waiting_custom = State()

class TasksEdit(StatesGroup):
    waiting_reward = State()

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

class AdAdd(StatesGroup):
    waiting_code = State()
    waiting_owner = State()
    waiting_price = State()

class AdDel(StatesGroup):
    waiting_code = State()

# === РАССЫЛКА ===
class BroadcastFlow(StatesGroup):
    waiting_text = State()
    waiting_media = State()      # фото / стикер / видео
    waiting_buttons = State()
    waiting_count = State()

# === ВИДЕО ВЫВОДА (отдельный FSM) ===
class WDVideo(StatesGroup):
    waiting_video = State()


# ============ BOTOHUB ============
def bh_enabled():
    return get_setting("botohub_enabled") == "1"


def tasks_enabled():
    return get_setting("tasks_enabled") == "1"


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


async def check_custom_task(user_id, check_type, check_target):
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


# ============ СБОР ОП ============
async def _get_botohub_pending(user_id):
    if not (bh_enabled() and BOTOHUB_TOKEN):
        return []
    try:
        count = int(get_setting("botohub_entry_count") or 2)
    except Exception:
        count = 2
    data = await bh_get_tasks(user_id, count)
    tasks = data.get("tasks", [])
    return [t for t in tasks if not t.get("completed") and t.get("url")]


async def collect_op_items(user_id):
    passed_set = set(get_user_passed_ops(user_id))
    items = []
    for t in await _get_botohub_pending(user_id):
        url = t.get("url")
        op_key = f"bh:{url}"
        if op_key in passed_set:
            continue
        items.append((op_key, "Подписаться", url, False))
    try:
        custom_limit = int(get_setting("op_custom_entry_count") or 0)
    except Exception:
        custom_limit = 0
    customs = list_custom_ops("entry")
    if custom_limit > 0:
        customs = customs[:custom_limit]
    for cid, title, link in customs:
        op_key = f"custom:{cid}"
        if op_key in passed_set:
            continue
        items.append((op_key, title, link, False))
    return items


async def _mark_botohub_completed(user_id):
    if not (bh_enabled() and BOTOHUB_TOKEN):
        return
    try:
        count = int(get_setting("botohub_entry_count") or 2)
    except Exception:
        count = 2
    data = await bh_get_tasks(user_id, count)
    tasks = data.get("tasks", [])
    for t in tasks:
        if t.get("completed") and t.get("url"):
            mark_op_passed(user_id, f"bh:{t['url']}")


async def send_op_screen(chat_id, user_id, header_text=None,
                         confirm_callback="op_check", pending_promo=None):
    items = await collect_op_items(user_id)
    if not items:
        return True
    text = header_text if header_text else get_setting("botohub_text")
    kb = op_screen_kb(items, confirm_callback=confirm_callback)
    await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")
    return False


async def _guard_ops(message_or_call):
    if isinstance(message_or_call, Message):
        user_id = message_or_call.from_user.id
        chat_id = message_or_call.chat.id
    else:
        user_id = message_or_call.from_user.id
        chat_id = message_or_call.from_user.id
    items = await collect_op_items(user_id)
    if not items:
        return True
    await bot.send_message(chat_id, get_setting("botohub_text"),
                           reply_markup=op_screen_kb(items), parse_mode="HTML")
    return False


# ============ ПЕРЕХОД В МЕНЮ ============
async def _send_earn_screen(chat_id, user_id):
    me = await bot.get_me()
    ref_bonus = get_setting("ref_bonus")
    refs = get_confirmed_refs_count(user_id)
    ref_link = f"https://t.me/{me.username}?start=ref_{user_id}"
    share_text = "Заходи в бота, тут раздают звёзды ⭐"
    share_url = (f"https://t.me/share/url?url={quote(ref_link, safe='')}"
                 f"&text={quote(share_text, safe='')}")

    text = (
        f'Приглашай пользователей в бота и получай по {ref_bonus} '
        f'<tg-emoji emoji-id="5895708410447401643">🌟</tg-emoji> '
        f'как только они подпишутся на каналы!\n\n'
        f'<tg-emoji emoji-id="5260730055880876557">⛓</tg-emoji><b>Ваша ссылка:</b>\n'
        f'{ref_link}\n\n'
        f'<blockquote>'
        f'<tg-emoji emoji-id="5361948905900635660">❓</tg-emoji> <b>Как использовать реферальную ссылку?</b>\n'
        f'• Отправь её друзьям в личные сообщения <tg-emoji emoji-id="5258513401784573443">👥</tg-emoji>\n'
        f'• Поделись ссылкой в своём Telegram-канале <tg-emoji emoji-id="5258236805890710909">⬅️</tg-emoji>\n'
        f'• Оставь её в комментариях или чатах <tg-emoji emoji-id="5258215850745275216">➡️</tg-emoji>\n'
        f'• Распространяй ссылку в соцсетях: TikTok, Instagram, WhatsApp и других '
        f'<tg-emoji emoji-id="5258057130228849960">✅</tg-emoji>'
        f'</blockquote>\n\n'
        f'<tg-emoji emoji-id="5258513401784573443">👥</tg-emoji> Вы пригласили: <b>{refs}</b>'
    )
    await bot.send_message(chat_id, text, reply_markup=earn_kb(share_url), parse_mode="HTML")


async def _go_to_main(chat_id, user_id):
    await bot.send_message(chat_id, "👇", reply_markup=main_menu())
    await _send_earn_screen(chat_id, user_id)


# ============ 2 ДРУГА (вариант Б) ============
def _friends_required():
    try:
        return int(get_setting("withdraw_friends_required") or 2)
    except Exception:
        return 2


def _friends_screen_text(user_id):
    need = _friends_required()
    refs_now = get_confirmed_refs_count(user_id)
    done = min(need, refs_now)
    me_link_base = "https://t.me/"
    return need, done, refs_now


async def _show_friends_screen(target, user_id, edit_message=False):
    w = get_waiting_withdraw(user_id)
    if not w:
        return
    need, done, _ = _friends_screen_text(user_id)
    me = await bot.get_me()
    ref_link = f"https://t.me/{me.username}?start=ref_{user_id}"
    text = (
        f'<tg-emoji emoji-id="5449800250032143374">🎁</tg-emoji> '
        f'<b>Чтобы получить подарок — пригласи {need} друзей!</b>\n\n'
        f'<tg-emoji emoji-id="5258513401784573443">👥</tg-emoji> '
        f'Прогресс: <b>{done}/{need}</b>\n\n'
        f'<tg-emoji emoji-id="5318757666800031348">✅</tg-emoji> '
        f'<b>Твоя ссылка:</b>\n{ref_link}\n\n'
        f'<blockquote><tg-emoji emoji-id="5452069934089641166">❓</tg-emoji> '
        f'Друг должен зайти по ссылке и забрать бонус</blockquote>'
    )
    kb = friends_check_kb()

    if edit_message and isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            return
        except Exception:
            pass

    if isinstance(target, int):
        await bot.send_message(target, text, reply_markup=kb, parse_mode="HTML")
    elif isinstance(target, CallbackQuery):
        await target.message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=kb, parse_mode="HTML")


async def _create_withdraw_waiting(user_id, gift_key, target):
    set_waiting_withdraw(user_id, gift_key)
    await _show_friends_screen(target, user_id)


async def _check_and_fulfill_waiting(user_id):
    w = get_waiting_withdraw(user_id)
    if not w:
        return False
    _, gift_key, _ = w
    need = _friends_required()
    refs_now = get_confirmed_refs_count(user_id)
    if refs_now < need:
        return False
    if gift_key not in GIFTS:
        delete_waiting_withdraw(user_id)
        return False
    name, price = GIFTS[gift_key]
    balance = get_balance(user_id)
    if balance < price:
        return False

    wid = create_withdrawal(user_id, price, gift_key)
    delete_waiting_withdraw(user_id)

    new_balance = get_balance(user_id)
    gift_emoji_id = GIFTS_EMOJI.get(gift_key, "")

    text = (
        f'<tg-emoji emoji-id="6026257381678124710">✅</tg-emoji> '
        f'<b>Заявка #{wid} создана!</b>\n\n'
        f'<tg-emoji emoji-id="5449800250032143374">🎁</tg-emoji> Подарок: '
        f'<tg-emoji emoji-id="{gift_emoji_id}">🎁</tg-emoji> {name}\n'
        f'<tg-emoji emoji-id="5224257782013769471">💰</tg-emoji> Твой баланс: <b>{new_balance}</b> '
        f'<tg-emoji emoji-id="6030656914247914196">⭐</tg-emoji>\n'
        f'<tg-emoji emoji-id="5920433463428650761">⌛</tg-emoji> Ожидай — админ отправит подарок вручную.'
    )
    try:
        await bot.send_message(user_id, text, parse_mode="HTML")
    except Exception:
        pass

    u = get_user(user_id)
    uname = f"@{u[1]}" if u and u[1] else "без username"
    try:
        await bot.send_message(ADMIN_ID,
            f"💸 <b>Новая заявка #{wid}</b>\n\n👤 {uname}\n"
            f"🆔 <code>{user_id}</code>\n🎁 {name}\n💰 {price} ⭐",
            reply_markup=admin_wd_kb(wid), parse_mode="HTML")
    except Exception as e:
        print("Ошибка админу:", e)
    return True


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
    cur.execute("SELECT code, amount, max_uses, used, active, p_type, amount_min FROM promos")
    promos = [{"code": r[0], "amount": r[1], "max_uses": r[2], "used": r[3],
               "active": r[4], "p_type": r[5], "amount_min": r[6]}
              for r in cur.fetchall()]
    cur.execute("SELECT user_id, amount, gift, status, created_at FROM withdrawals")
    withdrawals = [{"user_id": r[0], "amount": r[1], "gift": r[2],
                    "status": r[3], "created_at": r[4]}
                   for r in cur.fetchall()]
    cur.execute("SELECT key, value FROM settings")
    settings = {r[0]: r[1] for r in cur.fetchall()}
    cur.execute("SELECT id, title, link, type, active FROM custom_ops")
    custom_ops = [{"id": r[0], "title": r[1], "link": r[2], "type": r[3], "active": r[4]}
                  for r in cur.fetchall()]
    cur.execute("SELECT id, title, link, reward, active, check_type, check_target FROM custom_tasks")
    custom_tasks = [{"id": r[0], "title": r[1], "link": r[2], "reward": r[3], "active": r[4],
                     "check_type": r[5], "check_target": r[6]} for r in cur.fetchall()]
    try:
        cur.execute("SELECT user_id, op_key, passed_at FROM user_ops")
        user_ops = [{"user_id": r[0], "op_key": r[1], "passed_at": r[2]} for r in cur.fetchall()]
    except Exception:
        user_ops = []
    try:
        cur.execute("SELECT code, owner_id, owner_username, created_at FROM ad_sources")
        ad_sources = [{"code": r[0], "owner_id": r[1], "owner_username": r[2], "created_at": r[3]}
                      for r in cur.fetchall()]
    except Exception:
        ad_sources = []
    conn.close()
    return {"exported_at": datetime.now().isoformat(),
            "users": users, "referrals": referrals, "promos": promos,
            "withdrawals": withdrawals, "settings": settings,
            "custom_ops": custom_ops, "custom_tasks": custom_tasks,
            "user_ops": user_ops, "ad_sources": ad_sources}


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
    cur.execute("DELETE FROM referrals")
    for r in data.get("referrals", []):
        cur.execute("INSERT INTO referrals (user_id, referrer_id, created_at, status) VALUES (?,?,?,?)",
                    (r["user_id"], r["referrer_id"], r.get("created_at"), r.get("status", "pending")))
    for p in data.get("promos", []):
        cur.execute("INSERT OR REPLACE INTO promos (code, amount, max_uses, used, active, p_type, amount_min) VALUES (?,?,?,?,?,?,?)",
                    (p["code"], p["amount"], p["max_uses"], p.get("used", 0),
                     p.get("active", 1), p.get("p_type", "normal"), p.get("amount_min", 0)))
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
    # ============ СТАРТ ============
def _parse_start_arg(arg):
    if not arg:
        return None, None
    if arg.startswith("ref_"):
        return "ref", arg[4:]
    if arg.startswith("ad_"):
        return "ad", arg[3:]
    if arg.startswith("promo_"):
        return "promo", arg[6:]
    return None, None


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    args = message.text.split()
    start_arg = args[1] if len(args) > 1 else ""
    kind, value = _parse_start_arg(start_arg)

    referrer = None
    ad_code = None
    promo_code = None

    if kind == "ref":
        try:
            referrer = int(value)
        except Exception:
            referrer = None
    elif kind == "ad":
        ad_code = value
    elif kind == "promo":
        promo_code = value.upper()

    is_new = add_user(message.from_user.id, message.from_user.username, referrer)
    if not is_new:
        update_username(message.from_user.id, message.from_user.username)

    if not is_welcome_bonus_paid(message.from_user.id):
        try:
            bonus = int(get_setting("welcome_bonus") or 15)
        except Exception:
            bonus = 15
        if bonus > 0:
            add_balance(message.from_user.id, bonus)
            mark_welcome_bonus_paid(message.from_user.id)
            try:
                await message.answer(
                    f'<tg-emoji emoji-id="5895708410447401643">⭐️</tg-emoji> '
                    f'<b>Вы получили {bonus} Звёзд за запуск бота!</b>',
                    parse_mode="HTML")
            except Exception:
                pass

    if is_new and referrer and referrer != message.from_user.id:
        create_pending_referral(message.from_user.id, referrer)
        try:
            await bot.send_message(referrer,
                '<tg-emoji emoji-id="5193018401810822951">🎉</tg-emoji> '
                '<b>По твоей ссылке зашёл новый друг!</b>\n\n'
                'Он должен зайти в прочее и забрать бонус — тогда ты получишь звёзды.',
                parse_mode="HTML")
        except Exception:
            pass

    if ad_code:
        src = get_ad_source(ad_code)
        if src:
            increment_ad_click(ad_code, is_new_user=is_new)
            is_premium = 1 if getattr(message.from_user, "is_premium", False) else 0
            mark_ad_user(message.from_user.id, ad_code,
                         registered=1 if is_new else 0,
                         is_premium=is_premium)

    if get_setting("priv_enabled") == "1":
        priv_text = get_setting("priv_text")
        kb = build_priv_buttons()
        if kb:
            await message.answer(priv_text, reply_markup=kb, parse_mode="HTML")
        else:
            await message.answer(priv_text, parse_mode="HTML")

    await asyncio.sleep(3)

    if promo_code:
        promo = get_promo(promo_code)
        if promo:
            c, amount, max_uses, used, active, p_type, amount_min = promo
            if p_type == "op":
                PENDING_PROMO[message.from_user.id] = promo_code
                header = (
                    f'<tg-emoji emoji-id="5449800250032143374">💬</tg-emoji> '
                    f'Чек даёт вам до <b>{amount}</b> '
                    f'<tg-emoji emoji-id="5895708410447401643">⭐️</tg-emoji>\n\n'
                    f'<blockquote>Для его активации подпишитесь на спонсоров</blockquote>'
                )
                passed = await send_op_screen(message.chat.id, message.from_user.id,
                                              header_text=header, pending_promo=promo_code)
                if not passed:
                    return
                got = activate_promo_after_op(promo_code, message.from_user.id)
                if got:
                    await message.answer(f"✅ Промокод активирован! +{got} ⭐")
                    PENDING_PROMO.pop(message.from_user.id, None)
                await _go_to_main(message.chat.id, message.from_user.id)
                return
            ok, msg_, amt, _, _ = activate_promo(promo_code, message.from_user.id)
            if ok and msg_ != "NEED_OP":
                await message.answer(f"✅ Промокод активирован! +{amt} ⭐")
            await _go_to_main(message.chat.id, message.from_user.id)
            return

    passed = await send_op_screen(message.chat.id, message.from_user.id)
    if not passed:
        return

    await _go_to_main(message.chat.id, message.from_user.id)


@dp.callback_query(F.data == "op_check")
async def op_check_cb(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    await call.answer()

    try:
        await _mark_botohub_completed(user_id)
    except Exception:
        pass

    items = await collect_op_items(user_id)

    if not items:
        # все ОП пройдены
        try:
            await call.message.delete()
        except Exception:
            pass

        mark_ad_user_op(user_id)

        pending = PENDING_PROMO.pop(user_id, None)
        if pending:
            got = activate_promo_after_op(pending, user_id)
            if got:
                await bot.send_message(user_id, f"✅ Промокод активирован! +{got} ⭐")
            await _go_to_main(user_id, user_id)
            return

        await _go_to_main(user_id, user_id)
        return

    # Не все пройдены → alert + edit_text с новым списком
    await call.answer(
        "Подписался не на всё — галочки покажут, что осталось",
        show_alert=True)

    text = get_setting("botohub_text")
    kb = op_screen_kb(items, confirm_callback="op_check")
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        try:
            await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass


# ============ ЗАРАБОТАТЬ ============
@dp.message(F.text == "Заработать звёзды")
async def earn(message: Message):
    if not await _guard_ops(message):
        return
    await _send_earn_screen(message.chat.id, message.from_user.id)


# ============ ПРОЧЕЕ ============
def _profile_text(uid: int, first_name: str) -> str:
    u = get_user(uid)
    balance = u[2] if u else 0
    name = first_name or "друг"
    refs = get_confirmed_refs_count(uid)
    pending = get_pending_refs_count(uid)
    place = get_place(uid)
    return (
        f'<tg-emoji emoji-id="5260399854500191689">👤</tg-emoji> <b>ПРОЧЕЕ</b>\n\n'
        f'<tg-emoji emoji-id="5389099588906922686">🧑</tg-emoji> {name}\n'
        f'<tg-emoji emoji-id="6030656587830399914">🆔</tg-emoji> <code>{uid}</code>\n\n'
        f'<tg-emoji emoji-id="6030656914247914196">⭐</tg-emoji> Баланс: <b>{balance}.00</b>\n'
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


@dp.message(F.text == "Прочее")
async def profile(message: Message):
    if not get_user(message.from_user.id):
        await message.answer("Напиши /start")
        return
    if not await _guard_ops(message):
        return
    text = _profile_text(message.from_user.id, message.from_user.first_name)
    await message.answer(text, reply_markup=profile_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "daily_bonus")
async def cb_daily_bonus(call: CallbackQuery):
    balance = get_balance(call.from_user.id)
    if not can_take_bonus(call.from_user.id):
        await call.message.edit_text(
            f'<tg-emoji emoji-id="5784964035929707157">🎁</tg-emoji> <b>Ежедневные бонусы</b>\n\n'
            f'<tg-emoji emoji-id="5449449325434266744">❄️</tg-emoji> Бонус уже получен сегодня!\n\n'
            f'<tg-emoji emoji-id="5920108570627544286">⭐️</tg-emoji> Твой баланс: {balance} '
            f'<tg-emoji emoji-id="5895708410447401643">🌟</tg-emoji>',
            reply_markup=daily_back_kb(), parse_mode="HTML")
        return
    await call.message.edit_text(
        f'<tg-emoji emoji-id="5784964035929707157">🎁</tg-emoji> <b>Ежедневные бонусы</b>\n\n'
        f'<tg-emoji emoji-id="5449449325434266744">❄️</tg-emoji> Собирай ежедневный бонус каждый день!\n\n'
        f'<tg-emoji emoji-id="5920108570627544286">⭐️</tg-emoji> Твой баланс: {balance} '
        f'<tg-emoji emoji-id="5895708410447401643">🌟</tg-emoji>',
        reply_markup=daily_bonus_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "daily_claim")
async def daily_claim(call: CallbackQuery):
    if not can_take_bonus(call.from_user.id):
        await call.answer("⏳ Уже забирал сегодня!", show_alert=True)
        return
    amount = int(get_setting("daily_bonus"))
    add_balance(call.from_user.id, amount)
    set_bonus_taken(call.from_user.id)
    balance = get_balance(call.from_user.id)

    referrer = confirm_referral(call.from_user.id)
    if referrer:
        ref_bonus = int(get_setting("ref_bonus"))
        add_balance(referrer, ref_bonus)
        add_ad_stars(referrer, ref_bonus)
        increment_ad_refs(call.from_user.id)
        try:
            await bot.send_message(referrer,
                f'<tg-emoji emoji-id="5193018401810822951">🎉</tg-emoji> '
                f'<b>Друг подтвердил реферал!</b>\n\n'
                f'<tg-emoji emoji-id="5469744063815102906">💫</tg-emoji> '
                f'Тебе начислено <b>+{ref_bonus}</b> '
                f'<tg-emoji emoji-id="6030656914247914196">⭐</tg-emoji>',
                parse_mode="HTML")
        except Exception:
            pass

    await call.answer()
    try:
        await call.message.edit_text(
            f'<tg-emoji emoji-id="5784964035929707157">🎁</tg-emoji> <b>Ежедневный бонус получен!</b>\n\n'
            f'<tg-emoji emoji-id="6025976946083500432">💰</tg-emoji> +{amount}'
            f'<tg-emoji emoji-id="5895708410447401643">🌟</tg-emoji>\n'
            f'<tg-emoji emoji-id="5920281855378068765">⭐️</tg-emoji> Баланс: {balance} '
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


# ============ ПРОМОКОД (ручной ввод) ============
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
    code = message.text.strip().upper()
    await state.clear()
    promo = get_promo(code)
    if not promo:
        await message.answer(
            f'<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> '
            f'<b>Промокод не найден</b>\n\n'
            f'Проверьте правильность написания и попробуйте снова',
            parse_mode="HTML")
        return

    c, amount, max_uses, used, active, p_type, amount_min = promo
    if p_type == "op":
        PENDING_PROMO[message.from_user.id] = code
        header = (
            f'<tg-emoji emoji-id="5449800250032143374">💬</tg-emoji> '
            f'Чек даёт вам до <b>{amount}</b> '
            f'<tg-emoji emoji-id="5895708410447401643">⭐️</tg-emoji>\n\n'
            f'<blockquote>Для его активации подпишитесь на спонсоров</blockquote>'
        )
        items = await collect_op_items(message.from_user.id)
        if not items:
            got = activate_promo_after_op(code, message.from_user.id)
            PENDING_PROMO.pop(message.from_user.id, None)
            if got:
                await message.answer(f"✅ Промокод активирован! +{got} ⭐")
            return
        await bot.send_message(message.chat.id, header,
                               reply_markup=op_screen_kb(items), parse_mode="HTML")
        return

    ok, msg_, amt, _, _ = activate_promo(code, message.from_user.id)
    if ok:
        balance = get_balance(message.from_user.id)
        add_ad_stars(message.from_user.id, amt)
        await message.answer(
            f"✅ <b>Промокод активирован!</b>\n\n"
            f"💰 +{amt}.00 ⭐\n⭐️ Баланс: <b>{balance}.00</b>",
            parse_mode="HTML")
    else:
        await message.answer(msg_, parse_mode="HTML")


# ============ /stat_XXX ============
@dp.message(F.text.regexp(r"^/stat_[A-Za-z0-9_]+$"))
async def ad_stats_cmd(message: Message):
    user_id = message.from_user.id
    code = message.text[len("/stat_"):].strip().lower()

    src = get_ad_source(code)
    if not src:
        await message.answer("❌ Такой метки не существует.")
        return
    if src[1] != user_id and user_id != ADMIN_ID:
        await message.answer("❌ У тебя нет доступа к этой метке.")
        return

    owner_username = src[2] or ""
    price_per_click = src[5] if len(src) > 5 else 0

    me = await bot.get_me()
    ref_link = f"https://t.me/{me.username}?start=ad_{code}"

    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    yest_start = today_start - timedelta(days=1)

    total = get_ad_stats_period(code)
    today = get_ad_stats_period(code, today_start.isoformat(), today_end.isoformat())
    yest = get_ad_stats_period(code, yest_start.isoformat(), today_start.isoformat())

    def pct(a, b):
        if not b:
            return 0
        return round(a / b * 100)

    def block(title, s):
        clicks = s["clicks"]
        users = s["users"]
        registered = s["registered"]
        op = s["op"]
        return (
            f"<b>{title}</b>\n"
            f"Переходов: <b>{clicks}</b>\n"
            f"Пользователей: <b>{users}</b> ({pct(users, clicks)}%)\n"
            f"Зарегистрированных: <b>{registered}</b> ({pct(registered, clicks)}%)\n"
            f"Подписки: <b>{op}</b> ({pct(op, clicks)}%)\n"
        )

    users_total = total["users"]
    blocked = total["blocked"]
    alive = users_total - blocked
    premium = total["premium"]
    uniq = total["op"]
    non_uniq = users_total - uniq
    spent = price_per_click * total["clicks"]
    stars = total["stars"]

    text = (
        f"🍑 <b>Статистика</b>\n\n"
        f"{block('Всего', total)}\n"
        f"{block('За вчера', yest)}\n"
        f"{block('За сегодня', today)}\n"
        f"Живых: <b>{alive}</b> ({pct(alive, users_total)}%)\n"
        f"Мертвых: <b>{blocked}</b> ({pct(blocked, users_total)}%)\n\n"
        f"Уникальных: <b>{uniq}</b>\n"
        f"Не уникальных: <b>{non_uniq}</b> ({pct(non_uniq, users_total)}%)\n"
        f"Премиум: <b>{premium}</b> ({pct(premium, users_total)}%) 💎\n\n"
        f"💰 Цена перехода: <b>{price_per_click}</b> ₽\n"
        f"💸 Потрачено: <b>{spent}</b> ₽\n"
        f"⭐ Заработали звёзд: <b>{stars}</b>\n\n"
        f"👤 Рекламодатель: <b>@{owner_username}</b>\n"
        f"🔗 <b>Реф-ссылка:</b>\n<code>{ref_link}</code>"
    )
    if len(text) > 4000:
        text = text[:4000] + "\n...обрезано"
    await message.answer(text, parse_mode="HTML")
    # ============ ЗАДАНИЯ ============
async def show_task(message, link, source="bh", reward=None):
    if reward is None:
        reward = int(get_setting("task_reward"))
    text = (
        f'<tg-emoji emoji-id="5449449325434266744">❄️</tg-emoji> '
        f'<b>Собирай Звёзды за простые задания!</b> '
        f'<tg-emoji emoji-id="5470177992950946662">👇</tg-emoji>\n\n'
        f'<tg-emoji emoji-id="5980930633298350051">✅</tg-emoji> '
        f'Подпишись на канал и нажми «Подтвердить»\n\n'
        f'<tg-emoji emoji-id="5765005318610228026">❌</tg-emoji> '
        f'За отписку или блокировку ресурса, вы получите бан\n\n'
        f'<b>Вознаграждение: +{reward} '
        f'<tg-emoji emoji-id="5895708410447401643">🌟</tg-emoji></b>'
    )
    kb = task_kb(link, source)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


async def _no_tasks_left(message):
    ref_bonus = get_setting("ref_bonus")
    text = (
        f'<tg-emoji emoji-id="5350460637182993292">🎉</tg-emoji> '
        f'<b>Ты молодец, выполнены все доступные задания!</b>\n\n'
        f'<tg-emoji emoji-id="5920433463428650761">🔄</tg-emoji> '
        f'Новые задания скоро появятся…\n\n'
        f'<tg-emoji emoji-id="5449800250032143374">💖</tg-emoji> '
        f'За друга платим больше — +{ref_bonus} '
        f'<tg-emoji emoji-id="5895708410447401643">🌟</tg-emoji>'
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Обновить задания",
            callback_data="tasks_refresh",
            icon_custom_emoji_id="5386367538735104399"
        )],
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@dp.message(F.text == "Задания")
async def tasks_menu(message: Message):
    if not await _guard_ops(message):
        return
    if not tasks_enabled():
        await message.answer("❌ Задания временно недоступны.")
        return
    await message.answer(
        f'<tg-emoji emoji-id="5920433463428650761">⌛</tg-emoji> Ищу новое задание...',
        parse_mode="HTML")

    data = await bh_get_task(message.from_user.id, skip=False)
    if data:
        if data.get("fake"):
            await message.answer("🚫 Задания недоступны для этого аккаунта")
            return
        tasks = data.get("tasks", [])
        if tasks:
            await show_task(message, tasks[0], source="bh")
            return

    custom = get_next_custom_task(message.from_user.id)
    if custom:
        tid, title, link, reward_db, ctype, ctarget = custom
        reward = int(get_setting("task_reward"))
        await show_task(message, link, source=f"ct:{tid}", reward=reward)
        return

    await _no_tasks_left(message)


@dp.callback_query(F.data == "tasks_refresh")
async def tasks_refresh(call: CallbackQuery):
    await call.answer()
    if not await _guard_ops(call):
        return
    try:
        await call.message.delete()
    except Exception:
        pass
    if not tasks_enabled():
        await call.message.answer("❌ Задания временно недоступны.")
        return
    await call.message.answer(
        f'<tg-emoji emoji-id="5920433463428650761">⌛</tg-emoji> Ищу новое задание...',
        parse_mode="HTML")

    data = await bh_get_task(call.from_user.id, skip=False)
    if data:
        if data.get("fake"):
            await call.message.answer("🚫 Задания недоступны для этого аккаунта")
            return
        tasks = data.get("tasks", [])
        if tasks:
            await show_task(call.message, tasks[0], source="bh")
            return

    custom = get_next_custom_task(call.from_user.id)
    if custom:
        tid, title, link, reward_db, ctype, ctarget = custom
        reward = int(get_setting("task_reward"))
        await show_task(call.message, link, source=f"ct:{tid}", reward=reward)
        return

    await _no_tasks_left(call.message)


@dp.callback_query(F.data == "task_skip")
async def task_skip(call: CallbackQuery):
    await call.answer()
    if not await _guard_ops(call):
        return
    try:
        await call.message.delete()
    except Exception:
        pass

    data = await bh_get_task(call.from_user.id, skip=True)
    if data:
        if data.get("fake"):
            await call.message.answer("🚫 Задания недоступны для этого аккаунта")
            return
        tasks = data.get("tasks", [])
        if tasks:
            await call.message.answer(
                f'<tg-emoji emoji-id="5260450573768990626">➡️</tg-emoji> '
                f'<b>Задание пропущено</b>\n\n'
                f'<tg-emoji emoji-id="5920433463428650761">⌛</tg-emoji> '
                f'Загружаю следующее задание...',
                parse_mode="HTML")
            await show_task(call.message, tasks[0], source="bh")
            return

    custom = get_next_custom_task(call.from_user.id)
    if custom:
        tid, title, link, reward_db, ctype, ctarget = custom
        reward = int(get_setting("task_reward"))
        await call.message.answer(
            f'<tg-emoji emoji-id="5260450573768990626">➡️</tg-emoji> '
            f'<b>Задание пропущено</b>\n\n'
            f'<tg-emoji emoji-id="5920433463428650761">⌛</tg-emoji> '
            f'Загружаю следующее задание...',
            parse_mode="HTML")
        await show_task(call.message, link, source=f"ct:{tid}", reward=reward)
        return

    await _no_tasks_left(call.message)


async def _send_reward_and_next(call, msg, reward, balance, user_id):
    reward_text = (
        f'<tg-emoji emoji-id="6026257381678124710">✅</tg-emoji> <b>Задание выполнено!</b>\n\n'
        f'<tg-emoji emoji-id="6025976946083500432">💰</tg-emoji> Награда: <b>+{reward}</b> '
        f'<tg-emoji emoji-id="6030656914247914196">⭐</tg-emoji>\n'
        f'<tg-emoji emoji-id="5427168083074628963">💎</tg-emoji> Баланс: <b>{balance}</b> '
        f'<tg-emoji emoji-id="6030656914247914196">⭐</tg-emoji>\n\n'
        f'<tg-emoji emoji-id="5920433463428650761">⌛</tg-emoji> Загружаю следующее задание...'
    )
    if msg:
        try:
            await msg.delete()
        except Exception:
            pass
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.message.answer(reward_text, parse_mode="HTML")

    data = await bh_get_task(user_id, skip=False)
    if data and not data.get("fake"):
        tasks = data.get("tasks", [])
        if tasks:
            await show_task(call.message, tasks[0], source="bh")
            return

    custom = get_next_custom_task(user_id)
    if custom:
        tid, title, link, reward_db, ctype, ctarget = custom
        reward2 = int(get_setting("task_reward"))
        await show_task(call.message, link, source=f"ct:{tid}", reward=reward2)
        return

    await _no_tasks_left(call.message)


@dp.callback_query(F.data.startswith("tc:"))
async def task_check(call: CallbackQuery):
    user_id = call.from_user.id
    await call.answer()
    source = call.data.split(":", 1)[1]

    try:
        msg = await call.message.answer("⏳ Проверяю подписку, подожди...")
    except Exception:
        msg = None

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
        mark_custom_task_done(user_id, tid)
        reward = int(get_setting("task_reward"))
        add_balance(user_id, reward)
        add_ad_stars(user_id, reward)
        balance = get_balance(user_id)
        await _send_reward_and_next(call, msg, reward, balance, user_id)
        return

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

    reward = int(get_setting("task_reward"))
    add_balance(user_id, reward)
    add_ad_stars(user_id, reward)
    balance = get_balance(user_id)
    await _send_reward_and_next(call, msg, reward, balance, user_id)


# ============ ВЫВОД ============
async def _show_gifts_with_video(chat_id, user_id):
    video_id = get_setting("withdraw_video_id")
    kb = gifts_kb()
    caption = '<tg-emoji emoji-id="5427236501903655352">❣️</tg-emoji> <b>Выбери подарок</b>'
    try:
        if video_id:
            await bot.send_video(
                chat_id=chat_id, video=video_id,
                caption=caption, reply_markup=kb, parse_mode="HTML")
        else:
            await bot.send_message(chat_id, caption, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        print("video send error:", e)
        try:
            await bot.send_message(chat_id, caption, reply_markup=kb, parse_mode="HTML")
        except Exception:
            pass


@dp.message(F.text == "Вывести звёзды")
async def withdraw(message: Message, state: FSMContext):
    if not await _guard_ops(message):
        return
    await state.clear()
    user_id = message.from_user.id
    chat_id = message.chat.id

    w = get_waiting_withdraw(user_id)
    if w:
        await _show_friends_screen(message, user_id)
        return

    extra_items = []
    if bh_enabled() and BOTOHUB_TOKEN:
        try:
            wd_count = int(get_setting("botohub_withdraw_count"))
        except Exception:
            wd_count = 6
        data = await bh_get_tasks(user_id, wd_count)
        tasks = data.get("tasks", [])
        not_done = [t for t in tasks if not t.get("completed")]
        for t in not_done:
            link = t.get("url")
            if link:
                extra_items.append((f"bh_wd:{link}", "Подписаться", link, False))
    customs_wd = list_custom_ops("withdraw")
    for cid, title, link in customs_wd:
        extra_items.append((f"custom_wd:{cid}", title, link, False))

    if extra_items:
        PENDING_WD[user_id] = "next_gift"
        await bot.send_message(
            chat_id, get_setting("botohub_text"),
            reply_markup=op_screen_kb(extra_items, confirm_callback="op_check_wd"),
            parse_mode="HTML")
        return

    await _show_gifts_with_video(chat_id, user_id)


@dp.callback_query(F.data == "op_check_wd")
async def op_check_wd_cb(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    await call.answer()
    await asyncio.sleep(2)

    still_not_done = []
    if bh_enabled() and BOTOHUB_TOKEN:
        try:
            wd_count = int(get_setting("botohub_withdraw_count"))
        except Exception:
            wd_count = 6
        data = await bh_get_tasks(user_id, wd_count)
        tasks = data.get("tasks", [])
        still_not_done = [t for t in tasks if not t.get("completed") and t.get("url")]

    if still_not_done:
        await call.answer("Ты ещё не подписался на все каналы", show_alert=True)
        return

    try:
        await call.message.delete()
    except Exception:
        pass

    await _show_gifts_with_video(user_id, user_id)


@dp.callback_query(F.data.startswith("gift:"))
async def cb_gift(call: CallbackQuery, state: FSMContext):
    if not await _guard_ops(call):
        return
    key = call.data.split(":")[1]
    if key not in GIFTS:
        await call.answer("Подарок не найден")
        return
    name, price = GIFTS[key]
    balance = get_balance(call.from_user.id)
    if balance < price:
        need_sum = price - balance
        await call.answer(f"❌ Не хватает {need_sum} ⭐\nНужно: {price} ⭐\nУ тебя: {balance} ⭐",
                          show_alert=True)
        return

    user_id = call.from_user.id
    need = _friends_required()
    refs_now = get_confirmed_refs_count(user_id)

    if refs_now >= need:
        try:
            await call.message.delete()
        except Exception:
            pass
        await create_order(call, key)
        return

    set_waiting_withdraw(user_id, key)
    try:
        await call.message.delete()
    except Exception:
        pass
    await _show_friends_screen(user_id, user_id)


@dp.callback_query(F.data == "wd_friends_check")
async def wd_friends_check_cb(call: CallbackQuery):
    user_id = call.from_user.id

    ok = await _check_and_fulfill_waiting(user_id)

    await call.answer("Обновлено", show_alert=True)

    if ok:
        try:
            await call.message.delete()
        except Exception:
            pass
        return

    w = get_waiting_withdraw(user_id)
    if not w:
        return

    # обновляем то же сообщение
    await _show_friends_screen(call, user_id, edit_message=True)


async def create_order(call: CallbackQuery, key):
    name, price = GIFTS[key]
    gift_emoji_id = GIFTS_EMOJI.get(key, "")
    balance = get_balance(call.from_user.id)
    if balance < price:
        await call.answer(f"❌ Нужно {price} ⭐", show_alert=True)
        return
    wid = create_withdrawal(call.from_user.id, price, key)
    new_balance = get_balance(call.from_user.id)
    uname = f"@{call.from_user.username}" if call.from_user.username else "без username"

    text = (
        f'<tg-emoji emoji-id="6026257381678124710">✅</tg-emoji> <b>Заявка #{wid} создана!</b>\n\n'
        f'<tg-emoji emoji-id="5449800250032143374">🎁</tg-emoji> Подарок: '
        f'<tg-emoji emoji-id="{gift_emoji_id}">🎁</tg-emoji> {name}\n'
        f'<tg-emoji emoji-id="5224257782013769471">💰</tg-emoji> Твой баланс: <b>{new_balance}</b> '
        f'<tg-emoji emoji-id="6030656914247914196">⭐</tg-emoji>\n'
        f'<tg-emoji emoji-id="5920433463428650761">⌛</tg-emoji> Ожидай — админ отправит подарок вручную.'
    )
    try:
        await bot.send_message(call.from_user.id, text, parse_mode="HTML")
    except Exception as e:
        print("Ошибка юзеру:", e)
    try:
        await bot.send_message(ADMIN_ID,
            f"💸 <b>Новая заявка #{wid}</b>\n\n👤 {uname}\n"
            f"🆔 <code>{call.from_user.id}</code>\n🎁 {name}\n💰 {price} ⭐",
            reply_markup=admin_wd_kb(wid), parse_mode="HTML")
    except Exception as e:
        print("Ошибка админу:", e)
