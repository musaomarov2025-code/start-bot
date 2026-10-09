import sqlite3
import random
from datetime import datetime, timedelta, date
from config import DB, DEFAULTS, REFERRAL_DAYS, JOIN_REQUEST_HOURS


def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance INTEGER DEFAULT 0, last_bonus TEXT, referrer_id INTEGER, registered_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS referrals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, referrer_id INTEGER, created_at TEXT, reminded INTEGER DEFAULT 0, status TEXT DEFAULT 'pending')""")
    cur.execute("""CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, gift TEXT, status TEXT DEFAULT 'pending', created_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS promos (code TEXT PRIMARY KEY, amount INTEGER, max_uses INTEGER, used INTEGER DEFAULT 0, active INTEGER DEFAULT 1)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS promo_uses (code TEXT, user_id INTEGER, used_at TEXT, PRIMARY KEY (code, user_id))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS custom_ops (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, link TEXT, type TEXT, active INTEGER DEFAULT 1)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS bh_rewards (user_id INTEGER, link TEXT, done_at TEXT, PRIMARY KEY (user_id, link))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS custom_tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, link TEXT, reward INTEGER DEFAULT 10, active INTEGER DEFAULT 1)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS custom_tasks_done (user_id INTEGER, task_id INTEGER, done_at TEXT, PRIMARY KEY (user_id, task_id))""")

    cur.execute("PRAGMA table_info(custom_tasks)")
    cols = {r[1] for r in cur.fetchall()}
    if "check_type" not in cols:
        cur.execute("ALTER TABLE custom_tasks ADD COLUMN check_type TEXT DEFAULT 'bot'")
    if "check_target" not in cols:
        cur.execute("ALTER TABLE custom_tasks ADD COLUMN check_target TEXT DEFAULT ''")

    cur.execute("""CREATE TABLE IF NOT EXISTS user_ops (
        user_id INTEGER,
        op_key TEXT,
        passed_at TEXT,
        PRIMARY KEY (user_id, op_key)
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS op_passed_cache (
        user_id INTEGER,
        op_key TEXT,
        passed_at TEXT,
        PRIMARY KEY (user_id, op_key)
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS ad_sources (
        code TEXT PRIMARY KEY,
        owner_id INTEGER,
        owner_username TEXT,
        created_at TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS ad_users (
        user_id INTEGER PRIMARY KEY,
        code TEXT,
        registered_at TEXT,
        passed_op INTEGER DEFAULT 0,
        passed_op_at TEXT,
        blocked INTEGER DEFAULT 0,
        refs_count INTEGER DEFAULT 0,
        stars_earned INTEGER DEFAULT 0
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS promo_op_reqs (
        code TEXT,
        op_key TEXT,
        PRIMARY KEY (code, op_key)
    )""")

    cur.execute("PRAGMA table_info(promos)")
    cols = {r[1] for r in cur.fetchall()}
    if "p_type" not in cols:
        cur.execute("ALTER TABLE promos ADD COLUMN p_type TEXT DEFAULT 'normal'")
    if "amount_min" not in cols:
        cur.execute("ALTER TABLE promos ADD COLUMN amount_min INTEGER DEFAULT 0")

    cur.execute("PRAGMA table_info(ad_sources)")
    cols = {r[1] for r in cur.fetchall()}
    if "clicks" not in cols:
        cur.execute("ALTER TABLE ad_sources ADD COLUMN clicks INTEGER DEFAULT 0")
    if "price_per_click" not in cols:
        cur.execute("ALTER TABLE ad_sources ADD COLUMN price_per_click INTEGER DEFAULT 0")

    cur.execute("PRAGMA table_info(ad_users)")
    cols = {r[1] for r in cur.fetchall()}
    if "registered" not in cols:
        cur.execute("ALTER TABLE ad_users ADD COLUMN registered INTEGER DEFAULT 0")
    if "is_premium" not in cols:
        cur.execute("ALTER TABLE ad_users ADD COLUMN is_premium INTEGER DEFAULT 0")

    cur.execute("""CREATE TABLE IF NOT EXISTS ad_daily (
        code TEXT,
        date TEXT,
        clicks INTEGER DEFAULT 0,
        users_new INTEGER DEFAULT 0,
        PRIMARY KEY (code, date)
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS withdraw_waiting (
        user_id INTEGER PRIMARY KEY,
        gift_key TEXT,
        friends_base INTEGER DEFAULT 0,
        created_at TEXT
    )""")

    cur.execute("PRAGMA table_info(withdraw_waiting)")
    cols = {r[1] for r in cur.fetchall()}
    if "friends_base" not in cols:
        cur.execute("ALTER TABLE withdraw_waiting ADD COLUMN friends_base INTEGER DEFAULT 0")
    cur.execute("UPDATE withdraw_waiting SET friends_base = 0 WHERE friends_base IS NULL")

    cur.execute("PRAGMA table_info(users)")
    cols = {r[1] for r in cur.fetchall()}
    if "welcome_bonus_paid" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN welcome_bonus_paid INTEGER DEFAULT 0")
        cur.execute("UPDATE users SET welcome_bonus_paid = 1")
    if "blocked" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN blocked INTEGER DEFAULT 0")

    conn.commit()
    conn.close()


# ================== SETTINGS ==================
def get_setting(key):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else DEFAULTS.get(key, "")


def set_setting(key, value):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()


# ================== USERS ==================
def get_user(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row


def add_user(user_id, username, referrer_id=None):
    if get_user(user_id):
        return False
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("INSERT INTO users (user_id, username, referrer_id, registered_at) VALUES (?, ?, ?, ?)",
                (user_id, username, referrer_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return True


def update_username(user_id, username):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
    conn.commit()
    conn.close()


def add_balance(user_id, amount):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()


def get_balance(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0


def get_place(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE balance > (SELECT balance FROM users WHERE user_id = ?)", (user_id,))
    place = cur.fetchone()[0] + 1
    conn.close()
    return place


def can_take_bonus(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT last_bonus FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row or not row[0]:
        return True
    last = datetime.fromisoformat(row[0])
    return datetime.now() - last >= timedelta(hours=24)


def set_bonus_taken(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("UPDATE users SET last_bonus = ? WHERE user_id = ?", (datetime.now().isoformat(), user_id))
    conn.commit()
    conn.close()


def get_all_user_ids():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def is_welcome_bonus_paid(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT welcome_bonus_paid FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return True
    return bool(row[0])


def mark_welcome_bonus_paid(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("UPDATE users SET welcome_bonus_paid = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# ================== BLOCKED ==================
def mark_user_blocked(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("UPDATE users SET blocked = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def is_user_blocked(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT blocked FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return bool(row and row[0])


def get_blocked_count():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE blocked = 1")
    n = cur.fetchone()[0]
    conn.close()
    return n


# ================== REFERRALS ==================
def create_pending_referral(user_id, referrer_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("INSERT INTO referrals (user_id, referrer_id, created_at, status) VALUES (?, ?, ?, 'pending')",
                (user_id, referrer_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_pending_refs_count(referrer_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND status = 'pending'", (referrer_id,))
    n = cur.fetchone()[0]
    conn.close()
    return n


def get_confirmed_refs_count(referrer_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND status = 'confirmed'", (referrer_id,))
    n = cur.fetchone()[0]
    conn.close()
    return n


def get_user_referrals(referrer_id, limit=100):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT r.user_id, u.username, r.created_at, r.status FROM referrals r LEFT JOIN users u ON u.user_id = r.user_id WHERE r.referrer_id = ? ORDER BY r.created_at DESC LIMIT ?",
                (referrer_id, limit))
    rows = cur.fetchall()
    conn.close()
    return rows


def confirm_referral(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, referrer_id FROM referrals WHERE user_id = ? AND status = 'pending' ORDER BY id LIMIT 1", (user_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None
    rid, referrer_id = row
    cur.execute("UPDATE referrals SET status = 'confirmed' WHERE id = ?", (rid,))
    conn.commit()
    conn.close()
    return referrer_id


def expire_old_referrals():
    threshold = (datetime.now() - timedelta(days=REFERRAL_DAYS)).isoformat()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, referrer_id FROM referrals WHERE status = 'pending' AND created_at < ?", (threshold,))
    rows = cur.fetchall()
    for rid, _, _ in rows:
        cur.execute("UPDATE referrals SET status = 'expired' WHERE id = ?", (rid,))
    conn.commit()
    conn.close()
    return [(u, r) for _, u, r in rows]


def get_refs_to_remind():
    from config import REFERRAL_REMIND_MIN
    threshold = (datetime.now() - timedelta(minutes=REFERRAL_REMIND_MIN)).isoformat()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, referrer_id FROM referrals WHERE status = 'pending' AND reminded = 0 AND created_at < ?", (threshold,))
    rows = cur.fetchall()
    conn.close()
    return rows


def mark_reminded(rid):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("UPDATE referrals SET reminded = 1 WHERE id = ?", (rid,))
    conn.commit()
    conn.close()


# ================== WITHDRAWALS ==================
def create_withdrawal(user_id, amount, gift):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("INSERT INTO withdrawals (user_id, amount, gift, created_at) VALUES (?, ?, ?, ?)",
                (user_id, amount, gift, datetime.now().isoformat()))
    wid = cur.lastrowid
    cur.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()
    return wid


def get_withdrawal(wid):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, amount, gift, status FROM withdrawals WHERE id = ?", (wid,))
    row = cur.fetchone()
    conn.close()
    return row


def get_pending_withdrawals():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, amount, gift FROM withdrawals WHERE status = 'pending' ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_pending_withdrawals_count():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'pending'")
    n = cur.fetchone()[0]
    conn.close()
    return n


def get_pending_withdrawals_page(offset=0, limit=10):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, amount, gift FROM withdrawals WHERE status = 'pending' ORDER BY id LIMIT ? OFFSET ?",
                (limit, offset))
    rows = cur.fetchall()
    conn.close()
    return rows


def bulk_accept_withdrawals():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, amount, gift FROM withdrawals WHERE status = 'pending'")
    rows = cur.fetchall()
    if rows:
        cur.execute("UPDATE withdrawals SET status = 'completed' WHERE status = 'pending'")
    conn.commit()
    conn.close()
    return rows


def bulk_reject_withdrawals():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, amount, gift FROM withdrawals WHERE status = 'pending'")
    rows = cur.fetchall()
    for wid, user_id, amount, gift in rows:
        cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    if rows:
        cur.execute("UPDATE withdrawals SET status = 'rejected' WHERE status = 'pending'")
    conn.commit()
    conn.close()
    return rows


def get_withdrawal_history(limit=50):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, amount, gift, status, created_at FROM withdrawals WHERE status != 'pending' ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows


def set_withdrawal_status(wid, status):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("UPDATE withdrawals SET status = ? WHERE id = ?", (status, wid))
    conn.commit()
    conn.close()


# ================== STATS ==================
def get_stats():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users WHERE registered_at LIKE ?", (str(date.today()) + "%",))
    today = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(SUM(balance),0) FROM users")
    total_balance = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM referrals WHERE status = 'confirmed'")
    total_refs = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'pending'")
    pending = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'completed'")
    done = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'rejected'")
    rejected = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status = 'completed'")
    total_stars = cur.fetchone()[0]
    conn.close()
    return {"total": total, "today": today, "total_balance": total_balance,
            "total_refs": total_refs, "pending": pending, "done": done,
            "rejected": rejected, "total_stars": total_stars}


def get_extended_stats():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users WHERE blocked = 1")
    blocked = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM users WHERE registered_at >= ?",
                ((datetime.now() - timedelta(days=7)).isoformat(),))
    new_7d = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM users WHERE registered_at >= ?",
                ((datetime.now() - timedelta(days=30)).isoformat(),))
    new_30d = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0] or 0

    cur.execute("SELECT COALESCE(SUM(balance),0) FROM users")
    total_balance = cur.fetchone()[0] or 0

    avg_balance = round(total_balance / total, 1) if total else 0

    cur.execute("SELECT COUNT(*) FROM users WHERE last_bonus >= ?",
                ((datetime.now() - timedelta(hours=24)).isoformat(),))
    active_24h = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM users WHERE referrer_id IS NOT NULL")
    with_ref = cur.fetchone()[0] or 0

    cur.execute("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status = 'completed'")
    total_withdrawn_stars = cur.fetchone()[0] or 0

    cur.execute("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status = 'pending'")
    pending_stars = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM referrals WHERE status = 'confirmed'")
    confirmed_refs = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM user_ops")
    ops_passed = cur.fetchone()[0] or 0

    cur.execute("SELECT COUNT(*) FROM custom_tasks_done")
    ctasks_done = cur.fetchone()[0] or 0

    conn.close()
    return {
        "blocked": blocked,
        "new_7d": new_7d,
        "new_30d": new_30d,
        "total": total,
        "avg_balance": avg_balance,
        "active_24h": active_24h,
        "with_ref": with_ref,
        "total_withdrawn_stars": total_withdrawn_stars,
        "pending_stars": pending_stars,
        "confirmed_refs": confirmed_refs,
        "ops_passed": ops_passed,
        "ctasks_done": ctasks_done,
    }


def get_top_balance(limit=10):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, balance FROM users ORDER BY balance DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_top_refs(limit=10):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""SELECT u.user_id, u.username, COUNT(r.id) as refs FROM users u LEFT JOIN referrals r ON r.referrer_id = u.user_id AND r.status = 'confirmed' GROUP BY u.user_id HAVING refs > 0 ORDER BY refs DESC LIMIT ?""", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows


# ================== PROMOS ==================
def create_promo(code, amount, max_uses, p_type="normal", amount_min=0, op_keys=None):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO promos (code, amount, max_uses, used, active, p_type, amount_min) "
        "VALUES (?, ?, ?, 0, 1, ?, ?)",
        (code.upper(), amount, max_uses, p_type, amount_min))
    if op_keys:
        for k in op_keys:
            cur.execute("INSERT OR IGNORE INTO promo_op_reqs (code, op_key) VALUES (?, ?)", (code.upper(), k))
    conn.commit()
    conn.close()


def get_promo(code):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT code, amount, max_uses, used, active, p_type, amount_min FROM promos WHERE code = ?", (code.upper(),))
    row = cur.fetchone()
    conn.close()
    return row


def get_promo_op_reqs(code):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT op_key FROM promo_op_reqs WHERE code = ?", (code.upper(),))
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def list_promos():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT code, amount, max_uses, used, active, p_type, amount_min FROM promos ORDER BY code")
    rows = cur.fetchall()
    conn.close()
    return rows


def delete_promo(code):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM promos WHERE code = ?", (code.upper(),))
    cur.execute("DELETE FROM promo_uses WHERE code = ?", (code.upper(),))
    cur.execute("DELETE FROM promo_op_reqs WHERE code = ?", (code.upper(),))
    conn.commit()
    conn.close()


def user_used_promo(code, user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM promo_uses WHERE code = ? AND user_id = ?", (code.upper(), user_id))
    row = cur.fetchone()
    conn.close()
    return row is not None


def get_promo_uses_list(code, limit=10):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""SELECT pu.user_id, u.username, pu.used_at
                   FROM promo_uses pu
                   LEFT JOIN users u ON u.user_id = pu.user_id
                   WHERE pu.code = ?
                   ORDER BY pu.used_at DESC LIMIT ?""",
                (code.upper(), limit))
    rows = cur.fetchall()
    conn.close()
    return rows


def _calc_promo_amount(amount, amount_min, p_type):
    if p_type == "op" and amount_min and amount_min < amount:
        return random.randint(amount_min, amount)
    return amount


def activate_promo(code, user_id):
    code = code.upper()
    promo = get_promo(code)
    if not promo:
        return False, "❌ Такого промокода не существует.", 0, False, []
    c, amount, max_uses, used, active, p_type, amount_min = promo
    if not active:
        return False, "❌ Промокод деактивирован.", 0, False, []
    if used >= max_uses:
        return False, "❌ Промокод больше не действует.", 0, False, []
    if user_used_promo(code, user_id):
        return False, "❌ Ты уже активировал этот промокод.", 0, False, []

    op_keys = get_promo_op_reqs(code)
    if p_type == "op" and op_keys:
        passed = set(get_user_passed_ops(user_id))
        missing = [k for k in op_keys if k not in passed]
        if missing:
            calc = _calc_promo_amount(amount, amount_min, p_type)
            return True, "NEED_OP", calc, True, op_keys

    calc = _calc_promo_amount(amount, amount_min, p_type)
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("INSERT INTO promo_uses (code, user_id, used_at) VALUES (?, ?, ?)",
                (code, user_id, datetime.now().isoformat()))
    cur.execute("UPDATE promos SET used = used + 1 WHERE code = ?", (code,))
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (calc, user_id))
    conn.commit()
    conn.close()
    return True, f"✅ Промокод активирован! +{calc} ⭐", calc, False, []


def activate_promo_after_op(code, user_id):
    code = code.upper()
    promo = get_promo(code)
    if not promo:
        return 0
    c, amount, max_uses, used, active, p_type, amount_min = promo
    if user_used_promo(code, user_id):
        return 0
    calc = _calc_promo_amount(amount, amount_min, p_type)
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("INSERT INTO promo_uses (code, user_id, used_at) VALUES (?, ?, ?)",
                (code, user_id, datetime.now().isoformat()))
    cur.execute("UPDATE promos SET used = used + 1 WHERE code = ?", (code,))
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (calc, user_id))
    conn.commit()
    conn.close()
    return calc


# ================== CUSTOM OPS ==================
def add_custom_op(title, link, op_type):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("INSERT INTO custom_ops (title, link, type, active) VALUES (?, ?, ?, 1)", (title, link, op_type))
    conn.commit()
    conn.close()


def list_custom_ops(op_type):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, title, link FROM custom_ops WHERE type = ? AND active = 1 ORDER BY id", (op_type,))
    rows = cur.fetchall()
    conn.close()
    return rows


def delete_custom_op(op_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM custom_ops WHERE id = ?", (op_id,))
    conn.commit()
    conn.close()


# ================== BH REWARDS ==================
def bh_reward_mark(user_id, link):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO bh_rewards (user_id, link, done_at) VALUES (?, ?, ?)",
                (user_id, link, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def bh_reward_was_given(user_id, link):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM bh_rewards WHERE user_id = ? AND link = ?", (user_id, link))
    row = cur.fetchone()
    conn.close()
    return row is not None


# ================== CUSTOM TASKS ==================
def add_custom_task(title, link, check_type="bot", check_target=""):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO custom_tasks (title, link, reward, active, check_type, check_target) "
        "VALUES (?, ?, 0, 1, ?, ?)",
        (title, link, check_type, check_target))
    conn.commit()
    conn.close()


def list_custom_tasks():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, title, link, reward, active, check_type, check_target FROM custom_tasks ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_custom_task(task_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, title, link, reward, active, check_type, check_target FROM custom_tasks WHERE id = ?", (task_id,))
    row = cur.fetchone()
    conn.close()
    return row


def delete_custom_task(task_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM custom_tasks WHERE id = ?", (task_id,))
    cur.execute("DELETE FROM custom_tasks_done WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()


def get_next_custom_task(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, title, link, reward, check_type, check_target FROM custom_tasks "
        "WHERE active = 1 AND id NOT IN "
        "(SELECT task_id FROM custom_tasks_done WHERE user_id = ?) ORDER BY id LIMIT 1",
        (user_id,))
    row = cur.fetchone()
    conn.close()
    return row


def mark_custom_task_done(user_id, task_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO custom_tasks_done (user_id, task_id, done_at) VALUES (?, ?, ?)",
                (user_id, task_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()


# ================== USER OPS ==================
def mark_op_passed(user_id, op_key):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO user_ops (user_id, op_key, passed_at) VALUES (?, ?, ?)",
                (user_id, op_key, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_user_passed_ops(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT op_key FROM user_ops WHERE user_id = ?", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def has_op_passed(user_id, op_key):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM user_ops WHERE user_id = ? AND op_key = ?", (user_id, op_key))
    row = cur.fetchone()
    conn.close()
    return row is not None


# ================== OP CACHE 48H ==================
def mark_op_passed_cached(user_id, op_key):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO op_passed_cache (user_id, op_key, passed_at) VALUES (?, ?, ?)",
                (user_id, op_key, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_cached_op_keys(user_id, hours=48):
    threshold = (datetime.now() - timedelta(hours=hours)).isoformat()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT op_key FROM op_passed_cache WHERE user_id = ? AND passed_at >= ?",
                (user_id, threshold))
    rows = cur.fetchall()
    conn.close()
    return {r[0] for r in rows}


def clear_expired_op_cache(hours=48):
    threshold = (datetime.now() - timedelta(hours=hours)).isoformat()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM op_passed_cache WHERE passed_at < ?", (threshold,))
    conn.commit()
    conn.close()


# ================== AD SOURCES ==================
def add_ad_source(code, owner_id, owner_username="", price_per_click=0):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO ad_sources (code, owner_id, owner_username, created_at, price_per_click) VALUES (?, ?, ?, ?, ?)",
                (code.lower(), owner_id, owner_username or "", datetime.now().isoformat(), price_per_click))
    conn.commit()
    conn.close()


def get_ad_source(code):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT code, owner_id, owner_username, created_at, clicks, price_per_click FROM ad_sources WHERE code = ?", (code.lower(),))
    row = cur.fetchone()
    conn.close()
    return row


def list_ad_sources():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT code, owner_id, owner_username, created_at, clicks, price_per_click FROM ad_sources ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return rows


def delete_ad_source(code):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM ad_sources WHERE code = ?", (code.lower(),))
    cur.execute("DELETE FROM ad_users WHERE code = ?", (code.lower(),))
    cur.execute("DELETE FROM ad_daily WHERE code = ?", (code.lower(),))
    conn.commit()
    conn.close()


def increment_ad_click(code, is_new_user):
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("UPDATE ad_sources SET clicks = clicks + 1 WHERE code = ?", (code.lower(),))
    cur.execute("INSERT OR IGNORE INTO ad_daily (code, date, clicks, users_new) VALUES (?, ?, 0, 0)",
                (code.lower(), today))
    cur.execute("UPDATE ad_daily SET clicks = clicks + 1 WHERE code = ? AND date = ?",
                (code.lower(), today))
    if is_new_user:
        cur.execute("UPDATE ad_daily SET users_new = users_new + 1 WHERE code = ? AND date = ?",
                    (code.lower(), today))
    conn.commit()
    conn.close()


def mark_ad_user(user_id, code, registered=0, is_premium=0):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO ad_users (user_id, code, registered_at, registered, is_premium) VALUES (?, ?, ?, ?, ?)",
                (user_id, code.lower(), datetime.now().isoformat(), registered, is_premium))
    conn.commit()
    conn.close()


def mark_ad_user_op(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("UPDATE ad_users SET passed_op = 1, passed_op_at = ? WHERE user_id = ? AND passed_op = 0",
                (datetime.now().isoformat(), user_id))
    conn.commit()
    conn.close()


def mark_ad_user_blocked(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("UPDATE ad_users SET blocked = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def increment_ad_refs(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT referrer_id FROM users WHERE user_id = ?", (user_id,))
    r = cur.fetchone()
    if not r or not r[0]:
        conn.close()
        return
    referrer_id = r[0]
    cur.execute("UPDATE ad_users SET refs_count = refs_count + 1 WHERE user_id = ?", (referrer_id,))
    conn.commit()
    conn.close()


def add_ad_stars(user_id, amount):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("UPDATE ad_users SET stars_earned = stars_earned + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()


def get_ad_stats_period(code, start_iso=None, end_iso=None):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    if start_iso and end_iso:
        cur.execute("""SELECT
            COUNT(*),
            SUM(CASE WHEN registered=1 THEN 1 ELSE 0 END),
            SUM(CASE WHEN passed_op=1 AND passed_op_at >= ? AND passed_op_at < ? THEN 1 ELSE 0 END),
            SUM(CASE WHEN blocked=1 THEN 1 ELSE 0 END),
            SUM(CASE WHEN is_premium=1 THEN 1 ELSE 0 END),
            COALESCE(SUM(stars_earned),0)
            FROM ad_users WHERE code = ? AND registered_at >= ? AND registered_at < ?""",
                    (start_iso, end_iso, code.lower(), start_iso, end_iso))
    else:
        cur.execute("""SELECT
            COUNT(*),
            SUM(CASE WHEN registered=1 THEN 1 ELSE 0 END),
            SUM(CASE WHEN passed_op=1 THEN 1 ELSE 0 END),
            SUM(CASE WHEN blocked=1 THEN 1 ELSE 0 END),
            SUM(CASE WHEN is_premium=1 THEN 1 ELSE 0 END),
            COALESCE(SUM(stars_earned),0)
            FROM ad_users WHERE code = ?""", (code.lower(),))
    row = cur.fetchone()
    users = row[0] or 0
    registered = row[1] or 0
    op = row[2] or 0
    blocked = row[3] or 0
    premium = row[4] or 0
    stars = row[5] or 0

    if start_iso and end_iso:
        start_date = start_iso[:10]
        end_date = end_iso[:10]
        cur.execute("SELECT COALESCE(SUM(clicks),0) FROM ad_daily WHERE code = ? AND date >= ? AND date < ?",
                    (code.lower(), start_date, end_date))
    else:
        cur.execute("SELECT COALESCE(clicks,0) FROM ad_sources WHERE code = ?", (code.lower(),))
    clicks_row = cur.fetchone()
    clicks = clicks_row[0] if clicks_row else 0

    conn.close()
    return {
        "clicks": clicks,
        "users": users,
        "registered": registered,
        "op": op,
        "blocked": blocked,
        "premium": premium,
        "stars": stars,
    }


# ================== WITHDRAW WAITING ==================
def set_waiting_withdraw(user_id, gift_key, friends_base):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO withdraw_waiting (user_id, gift_key, friends_base, created_at) "
        "VALUES (?, ?, ?, ?)",
        (user_id, gift_key, friends_base, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_waiting_withdraw(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT user_id, gift_key, friends_base, created_at "
                "FROM withdraw_waiting WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row


def delete_waiting_withdraw(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM withdraw_waiting WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_all_waiting_withdraw_users():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM withdraw_waiting")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]
