import asyncio
import json
import os
import time
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
    BOTOHUB_TOKEN, BOTOHUB_URL, BOTOHUB_TASKS_URL, OP_CACHE_HOURS,
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
    get_stats, get_top_balance, get_top_refs, get_extended_stats,
    create_promo, get_promo, get_promo_op_reqs, list_promos, delete_promo,
    activate_promo, activate_promo_after_op, get_promo_uses_list,
    add_custom_op, list_custom_ops, delete_custom_op,
    bh_reward_mark, bh_reward_was_given,
    add_custom_task, list_custom_tasks, get_custom_task, delete_custom_task,
    get_next_custom_task, mark_custom_task_done,
    mark_op_passed, get_user_passed_ops, has_op_passed,
    mark_op_passed_cached, get_cached_op_keys, clear_expired_op_cache,
    mark_user_blocked, is_user_blocked, get_blocked_count,
    add_ad_source, get_ad_source, list_ad_sources, delete_ad_source,
    mark_ad_user, mark_ad_user_op, mark_ad_user_blocked,
    increment_ad_refs, add_ad_stars, get_ad_stats_period,
    increment_ad_click,
    set_waiting_withdraw, get_waiting_withdraw, delete_waiting_withdraw,
    get_pending_withdrawals_count, get_pending_withdrawals_page,
    bulk_accept_withdrawals, bulk_reject_withdrawals,
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
    wd_list_kb, wd_bulk_confirm_kb,
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

BOT_ID = int(BOT_TOKEN.split(":")[0]) if BOT_TOKEN else 0

PENDING_PROMO = {}
PENDING_WD = {}

# п.3А: хранит ID последнего сообщения меню у юзера
# {user_id: message_id}
MENU_MSG = {}


# ================== ХЕЛПЕР ==================
def _smart_text(message):
    if message.entities:
        return message.html_text or message.text or ""
    return message.text or ""


async def _safe_delete(chat_id, message_id):
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


async def _safe_send(chat_id, text, **kwargs):
    """Обёртка: помечает юзера как заблокировавшего при Forbidden."""
    try:
        return await bot.send_message(chat_id, text, **kwargs)
    except Exception as e:
        es = str(e).lower()
        if "blocked" in es or "chat not found" in es or "user is deactivated" in es:
            try:
                mark_user_blocked(chat_id)
                mark_ad_user_blocked(chat_id)
            except Exception:
                pass
        raise


async def _send_menu_msg(chat_id, user_id, text, reply_markup=None, parse_mode=None):
    """
    Шлёт сообщение меню и удаляет предыдущее сообщение бота у этого юзера.
    Сохраняет новый message_id в MENU_MSG.
    """
    if get_setting("menu_edit_enabled") == "1":
        old_id = MENU_MSG.get(user_id)
        if old_id:
            await _safe_delete(chat_id, old_id)
    try:
        msg = await bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
        MENU_MSG[user_id] = msg.message_id
        return msg
    except Exception as e:
        es = str(e).lower()
        if "blocked" in es or "chat not found" in es or "user is deactivated" in es:
            mark_user_blocked(user_id)
        raise


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

class BroadcastFlow(StatesGroup):
    waiting_text = State()
    waiting_media = State()
    waiting_buttons = State()
    waiting_count = State()


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
    """
    Собирает ОП-экрана: только непройденные (не в user_ops и не в кэше 48ч).
    """
    passed_set = set(get_user_passed_ops(user_id))
    cached_set = get_cached_op_keys(user_id, hours=OP_CACHE_HOURS)
    items = []

    for t in await _get_botohub_pending(user_id):
        url = t.get("url")
        op_key = f"bh:{url}"
        if op_key in passed_set:
            continue
        if op_key in cached_set:
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
        if op_key in cached_set:
            continue
        items.append((op_key, title, link, False))

    return items


async def _mark_botohub_completed(user_id):
    """
    Помечает пройденные Botohub-каналы в user_ops И в кэш 48ч.
    """
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
            op_key = f"bh:{t['url']}"
            mark_op_passed(user_id, op_key)
            mark_op_passed_cached(user_id, op_key)


async def send_op_screen(chat_id, user_id, header_text=None,
                         confirm_callback="op_check", pending_promo=None):
    """
    Возвращает True, если ОП не нужны (или уже пройдены).
    Иначе шлёт экран и возвращает False.
    """
    items = await collect_op_items(user_id)
    if not items:
        return True
    text = header_text if header_text else get_setting("botohub_text")
    kb = op_screen_kb(items, confirm_callback=confirm_callback)
    await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")
    return False


async def _guard_ops(message_or_call):
    """
    True — можно идти дальше, False — показали ОП-экран.
    """
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
    await _send_menu_msg(chat_id, user_id, text, reply_markup=earn_kb(share_url), parse_mode="HTML")


async def _go_to_main(chat_id, user_id):
    try:
        await bot.send_message(chat_id, "👇", reply_markup=main_menu())
    except Exception as e:
        es = str(e).lower()
        if "blocked" in es or "chat not found" in es or "user is deactivated" in es:
            mark_user_blocked(user_id)
    await _send_earn_screen(chat_id, user_id)


# ============ 3 ДРУГА ============
def _friends_required():
    try:
        return int(get_setting("withdraw_friends_required") or 3)
    except Exception:
        return 3


def _friends_screen_text(user_id):
    """Собирает текст и клавиатуру экрана друзей."""
    w = get_waiting_withdraw(user_id)
    if not w:
        return None, None
    _, gift_key, friends_base, _ = w
    need = _friends_required()
    refs_now = get_confirmed_refs_count(user_id)
    done = refs_now - friends_base
    if done < 0:
        done = 0
    if done > need:
        done = need
    return need, done


async def _show_friends_screen(target, user_id, edit_message=False):
    w = get_waiting_withdraw(user_id)
    if not w:
        return
    _, gift_key, friends_base, _ = w
    if friends_base is None:
        friends_base = 0
    need = _friends_required()
    refs_now = get_confirmed_refs_count(user_id)
    done = refs_now - friends_base
    if done < 0:
        done = 0
    if done > need:
        done = need

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
    refs_now = get_confirmed_refs_count(user_id)
    set_waiting_withdraw(user_id, gift_key, refs_now)
    await _show_friends_screen(target, user_id)


async def _check_and_fulfill_waiting(user_id):
    w = get_waiting_withdraw(user_id)
    if not w:
        return False
    _, gift_key, friends_base, _ = w
    if friends_base is None:
        friends_base = 0
    need = _friends_required()
    refs_now = get_confirmed_refs_count(user_id)
    done = refs_now - friends_base
    if done < need:
        return False
    if gift_key not in GIFTS:
        delete_waiting_withdraw(user_id)
        return False
    name, price = GIFTS[gift_key]
    balance = get_balance(user_id)
    if balance < price:
        delete_waiting_withdraw(user_id)
        return False
    wid = create_withdrawal(user_id, price, gift_key)
    delete_waiting_withdraw(user_id)
    gift_emoji_id = GIFTS_EMOJI.get(gift_key, "")
    text = (
        f'<tg-emoji emoji-id="6026257381678124710">✅</tg-emoji> '
        f'<b>Заявка #{wid} создана!</b>\n\n'
        f'<tg-emoji emoji-id="5449800250032143374">🎁</tg-emoji> Подарок: '
        f'<tg-emoji emoji-id="{gift_emoji_id}">🎁</tg-emoji> {name}\n'
        f'<tg-emoji emoji-id="5224257782013769471">💰</tg-emoji> Сумма: {price} '
        f'<tg-emoji emoji-id="5386367538735104399">⭐</tg-emoji>\n'
        f'<tg-emoji emoji-id="5920433463428650761">⌛</tg-emoji> Ожидай — админ отправит подарок вручную.'
    )
    try:
        await _safe_send(user_id, text, parse_mode="HTML")
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


# ============ БЭКАП (экспорт/импорт — без изменений) ============
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

    # БОНУС за /start (только новым)
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
                'Он должен зайти в раздел «Прочее» и забрать бонус — тогда ты получишь звёзды.',
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
    await call.answer("⏳ Проверяю...")
    await asyncio.sleep(2)

    try:
        await _mark_botohub_completed(user_id)
    except Exception:
        pass

    items = await collect_op_items(user_id)
    if not items:
        # всё пройдено
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

    # Есть непройденные — РЕДАКТИРУЕМ то же сообщение (п.1)
    text = get_setting("botohub_text")
    kb = op_screen_kb(items)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        try:
            await call.message.answer("❌ Подписался не на всё — галочки покажут, что осталось.",
                                      parse_mode="HTML")
        except Exception:
            pass
          # ============ ЗАРАБОТАТЬ ============
@dp.message(F.text == "Заработать звёзды")
async def earn(message: Message):
    if not await _guard_ops(message):
        return
    await _send_earn_screen(message.chat.id, message.from_user.id)


# ============ ПРОЧЕЕ (бывш. Профиль) ============
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
    await _send_menu_msg(message.chat.id, message.from_user.id, text,
                         reply_markup=profile_kb(), parse_mode="HTML")


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
        ok = await _check_and_fulfill_waiting(user_id)
        if ok:
            return
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
    await call.answer("⏳ Проверяю...")
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
        # Редактируем то же сообщение (п.1)
        try:
            items = []
            for t in still_not_done:
                link = t.get("url")
                items.append((f"bh_wd:{link}", "Подписаться", link, False))
            for cid, title, link in list_custom_ops("withdraw"):
                items.append((f"custom_wd:{cid}", title, link, False))
            await call.message.edit_text(
                get_setting("botohub_text"),
                reply_markup=op_screen_kb(items, confirm_callback="op_check_wd"),
                parse_mode="HTML")
        except Exception:
            await call.message.answer("❌ Подписался не на всё — галочки покажут, что осталось.")
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

    existing = get_waiting_withdraw(user_id)
    if existing and existing[1] != key:
        delete_waiting_withdraw(user_id)

    refs_now = get_confirmed_refs_count(user_id)
    set_waiting_withdraw(user_id, key, refs_now)

    try:
        await call.message.delete()
    except Exception:
        pass

    ok = await _check_and_fulfill_waiting(user_id)
    if ok:
        return

    await _show_friends_screen(user_id, user_id)


@dp.callback_query(F.data == "wd_friends_check")
async def wd_friends_check_cb(call: CallbackQuery):
    user_id = call.from_user.id
    await call.answer()

    ok = await _check_and_fulfill_waiting(user_id)
    if ok:
        try:
            await call.message.delete()
        except Exception:
            pass
        return

    w = get_waiting_withdraw(user_id)
    if not w:
        await call.answer("Заявка не найдена", show_alert=True)
        return

    # РЕДАКТИРУЕМ то же сообщение (п.4А)
    await _show_friends_screen(call, user_id, edit_message=True)


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
        print("Ошибка юзеру:", e)
    try:
        await bot.send_message(ADMIN_ID,
            f"💸 <b>Новая заявка #{wid}</b>\n\n👤 {uname}\n"
            f"🆔 <code>{call.from_user.id}</code>\n🎁 {name}\n💰 {price} ⭐",
            reply_markup=admin_wd_kb(wid), parse_mode="HTML")
    except Exception as e:
        print("Ошибка админу:", e)
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
        f"📥 ОП на входе (Botohub): <b>{get_setting('botohub_entry_count')}</b>\n"
        f"📌 Свои ОП на входе: <b>{get_setting('op_custom_entry_count')}</b> (0 = все)\n"
        f"💸 ОП на выводе: <b>{get_setting('botohub_withdraw_count')}</b>\n"
        f"🔤 Текст кнопок: <code>{get_setting('botohub_btn_text')}</code>\n\n"
        f"⏱ Кэш ОП: <b>{OP_CACHE_HOURS}ч</b> (после прохождения не показываем)\n\n"
        f"📝 Текст:\n{get_setting('botohub_text')[:80]}..."
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
    await call.message.answer("✏️ Пришли новый текст для ОП:")
    await state.set_state(BHEdit.waiting_text)


@dp.message(BHEdit.waiting_text)
async def bh_save_text(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    set_setting("botohub_text", _smart_text(message))
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
    await call.message.answer("📥 Сколько ОП брать от Botohub на входе?")
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


@dp.callback_query(F.data == "bh_edit_custom")
async def bh_edit_custom(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("📌 Сколько своих ОП показывать? (0 = все):")
    await state.set_state(BHEdit.waiting_custom)


@dp.message(BHEdit.waiting_custom)
async def bh_save_custom(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        val = int(message.text.strip())
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    set_setting("op_custom_entry_count", val)
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


# ---------- ЗАДАНИЯ BOTOHUB ----------
def tasks_menu_text():
    enabled = tasks_enabled()
    return (
        f"🎯 <b>Задания (Botohub)</b>\n\n"
        f"Статус: {'🟢 включены' if enabled else '🔴 выключены'}\n\n"
        f"💰 Награда за задание: <b>{get_setting('task_reward')}.00</b> ⭐"
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
    await call.message.answer("💰 Сколько звёзд давать за задание?")
    await state.set_state(TasksEdit.waiting_reward)


@dp.message(TasksEdit.waiting_reward)
async def tasks_save_reward(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        val = int(message.text.strip())
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    set_setting("task_reward", val)
    await state.clear()
    await message.answer(f"✅ Награда: {val}.00 ⭐", reply_markup=back_admin_kb())


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
        await message.answer("🔗 Пришли @username канала или <code>t.me/username</code>",
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
                f"<code>{e}</code>\n\nДобавлю всё равно.",
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
        await message.answer("⚠️ chat_id должен быть числом.")
        return
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
        text += f"#{tid} — {tname} — {title}\n   {link}\n"
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
    await call.message.edit_text(f"📌 <b>Свои ОП (на {title})</b>",
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


# ---------- ЗАЯВКИ (п.7А, 8А) ----------
PAGE_SIZE = 10


def _render_wd_list(page=0):
    count = get_pending_withdrawals_count()
    if count == 0:
        return "📭 Нет активных заявок", back_admin_kb()
    pages = (count + PAGE_SIZE - 1) // PAGE_SIZE
    if page < 0:
        page = 0
    if page >= pages:
        page = pages - 1
    rows = get_pending_withdrawals_page(offset=page * PAGE_SIZE, limit=PAGE_SIZE)
    text = (
        f"📋 <b>Активные заявки</b>\n\n"
        f"Всего: <b>{count}</b> | Страница <b>{page + 1}/{pages}</b>\n\n"
        f"Нажми на заявку, чтобы открыть карточку."
    )
    return text, wd_list_kb(count, page, pages, rows)


@dp.callback_query(F.data == "wd_list")
async def wd_list(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    text, kb = _render_wd_list(0)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")


@dp.callback_query(F.data.startswith("wd_page:"))
async def wd_page(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    try:
        page = int(call.data.split(":")[1])
    except Exception:
        page = 0
    text, kb = _render_wd_list(page)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass
    await call.answer()


@dp.callback_query(F.data == "wd_noop")
async def wd_noop(call: CallbackQuery):
    await call.answer()


@dp.callback_query(F.data.startswith("wd_view:"))
async def wd_view(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    try:
        wid = int(call.data.split(":")[1])
    except Exception:
        await call.answer("Ошибка")
        return
    row = get_withdrawal(wid)
    if not row:
        await call.answer("Не найдена", show_alert=True)
        return
    _, user_id, amount, gift_key, status = row
    name = GIFTS.get(gift_key, ("—", 0))[0]
    u = get_user(user_id)
    uname = f"@{u[1]}" if u and u[1] else "без username"
    status_icon = {"pending": "⏳", "completed": "✅", "rejected": "❌"}.get(status, "•")
    text = (
        f"💸 <b>Заявка #{wid}</b> {status_icon}\n\n"
        f"👤 {uname}\n"
        f"🆔 <code>{user_id}</code>\n"
        f"🎁 {name}\n"
        f"💰 {amount} ⭐\n"
        f"📌 Статус: <b>{status}</b>"
    )
    kb = admin_wd_kb(wid) if status == "pending" else back_admin_kb()
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@dp.callback_query(F.data == "wd_bulk_ok_ask")
async def wd_bulk_ok_ask(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    count = get_pending_withdrawals_count()
    if count == 0:
        await call.answer("Нет заявок", show_alert=True)
        return
    try:
        await call.message.edit_text(
            f"⚠️ <b>Подтверждение</b>\n\n"
            f"Одобрить <b>{count}</b> заявок?\n\n"
            f"Это действие нельзя отменить.",
            reply_markup=wd_bulk_confirm_kb("ok", count), parse_mode="HTML")
    except Exception:
        pass
    await call.answer()


@dp.callback_query(F.data == "wd_bulk_no_ask")
async def wd_bulk_no_ask(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    count = get_pending_withdrawals_count()
    if count == 0:
        await call.answer("Нет заявок", show_alert=True)
        return
    try:
        await call.message.edit_text(
            f"⚠️ <b>Подтверждение</b>\n\n"
            f"Отклонить <b>{count}</b> заявок?\n"
            f"Звёзды вернутся юзерам.",
            reply_markup=wd_bulk_confirm_kb("no", count), parse_mode="HTML")
    except Exception:
        pass
    await call.answer()


@dp.callback_query(F.data == "wd_bulk_ok_do")
async def wd_bulk_ok_do(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    rows = bulk_accept_withdrawals()
    await call.answer(f"✅ Одобрено: {len(rows)}")
    sent = 0
    failed = 0
    for wid, user_id, amount, gift_key in rows:
        name = GIFTS.get(gift_key, ("подарок", 0))[0]
        try:
            await bot.send_message(user_id,
                f"✅ <b>Заявка #{wid} одобрена!</b>\n\n🎁 {name} отправлен тебе.",
                parse_mode="HTML")
            sent += 1
        except Exception as e:
            failed += 1
            es = str(e).lower()
            if "blocked" in es or "chat not found" in es or "user is deactivated" in es:
                try:
                    mark_user_blocked(user_id)
                except Exception:
                    pass
        await asyncio.sleep(0.05)
    await call.message.edit_text(
        f"✅ <b>Готово</b>\n\n"
        f"Одобрено: <b>{len(rows)}</b>\n"
        f"Уведомлений доставлено: <b>{sent}</b>\n"
        f"Не доставлено: <b>{failed}</b>",
        reply_markup=back_admin_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "wd_bulk_no_do")
async def wd_bulk_no_do(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    rows = bulk_reject_withdrawals()
    await call.answer(f"❌ Отклонено: {len(rows)}")
    sent = 0
    for wid, user_id, amount, gift_key in rows:
        try:
            await bot.send_message(user_id, f"❌ Заявка #{wid} отклонена.\n{amount} ⭐ возвращены.")
            sent += 1
        except Exception as e:
            es = str(e).lower()
            if "blocked" in es or "chat not found" in es or "user is deactivated" in es:
                try:
                    mark_user_blocked(user_id)
                except Exception:
                    pass
        await asyncio.sleep(0.05)
    await call.message.edit_text(
        f"❌ <b>Готово</b>\n\n"
        f"Отклонено: <b>{len(rows)}</b>\n"
        f"Уведомлений доставлено: <b>{sent}</b>",
        reply_markup=back_admin_kb(), parse_mode="HTML")


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
    except Exception as e:
        es = str(e).lower()
        if "blocked" in es or "chat not found" in es or "user is deactivated" in es:
            try:
                mark_user_blocked(user_id)
            except Exception:
                pass
    try:
        await call.message.edit_text(
            f"💸 <b>Заявка #{wid}</b> ✅\n\nВЫПОЛНЕНО",
            reply_markup=back_admin_kb(), parse_mode="HTML")
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
        await bot.send_message(user_id, f"❌ Заявка #{wid} отклонена.\n{amount} ⭐ возвращены.")
    except Exception:
        pass
    try:
        await call.message.edit_text(
            f"💸 <b>Заявка #{wid}</b> ❌\n\nОТКЛОНЕНО",
            reply_markup=back_admin_kb(), parse_mode="HTML")
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


# ---------- ПРИВАТКА ----------
@dp.callback_query(F.data == "priv_menu")
async def priv_menu(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    enabled = get_setting("priv_enabled") == "1"
    text = (
        f"🎛 <b>Приватка</b>\n\n"
        f"Статус: {'🟢 включена' if enabled else '🔴 выключена'}\n\n"
        f"<b>Текст:</b>\n{get_setting('priv_text')}\n\n"
        f"<b>Кнопки:</b>\n{get_setting('priv_buttons')}"
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
    set_setting("priv_text", _smart_text(message))
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
    await message.answer(f"👤 @{u[1] or '—'} — баланс: {u[2]} ⭐\n\nПришли сумму (+ или −):")
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
        return
    add_balance(uid, amount)
    new_balance = get_balance(uid)
    await state.clear()
    await message.answer(
        f"✅ {amount:+d} ⭐\n🆔 <code>{uid}</code>\n💰 Баланс: <b>{new_balance}</b> ⭐",
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
    blocked = "🚫 да" if is_user_blocked(uid) else "✅ нет"
    await state.clear()
    await message.answer(
        f"👤 <b>Юзер</b>\n\n🧑 @{u[1] or '—'}\n🆔 <code>{uid}</code>\n"
        f"⭐ Баланс: <b>{balance}</b>\n👥 Друзей: <b>{refs}</b>\n"
        f"⏳ Ожидают: <b>{pending}</b>\n"
        f"🚫 Заблокировал: <b>{blocked}</b>\n"
        f"📅 Регистрация: {reg}",
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
    icons = {"confirmed": "✅", "pending": "⏳", "expired": "❌"}
    for r_uid, r_name, r_date, r_status in rows:
        icon = icons.get(r_status, "•")
        date = (r_date or "")[:10]
        name = f"@{r_name}" if r_name else "аноним"
        text += f"{icon} {name} — <code>{r_uid}</code> — {date}\n"
    if len(text) > 4000:
        text = text[:4000] + "\n...обрезано"
    await call.message.answer(text, parse_mode="HTML")


# ---------- ВИДЕО ВЫВОДА ----------
@dp.callback_query(F.data == "wd_video_menu")
async def wd_video_menu(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    video_id = get_setting("withdraw_video_id")
    status = "✅ загружено" if video_id else "❌ нет"
    await call.message.edit_text(
        f"🎬 <b>Видео вывода</b>\n\n"
        f"Статус: <b>{status}</b>\n\n"
        f"Видео показывается юзеру при нажатии «Вывести звёзды».\n"
        f"Рекомендую 6 секунд.",
        reply_markup=wd_video_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "wd_video_add")
async def wd_video_add(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("🎬 Пришли видео (6 сек):")
    await state.update_data(wd_video=True)
    await state.set_state(BroadcastFlow.waiting_media)


@dp.callback_query(F.data == "wd_video_del")
async def wd_video_del(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    set_setting("withdraw_video_id", "")
    await call.answer("🗑 Убрано")
    try:
        await call.message.edit_text(
            "🎬 <b>Видео вывода</b>\n\nСтатус: <b>❌ нет</b>",
            reply_markup=wd_video_kb(), parse_mode="HTML")
    except Exception:
        pass


# ---------- СТАТИСТИКА (п.9А+Г+Д) ----------
@dp.callback_query(F.data == "stats")
async def stats(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    s = get_stats()
    e = get_extended_stats()
    top_bal = get_top_balance(10)
    top_refs = get_top_refs(10)

    medals = ["🥇", "🥈", "🥉"]
    bal_lines = ""
    for i, (uid, uname, bal) in enumerate(top_bal, 1):
        prefix = medals[i - 1] if i <= 3 else f"{i}."
        name = f"@{uname}" if uname else f"ID{uid}"
        bal_lines += f"{prefix} {name} — <b>{bal}</b> ⭐\n"

    ref_lines = ""
    for i, (uid, uname, refs) in enumerate(top_refs, 1):
        prefix = medals[i - 1] if i <= 3 else f"{i}."
        name = f"@{uname}" if uname else f"ID{uid}"
        ref_lines += f"{prefix} {name} — <b>{refs}</b> 👥\n"

    text = (
        f"📊 <b>РАСШИРЕННАЯ СТАТИСТИКА</b>\n\n"

        f"👥 <b>Пользователи:</b>\n"
        f"   Всего: <b>{e['total']}</b>\n"
        f"   Новых за 7 дней: <b>{e['new_7d']}</b>\n"
        f"   Новых за 30 дней: <b>{e['new_30d']}</b>\n"
        f"   Пришли по реф-ссылке: <b>{e['with_ref']}</b>\n"
        f"   Активных за 24ч: <b>{e['active_24h']}</b>\n"
        f"   🚫 Заблокировали бота: <b>{e['blocked']}</b>\n\n"

        f"💰 <b>Баланс и звёзды:</b>\n"
        f"   Общий баланс: <b>{s['total_balance']}</b> ⭐\n"
        f"   Средний баланс: <b>{e['avg_balance']}</b> ⭐\n"
        f"   Выведено звёзд: <b>{e['total_withdrawn_stars']}</b> ⭐\n"
        f"   В ожидании: <b>{e['pending_stars']}</b> ⭐\n\n"

        f"👥 <b>Рефералы:</b>\n"
        f"   Подтверждённых: <b>{e['confirmed_refs']}</b>\n\n"

        f"🎯 <b>Активность:</b>\n"
        f"   ОП пройдено: <b>{e['ops_passed']}</b>\n"
        f"   Своих заданий сделано: <b>{e['ctasks_done']}</b>\n\n"

        f"📋 <b>Заявки:</b>\n"
        f"   ⏳ В ожидании: <b>{s['pending']}</b>\n"
        f"   ✅ Выполнено: <b>{s['done']}</b>\n"
        f"   ❌ Отклонено: <b>{s['rejected']}</b>\n\n"

        f"🏆 <b>Топ-10 по балансу:</b>\n{bal_lines or '   —'}\n"
        f"👥 <b>Топ-10 по рефералам:</b>\n{ref_lines or '   —'}"
    )
    if len(text) > 4000:
        text = text[:4000] + "\n...обрезано"
    try:
        await call.message.edit_text(text, reply_markup=stats_kb(), parse_mode="HTML")
    except Exception:
        await call.message.answer(text, parse_mode="HTML")


# ---------- НАСТРОЙКИ ----------
@dp.callback_query(F.data == "settings")
async def settings(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text(
        f"⚙️ <b>НАСТРОЙКИ</b>\n\n"
        f"👥 Бонус за реферала: <b>{get_setting('ref_bonus')}</b> ⭐\n"
        f"🎁 Ежедневный бонус: <b>{get_setting('daily_bonus')}</b> ⭐\n"
        f"💸 Минимум вывода: <b>{get_setting('min_withdraw')}</b> ⭐\n"
        f"🎉 Бонус за /start: <b>{get_setting('welcome_bonus')}</b> ⭐\n"
        f"👥 Друзей для вывода: <b>{get_setting('withdraw_friends_required')}</b>\n"
        f"✏️ Текст под меню: {get_setting('welcome_text')}",
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
        "welcome_bonus": "🎉 Бонус за /start (число):",
        "withdraw_friends_required": "👥 Сколько друзей нужно для вывода?",
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
    if key in ("ref_bonus", "daily_bonus", "min_withdraw",
               "welcome_bonus", "withdraw_friends_required"):
        try:
            int(value)
        except Exception:
            await message.answer("⚠️ Нужно число.")
            return
    set_setting(key, value)
    await state.clear()
    await message.answer(f"✅ Сохранено: {key}", reply_markup=back_admin_kb())


# ---------- ПРОМОКОДЫ ----------
@dp.callback_query(F.data == "promos")
async def promos(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text("🎟 <b>Промокоды</b>", reply_markup=promos_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "promo_create")
async def promo_create(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer(
        "🎟 <b>Выбери тип промокода:</b>\n\n"
        "💫 <b>Обычный</b> — юзер получает звёзды сразу (без ОП)\n"
        "📢 <b>За ОП</b> — юзер подписывается на спонсоров и получает звёзды",
        reply_markup=promo_type_kb(), parse_mode="HTML")


@dp.callback_query(F.data.startswith("pcreate_type:"))
async def pcreate_type(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    p_type = call.data.split(":")[1]
    await state.update_data(p_type=p_type)
    try:
        await call.message.edit_text(
            f"Тип: <b>{'За ОП' if p_type == 'op' else 'Обычный'}</b>\n\n🎟 Название промокода:",
            parse_mode="HTML")
    except Exception:
        await call.message.answer(f"🎟 Название промокода (тип {p_type}):")
    await state.set_state(PromoCreate.waiting_code)
    await call.answer()


@dp.message(PromoCreate.waiting_code)
async def promo_code_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    code = message.text.strip().upper()
    if not code.isalnum() or len(code) < 3:
        await message.answer("⚠️ Только буквы/цифры, минимум 3.")
        return
    await state.update_data(code=code)
    data = await state.get_data()
    p_type = data.get("p_type", "normal")
    if p_type == "op":
        await message.answer(f"Код: <b>{code}</b>\n\nМаксимальная сумма (⭐):", parse_mode="HTML")
    else:
        await message.answer(f"Код: <b>{code}</b>\n\nСколько звёзд?", parse_mode="HTML")
    await state.set_state(PromoCreate.waiting_amount)


@dp.message(PromoCreate.waiting_amount)
async def promo_amount_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        amount = int(message.text.strip())
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    await state.update_data(amount=amount)
    data = await state.get_data()
    p_type = data.get("p_type", "normal")
    if p_type == "op":
        await message.answer(
            f"Максимум: <b>{amount}</b> ⭐\n\n"
            f"Минимум (для рандома, например 30 → 30-{amount}):\n"
            f"Если не хочешь рандом — пришли {amount}.",
            parse_mode="HTML")
        await state.set_state(PromoCreate.waiting_amount_min)
    else:
        await message.answer(f"Звёзд: <b>{amount}</b>\n\nСколько активаций?", parse_mode="HTML")
        await state.set_state(PromoCreate.waiting_uses)


@dp.message(PromoCreate.waiting_amount_min)
async def promo_amount_min_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        amount_min = int(message.text.strip())
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    await state.update_data(amount_min=amount_min)
    await message.answer("Сколько активаций?")
    await state.set_state(PromoCreate.waiting_uses)


@dp.message(PromoCreate.waiting_uses)
async def promo_uses_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        uses = int(message.text.strip())
    except Exception:
        await message.answer("⚠️ Нужно число.")
        return
    await state.update_data(uses=uses)
    data = await state.get_data()
    p_type = data.get("p_type", "normal")

    if p_type == "op":
        all_ops = await _collect_all_op_keys()
        if not all_ops:
            await message.answer("⚠️ Нет ни Botohub, ни своих ОП для выбора.")
            await state.clear()
            return
        selected = set()
        await state.update_data(selected_ops=list(selected))
        await message.answer(
            "📢 Отметь спонсоров (галочками):",
            reply_markup=promo_op_select_kb(all_ops, selected, data["code"]))
        await state.set_state(PromoCreate.waiting_op_select)
        return

    create_promo(data["code"], data["amount"], uses, p_type="normal")
    await state.clear()
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=promo_{data['code']}"
    await message.answer(
        f"✅ <b>Промокод</b> <code>{data['code']}</code> <b>создан!</b>\n\n"
        f"💫 Тип: обычный (без ОП)\n"
        f"💰 Сумма: <b>{data['amount']} ⭐</b>\n"
        f"🎯 Активаций: <b>{uses}</b>\n\n"
        f"🔗 <b>Ссылка для юзеров:</b>\n"
        f"<code>{link}</code>\n\n"
        f"Юзер жмёт → сразу получает <b>{data['amount']} ⭐</b> без ОП.",
        parse_mode="HTML")


async def _collect_all_op_keys():
    items = []
    if bh_enabled() and BOTOHUB_TOKEN:
        try:
            count = int(get_setting("botohub_entry_count") or 2)
        except Exception:
            count = 2
        data = await bh_get_tasks(ADMIN_ID, count)
        for t in data.get("tasks", []):
            url = t.get("url")
            if url:
                op_key = f"bh:{url}"
                items.append((op_key, f"Botohub: {url[:40]}"))
    for cid, title, link in list_custom_ops("entry"):
        op_key = f"custom:{cid}"
        items.append((op_key, f"Свой: {title}"))
    return items


@dp.callback_query(F.data.startswith("pcreate_toggle:"), PromoCreate.waiting_op_select)
async def pcreate_toggle(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    parts = call.data.split(":", 2)
    if len(parts) != 3:
        await call.answer()
        return
    _, code, op_key = parts
    data = await state.get_data()
    selected = set(data.get("selected_ops", []))
    if op_key in selected:
        selected.discard(op_key)
    else:
        selected.add(op_key)
    await state.update_data(selected_ops=list(selected))
    all_ops = await _collect_all_op_keys()
    try:
        await call.message.edit_reply_markup(
            reply_markup=promo_op_select_kb(all_ops, selected, code))
    except Exception:
        pass
    await call.answer()


@dp.callback_query(F.data.startswith("pcreate_done:"), PromoCreate.waiting_op_select)
async def pcreate_done(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    code = call.data.split(":", 1)[1]
    data = await state.get_data()
    selected = list(data.get("selected_ops", []))
    if not selected:
        await call.answer("⚠️ Выбери хотя бы одного спонсора", show_alert=True)
        return
    amount = data.get("amount", 0)
    amount_min = data.get("amount_min", amount)
    uses = data.get("uses", 1)
    create_promo(code, amount, uses, p_type="op", amount_min=amount_min, op_keys=selected)
    await state.clear()
    await call.answer("✅ Создан")
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=promo_{code}"
    try:
        await call.message.edit_text(
            f"✅ <b>Промокод</b> <code>{code}</code> <b>создан!</b>\n\n"
            f"📢 Тип: за ОП\n"
            f"💰 Сумма: <b>{amount_min}-{amount} ⭐</b>\n"
            f"🎯 Активаций: <b>{uses}</b>\n"
            f"🔗 <b>Ссылка:</b>\n"
            f"<code>{link}</code>",
            parse_mode="HTML")
    except Exception:
        await call.message.answer(f"✅ Промокод <code>{code}</code> создан", parse_mode="HTML")


@dp.callback_query(F.data == "promo_list")
async def promo_list_cb(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    rows = list_promos()
    if not rows:
        await call.answer("Пусто", show_alert=True)
        return
    await call.message.edit_text(
        "📜 <b>Промокоды</b>\n\nНажми на промокод, чтобы увидеть статистику:",
        reply_markup=promo_list_kb(rows), parse_mode="HTML")


@dp.callback_query(F.data.startswith("promo_view:"))
async def promo_view_cb(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    code = call.data.split(":", 1)[1]
    promo = get_promo(code)
    if not promo:
        await call.answer("Не найден", show_alert=True)
        return
    c, amount, mx, used, active, p_type, amount_min = promo
    uses_list = get_promo_uses_list(code, 10)

    if p_type == "op":
        type_line = "📢 Тип: за ОП"
        sum_line = f"{amount_min}-{amount} ⭐"
    else:
        type_line = "💫 Тип: обычный"
        sum_line = f"{amount} ⭐"

    if p_type == "op":
        avg = (amount + amount_min) // 2 if amount_min else amount
        total_given = used * avg
    else:
        total_given = used * amount

    text = (
        f"📊 <b>Промокод</b> <code>{code}</code>\n\n"
        f"{type_line}\n"
        f"💰 Сумма: <b>{sum_line}</b>\n"
        f"🎯 Активаций: <b>{used} / {mx}</b>\n"
        f"⭐ Выдано звёзд: <b>{total_given}</b>\n\n"
    )
    if uses_list:
        text += "<b>Последние активации:</b>\n"
        for uid, uname, used_at in uses_list:
            name = f"@{uname}" if uname else f"ID {uid}"
            date = (used_at or "")[:16].replace("T", " ")
            text += f"• {name} — {date}\n"
    else:
        text += "<i>Ещё никто не активировал.</i>"
    if len(text) > 4000:
        text = text[:4000] + "\n...обрезано"

    try:
        await call.message.edit_text(text, reply_markup=promo_view_kb(code), parse_mode="HTML")
    except Exception:
        await call.message.answer(text, parse_mode="HTML")


@dp.callback_query(F.data.startswith("promo_del_confirm:"))
async def promo_del_confirm(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    code = call.data.split(":", 1)[1]
    delete_promo(code)
    await call.answer(f"🗑 {code} удалён")
    rows = list_promos()
    if not rows:
        try:
            await call.message.edit_text("📜 <b>Список пуст</b>",
                                          reply_markup=promos_kb(), parse_mode="HTML")
        except Exception:
            pass
        return
    try:
        await call.message.edit_text(
            "📜 <b>Промокоды</b>\n\nНажми на промокод, чтобы увидеть статистику:",
            reply_markup=promo_list_kb(rows), parse_mode="HTML")
    except Exception:
        pass


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


# ---------- РЕКЛАМА ----------
@dp.callback_query(F.data == "ad_menu")
async def ad_menu(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text(
        "📊 <b>Реклама</b>\n\n"
        "Создай метку, дай рекламодателю ссылку <code>?start=ad_КОД</code>.\n"
        "Он сможет смотреть статистику командой <code>/stat_КОД</code>.",
        reply_markup=ad_menu_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "ad_add")
async def ad_add(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer(
        "📝 Пришли код метки (латиница, цифры, _), например: <code>nikita</code>",
        parse_mode="HTML")
    await state.set_state(AdAdd.waiting_code)


@dp.message(AdAdd.waiting_code)
async def ad_code_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    code = message.text.strip().lower()
    if not code.replace("_", "").isalnum() or len(code) < 3:
        await message.answer("⚠️ Только латиница/цифры/_, минимум 3.")
        return
    if get_ad_source(code):
        await message.answer("⚠️ Такая метка уже есть.")
        return
    await state.update_data(ad_code=code)
    await message.answer(
        "👤 Пришли <code>@username</code> или <code>user_id</code> рекламодателя:",
        parse_mode="HTML")
    await state.set_state(AdAdd.waiting_owner)


@dp.message(AdAdd.waiting_owner)
async def ad_owner_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    raw = message.text.strip()
    owner_id = None
    owner_username = ""
    if raw.lstrip("-").isdigit():
        owner_id = int(raw)
        u = get_user(owner_id)
        if u and u[1]:
            owner_username = u[1]
    elif raw.startswith("@"):
        uname = raw[1:]
        import sqlite3
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE username = ?", (uname,))
        r = cur.fetchone()
        conn.close()
        if not r:
            await message.answer("⚠️ Юзер с таким @username не найден.")
            return
        owner_id = r[0]
        owner_username = uname
    else:
        await message.answer("⚠️ Пришли @username или user_id.")
        return

    await state.update_data(ad_owner_id=owner_id, ad_owner_username=owner_username)
    await message.answer("💰 Цена за переход в рублях (целое число, 0 если не надо):")
    await state.set_state(AdAdd.waiting_price)


@dp.message(AdAdd.waiting_price)
async def ad_price_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        price = int(message.text.strip())
        if price < 0:
            raise ValueError
    except Exception:
        await message.answer("⚠️ Нужно число ≥ 0.")
        return

    data = await state.get_data()
    code = data.get("ad_code")
    owner_id = data.get("ad_owner_id")
    owner_username = data.get("ad_owner_username", "")

    add_ad_source(code, owner_id, owner_username, price_per_click=price)
    await state.clear()

    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ad_{code}"
    await message.answer(
        f"✅ Метка <code>{code}</code> создана.\n\n"
        f"👤 Владелец: <code>{owner_id}</code> (@{owner_username or '—'})\n"
        f"💰 Цена перехода: <b>{price}</b> ₽\n"
        f"🔗 Ссылка: <code>{link}</code>\n\n"
        f"Пусть рекламодатель зайдёт и напишет <code>/stat_{code}</code>",
        parse_mode="HTML")


@dp.callback_query(F.data == "ad_list")
async def ad_list(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    rows = list_ad_sources()
    if not rows:
        await call.answer("Пусто", show_alert=True)
        return
    me = await bot.get_me()
    text = "📜 <b>Метки</b>\n\n"
    for row in rows:
        code = row[0]
        owner_id = row[1]
        owner_username = row[2]
        price = row[5] if len(row) > 5 else 0
        link = f"https://t.me/{me.username}?start=ad_{code}"
        text += (f"<code>{code}</code> — <code>{owner_id}</code> (@{owner_username or '—'}) — "
                 f"<b>{price}</b> ₽\n{link}\n\n")
    if len(text) > 4000:
        text = text[:4000] + "\n...обрезано"
    await call.message.answer(text, parse_mode="HTML")


@dp.callback_query(F.data == "ad_del")
async def ad_del_cb(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("🗑 Пришли код метки для удаления:")
    await state.set_state(AdDel.waiting_code)


@dp.message(AdDel.waiting_code)
async def ad_del_step(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    code = message.text.strip().lower()
    if not get_ad_source(code):
        await message.answer("⚠️ Нет такой.")
        return
    delete_ad_source(code)
    await state.clear()
    await message.answer(f"🗑 Удалено <code>{code}</code>", parse_mode="HTML")
  # ---------- РАССЫЛКА (п.6Г) ----------
BROADCAST_STATE = {}


def _get_broadcast_state():
    return BROADCAST_STATE.setdefault(ADMIN_ID, {})


def _media_label(b):
    mt = b.get("media_type")
    if mt == "photo":
        return "🖼 фото"
    if mt == "video":
        return "🎬 видео"
    if mt == "animation":
        return "🎞 GIF"
    if mt == "sticker":
        return "🎨 стикер"
    return "нет"


def broadcast_menu_text():
    b = _get_broadcast_state()
    count = b.get("count") or get_setting("broadcast_batch_default") or "всем"
    btns = "есть" if b.get("buttons") else "нет"
    text_prev = (b.get("text") or "—")[:60]
    return (
        f"📢 <b>Рассылка</b>\n\n"
        f"📝 Текст: {text_prev}...\n"
        f"📎 Медиа: <b>{_media_label(b)}</b>\n"
        f"🔗 Кнопки: <b>{btns}</b>\n"
        f"👥 Количество: <b>{count}</b>\n\n"
        f"⚠️ Стикер уйдёт отдельным сообщением без текста и кнопок."
    )


@dp.callback_query(F.data == "broadcast_menu")
async def broadcast_menu(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await state.clear()
    try:
        await call.message.edit_text(broadcast_menu_text(),
                                      reply_markup=broadcast_menu_kb(), parse_mode="HTML")
    except Exception:
        await call.message.answer(broadcast_menu_text(),
                                  reply_markup=broadcast_menu_kb(), parse_mode="HTML")


@dp.callback_query(F.data == "bc_edit_text")
async def bc_edit_text(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer("✏️ Пришли текст рассылки:")
    await state.set_state(BroadcastFlow.waiting_text)


@dp.message(BroadcastFlow.waiting_text)
async def bc_save_text(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    _get_broadcast_state()["text"] = _smart_text(message)
    await state.clear()
    await message.answer("✅ Текст сохранён", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "bc_edit_media")
async def bc_edit_media(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer(
        "📎 Пришли медиа:\n\n"
        "🖼 фото\n🎬 видео\n🎞 GIF\n🎨 стикер\n\n"
        "Первое сообщение — то, что пойдёт в рассылку.",
        parse_mode="HTML")
    await state.update_data(bc_media=True)
    await state.set_state(BroadcastFlow.waiting_media)


@dp.message(BroadcastFlow.waiting_media)
async def bc_save_media(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()

    # сценарий 1: загрузка видео вывода (wd_video_add)
    if data.get("wd_video"):
        if not message.video:
            await message.answer("⚠️ Нужно именно видео.")
            return
        set_setting("withdraw_video_id", message.video.file_id)
        await state.clear()
        await message.answer("✅ Видео сохранено", reply_markup=back_admin_kb())
        return

    # сценарий 2: медиа для рассылки
    b = _get_broadcast_state()
    if message.photo:
        b["media_type"] = "photo"
        b["media_id"] = message.photo[-1].file_id
    elif message.video:
        b["media_type"] = "video"
        b["media_id"] = message.video.file_id
    elif message.animation:
        b["media_type"] = "animation"
        b["media_id"] = message.animation.file_id
    elif message.sticker:
        b["media_type"] = "sticker"
        b["media_id"] = message.sticker.file_id
    else:
        await message.answer("⚠️ Нужно фото, видео, GIF или стикер.")
        return
    await state.clear()
    await message.answer(f"✅ Сохранено: {_media_label(b)}", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "bc_del_photo")
async def bc_del_photo(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    b = _get_broadcast_state()
    b.pop("media_id", None)
    b.pop("media_type", None)
    await call.answer("🗑 Убрано")
    try:
        await call.message.edit_text(broadcast_menu_text(),
                                      reply_markup=broadcast_menu_kb(), parse_mode="HTML")
    except Exception:
        pass


@dp.callback_query(F.data == "bc_edit_buttons")
async def bc_edit_buttons(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.answer(
        "🔗 Пришли кнопки (по одной в строке, или через & для ряда):\n\n"
        "<code>Кнопка - https://t.me/xxx - 5258057130228849960</code>\n"
        "Третий параметр (ID эмодзи) — опционально.\n\n"
        "Очистить — пришли <code>-</code>",
        parse_mode="HTML")
    await state.set_state(BroadcastFlow.waiting_buttons)


@dp.message(BroadcastFlow.waiting_buttons)
async def bc_save_buttons(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.strip()
    if text == "-":
        _get_broadcast_state().pop("buttons", None)
        await state.clear()
        await message.answer("🗑 Очищено", reply_markup=back_admin_kb())
        return
    _get_broadcast_state()["buttons"] = text
    await state.clear()
    await message.answer("✅ Кнопки сохранены", reply_markup=back_admin_kb())


@dp.callback_query(F.data == "bc_edit_count")
async def bc_edit_count(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    users = get_all_user_ids()
    await call.message.answer(
        f"👥 Сколько отправить? Всего: <b>{len(users)}</b>\n\n"
        f"Пришли число (например 10000) или <code>all</code> — всем.",
        parse_mode="HTML")
    await state.set_state(BroadcastFlow.waiting_count)


@dp.message(BroadcastFlow.waiting_count)
async def bc_save_count(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    raw = message.text.strip().lower()
    if raw == "all":
        _get_broadcast_state()["count"] = 0
        await state.clear()
        await message.answer("✅ Всем", reply_markup=back_admin_kb())
        return
    try:
        val = int(raw)
        if val < 1:
            raise ValueError
    except Exception:
        await message.answer("⚠️ Нужно число или all.")
        return
    _get_broadcast_state()["count"] = val
    await state.clear()
    await message.answer(f"✅ Отправить {val}", reply_markup=back_admin_kb())


def _build_bc_kb():
    raw = _get_broadcast_state().get("buttons")
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
            parts = [p.strip() for p in pair.split(" - ")]
            if len(parts) < 2:
                continue
            text = parts[0]
            url = parts[1]
            emoji_id = parts[2] if len(parts) >= 3 else ""
            if not text or not url:
                continue
            if emoji_id:
                row.append(InlineKeyboardButton(text=text, url=url,
                                                icon_custom_emoji_id=emoji_id))
            else:
                row.append(InlineKeyboardButton(text=text, url=url))
        if row:
            rows.append(row)
    if not rows:
        return None
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_bc_to_user(uid, b, kb):
    """
    Отправляет одно сообщение рассылки юзеру uid.
    Возвращает True если успех, 'blocked' если заблокирован, False если другая ошибка.
    """
    text = b.get("text") or ""
    mt = b.get("media_type")
    mid = b.get("media_id")

    try:
        if not mt:
            await bot.send_message(uid, text, reply_markup=kb, parse_mode="HTML")
            return True

        if mt == "photo":
            await bot.send_photo(uid, mid, caption=text, reply_markup=kb, parse_mode="HTML")
            return True
        if mt == "video":
            await bot.send_video(uid, mid, caption=text, reply_markup=kb, parse_mode="HTML")
            return True
        if mt == "animation":
            await bot.send_animation(uid, mid, caption=text, reply_markup=kb, parse_mode="HTML")
            return True
        if mt == "sticker":
            # стикер без caption — текст отдельным сообщением
            await bot.send_sticker(uid, mid)
            if text:
                await bot.send_message(uid, text, reply_markup=kb, parse_mode="HTML")
            return True
    except Exception as e:
        es = str(e).lower()
        if "blocked" in es or "chat not found" in es or "user is deactivated" in es:
            return "blocked"
        # пробуем fallback без parse_mode
        if "parse entities" in es or "unclosed" in es or "can't parse" in es:
            try:
                if not mt:
                    await bot.send_message(uid, text, reply_markup=kb)
                elif mt == "photo":
                    await bot.send_photo(uid, mid, caption=text, reply_markup=kb)
                elif mt == "video":
                    await bot.send_video(uid, mid, caption=text, reply_markup=kb)
                elif mt == "animation":
                    await bot.send_animation(uid, mid, caption=text, reply_markup=kb)
                elif mt == "sticker":
                    await bot.send_sticker(uid, mid)
                    if text:
                        await bot.send_message(uid, text, reply_markup=kb)
                return True
            except Exception as e2:
                es2 = str(e2).lower()
                if "blocked" in es2 or "chat not found" in es2 or "user is deactivated" in es2:
                    return "blocked"
                return False
        return False
    return False


@dp.callback_query(F.data == "bc_preview")
async def bc_preview(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    b = _get_broadcast_state()
    text = b.get("text")
    mt = b.get("media_type")
    mid = b.get("media_id")
    if not text and not mt:
        await call.answer("Нет ни текста, ни медиа", show_alert=True)
        return
    kb = _build_bc_kb()
    try:
        if not mt:
            await call.message.answer(text or "—", reply_markup=kb, parse_mode="HTML")
        elif mt == "photo":
            await call.message.answer_photo(mid, caption=text or "", reply_markup=kb, parse_mode="HTML")
        elif mt == "video":
            await call.message.answer_video(mid, caption=text or "", reply_markup=kb, parse_mode="HTML")
        elif mt == "animation":
            await call.message.answer_animation(mid, caption=text or "", reply_markup=kb, parse_mode="HTML")
        elif mt == "sticker":
            await call.message.answer_sticker(mid)
            if text:
                await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
    except Exception as e:
        await call.message.answer(f"⚠️ Ошибка парсинга: {e}\n\nПоказываю без форматирования.")
        try:
            if not mt:
                await call.message.answer(text or "—", reply_markup=kb)
            elif mt == "photo":
                await call.message.answer_photo(mid, caption=text or "", reply_markup=kb)
            elif mt == "video":
                await call.message.answer_video(mid, caption=text or "", reply_markup=kb)
            elif mt == "animation":
                await call.message.answer_animation(mid, caption=text or "", reply_markup=kb)
            elif mt == "sticker":
                await call.message.answer_sticker(mid)
                if text:
                    await call.message.answer(text, reply_markup=kb)
        except Exception as e2:
            await call.message.answer(f"❌ {e2}")
    await call.message.answer("👁 Предпросмотр готов.", reply_markup=broadcast_preview_kb())


@dp.callback_query(F.data == "bc_send")
async def bc_send(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    b = _get_broadcast_state()
    if not b.get("text") and not b.get("media_id"):
        await call.answer("Нет ни текста, ни медиа", show_alert=True)
        return
    await call.message.edit_text(
        "📢 Проверь предпросмотр выше и нажми кнопку:",
        reply_markup=broadcast_confirm_kb())


@dp.callback_query(F.data == "bc_start")
async def bc_start(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    b = _get_broadcast_state()
    if not b.get("text") and not b.get("media_id"):
        await call.answer("Нет ни текста, ни медиа", show_alert=True)
        return
    count = b.get("count") or 0
    kb = _build_bc_kb()

    users = get_all_user_ids()
    if count and count < len(users):
        users = users[:count]

    total = len(users)
    await call.message.edit_text(f"📢 Начинаю... (0/{total})")

    sent = 0
    errors = 0
    blocked = 0
    for i, uid in enumerate(users, 1):
        res = await _send_bc_to_user(uid, b, kb)
        if res is True:
            sent += 1
        elif res == "blocked":
            blocked += 1
            try:
                mark_user_blocked(uid)
                mark_ad_user_blocked(uid)
            except Exception:
                pass
        else:
            errors += 1
        if i % 30 == 0:
            try:
                await call.message.edit_text(f"📢 Рассылка... ({i}/{total})")
            except Exception:
                pass
        await asyncio.sleep(0.05)

    try:
        await call.message.edit_text(
            f"✅ Готово!\n\n"
            f"📤 Отправлено: <b>{sent}</b>\n"
            f"🚫 Заблокировали: <b>{blocked}</b>\n"
            f"❌ Ошибок: <b>{errors}</b>",
            parse_mode="HTML",
            reply_markup=back_admin_kb())
    except Exception:
        pass
    BROADCAST_STATE[ADMIN_ID] = {}


# ---------- БЭКАП ----------
@dp.callback_query(F.data == "backup_help")
async def backup_help(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text(
        "📦 <b>Бэкап</b>\n\n"
        "📤 <b>Выгрузка:</b> <code>/backup</code>.\n\n"
        "📥 <b>Загрузка:</b> отправь боту JSON-файл.\n\n"
        "🤖 Авто-бэкап: 8:00 и 20:00.",
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
            f"💫 ОП пройдено: <b>{len(data['user_ops'])}</b>\n"
            f"📊 Меток: <b>{len(data['ad_sources'])}</b>\n"
            f"🎟 Промокодов: <b>{len(data['promos'])}</b>"), parse_mode="HTML")
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


# ================== ФОН: РЕФЕРАЛЬНЫЙ ВОРКЕР ==================
async def referral_watcher():
    while True:
        try:
            for rid, user_id, referrer_id in get_refs_to_remind():
                u = get_user(user_id)
                uname = f"@{u[1]}" if u and u[1] else "друг"
                try:
                    await bot.send_message(referrer_id,
                        f'<tg-emoji emoji-id="5920433463428650761">⌛</tg-emoji> '
                        f'{uname} зашёл по твоей ссылке, но не забрал бонус в разделе «Прочее».',
                        parse_mode="HTML")
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
                            f'<tg-emoji emoji-id="5787192063099408213">🕗</tg-emoji> '
                            f'<b>Прошло {REFERRAL_DAYS} дней.</b>\n'
                            f'Друзья не забрали бонус:\n{lines}',
                            parse_mode="HTML")
                    except Exception:
                        pass
        except Exception as e:
            print("Watcher error:", e)
        await asyncio.sleep(60)


# ================== ФОН: 3 ДРУГА ==================
async def withdraw_watcher():
    while True:
        try:
            import sqlite3
            conn = sqlite3.connect(DB)
            cur = conn.cursor()
            cur.execute("SELECT user_id FROM withdraw_waiting")
            rows = cur.fetchall()
            conn.close()
            for (user_id,) in rows:
                try:
                    await _check_and_fulfill_waiting(user_id)
                except Exception as e:
                    print(f"withdraw_watcher {user_id}: {e}")
        except Exception as e:
            print("withdraw_watcher error:", e)
        await asyncio.sleep(60)


# ================== ФОН: КЭШ ОП ==================
async def op_cache_cleaner():
    """Раз в час чистит протухший кэш ОП (старше 48ч)."""
    while True:
        try:
            clear_expired_op_cache(OP_CACHE_HOURS)
        except Exception as e:
            print("op_cache_cleaner error:", e)
        await asyncio.sleep(3600)


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
                             f"💫 ОП: <b>{len(data['user_ops'])}</b>"),
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
    asyncio.create_task(referral_watcher())
    asyncio.create_task(withdraw_watcher())
    asyncio.create_task(op_cache_cleaner())
    asyncio.create_task(daily_backup())
    print("Бот запущен")
    print(f"BOT_ID: {BOT_ID}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
