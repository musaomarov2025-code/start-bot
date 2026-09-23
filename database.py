import sqlite3
from datetime import datetime, timedelta, date
from config import DB, DEFAULTS, GIFTS, REFERRAL_DAYS, JOIN_REQUEST_HOURS


def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance INTEGER DEFAULT 0,
            last_bonus TEXT,
            referrer_id INTEGER,
            registered_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            referrer_id INTEGER,
            created_at TEXT,
            reminded INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending'
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            gift TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT,
            title TEXT,
            invite_link TEXT,
            type TEXT
        )
    """)
    cur.execute("PRAGMA table_info(channels)")
    cols = [row[1] for row in cur.fetchall()]
    if "bot_admin" not in cols:
        cur.execute("ALTER TABLE channels ADD COLUMN bot_admin INTEGER DEFAULT 0")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS channel_joins (
            chat_id TEXT,
            user_id INTEGER,
            PRIMARY KEY (chat_id, user_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS join_requests (
            user_id INTEGER,
            chat_id TEXT,
            created_at TEXT,
            PRIMARY KEY (user_id, chat_id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS promos (
            code TEXT PRIMARY KEY,
            amount INTEGER,
            max_uses INTEGER,
            used INTEGER DEFAULT 0,
            active INTEGER DEFAULT 1
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS promo_uses (
            code TEXT,
            user_id INTEGER,
            used_at TEXT,
            PRIMARY KEY (code, user_id)
        )
    """)
    conn.commit()
    conn.close()


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
    cur.execute(
        "INSERT INTO users (user_id, username, referrer_id, registered_at) VALUES (?, ?, ?, ?)",
        (user_id, username, referrer_id, datetime.now().isoformat())
    )
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


def get_top(limit=10):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT username, balance FROM users ORDER BY balance DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_place(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM users WHERE balance > (SELECT balance FROM users WHERE user_id = ?)",
        (user_id,)
    )
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
    cur.execute(
        "UPDATE users SET last_bonus = ? WHERE user_id = ?",
        (datetime.now().isoformat(), user_id)
    )
    conn.commit()
    conn.close()


def create_pending_referral(user_id, referrer_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO referrals (user_id, referrer_id, created_at, status) VALUES (?, ?, ?, 'pending')",
        (user_id, referrer_id, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_pending_refs_count(referrer_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND status = 'pending'",
        (referrer_id,)
    )
    n = cur.fetchone()[0]
    conn.close()
    return n


def get_confirmed_refs_count(referrer_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND status = 'confirmed'",
        (referrer_id,)
    )
    n = cur.fetchone()[0]
    conn.close()
    return n


def confirm_referral(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, referrer_id FROM referrals WHERE user_id = ? AND status = 'pending' ORDER BY id LIMIT 1",
        (user_id,)
    )
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
    cur.execute(
        "SELECT id, user_id, referrer_id FROM referrals WHERE status = 'pending' AND created_at < ?",
        (threshold,)
    )
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
    cur.execute(
        "SELECT id, user_id, referrer_id FROM referrals WHERE status = 'pending' AND reminded = 0 AND created_at < ?",
        (threshold,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def mark_reminded(rid):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("UPDATE referrals SET reminded = 1 WHERE id = ?", (rid,))
    conn.commit()
    conn.close()


def create_withdrawal(user_id, amount, gift):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO withdrawals (user_id, amount, gift, created_at) VALUES (?, ?, ?, ?)",
        (user_id, amount, gift, datetime.now().isoformat())
    )
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


def set_withdrawal_status(wid, status):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("UPDATE withdrawals SET status = ? WHERE id = ?", (status, wid))
    conn.commit()
    conn.close()


def get_channels(ch_type):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, chat_id, title, invite_link, bot_admin FROM channels WHERE type = ?", (ch_type,))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_channel_by_id(cid):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, chat_id, title, invite_link, type, bot_admin FROM channels WHERE id = ?", (cid,))
    row = cur.fetchone()
    conn.close()
    return row


def add_channel(chat_id, title, invite_link, ch_type, bot_admin=0):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO channels (chat_id, title, invite_link, type, bot_admin) VALUES (?, ?, ?, ?, ?)",
        (chat_id, title, invite_link, ch_type, bot_admin)
    )
    conn.commit()
    conn.close()


def delete_channel(cid):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM channels WHERE id = ?", (cid,))
    conn.commit()
    conn.close()


def clear_channels(ch_type):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM channels WHERE type = ?", (ch_type,))
    conn.commit()
    conn.close()


def track_channel_join(chat_id, user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO channel_joins (chat_id, user_id) VALUES (?, ?)", (chat_id, user_id))
    conn.commit()
    conn.close()


def get_channel_joins(chat_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM channel_joins WHERE chat_id = ?", (chat_id,))
    n = cur.fetchone()[0]
    conn.close()
    return n


def save_join_request(user_id, chat_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO join_requests (user_id, chat_id, created_at) VALUES (?, ?, ?)",
        (user_id, str(chat_id), datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def has_recent_join_request(user_id, chat_id):
    threshold = (datetime.now() - timedelta(hours=JOIN_REQUEST_HOURS)).isoformat()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM join_requests WHERE user_id = ? AND chat_id = ? AND created_at > ?",
        (user_id, str(chat_id), threshold)
    )
    row = cur.fetchone()
    conn.close()
    return row is not None


def cleanup_join_requests():
    threshold = (datetime.now() - timedelta(hours=JOIN_REQUEST_HOURS)).isoformat()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM join_requests WHERE created_at < ?", (threshold,))
    conn.commit()
    conn.close()


def get_stats():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users WHERE registered_at LIKE ?", (str(date.today()) + "%",))
    today = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'pending'")
    pending = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'completed'")
    done = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status = 'completed'")
    total_stars = cur.fetchone()[0]
    conn.close()
    return {
        "total": total,
        "today": today,
        "pending": pending,
        "done": done,
        "total_stars": total_stars,
    }


def create_promo(code, amount, max_uses):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO promos (code, amount, max_uses, used, active) VALUES (?, ?, ?, 0, 1)",
        (code.upper(), amount, max_uses)
    )
    conn.commit()
    conn.close()


def get_promo(code):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT code, amount, max_uses, used, active FROM promos WHERE code = ?", (code.upper(),))
    row = cur.fetchone()
    conn.close()
    return row


def list_promos():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT code, amount, max_uses, used, active FROM promos ORDER BY code")
    rows = cur.fetchall()
    conn.close()
    return rows


def delete_promo(code):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM promos WHERE code = ?", (code.upper(),))
    cur.execute("DELETE FROM promo_uses WHERE code = ?", (code.upper(),))
    conn.commit()
    conn.close()


def user_used_promo(code, user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM promo_uses WHERE code = ? AND user_id = ?", (code.upper(), user_id))
    row = cur.fetchone()
    conn.close()
    return row is not None


def activate_promo(code, user_id):
    code = code.upper()
    promo = get_promo(code)
    if not promo:
        return False, "❌ Такого промокода не существует.", 0
    c, amount, max_uses, used, active = promo
    if not active:
        return False, "❌ Промокод деактивирован.", 0
    if used >= max_uses:
        return False, "❌ Промокод больше не действует.", 0
    if user_used_promo(code, user_id):
        return False, "❌ Ты уже активировал этот промокод.", 0

    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO promo_uses (code, user_id, used_at) VALUES (?, ?, ?)",
        (code, user_id, datetime.now().isoformat())
    )
    cur.execute("UPDATE promos SET used = used + 1 WHERE code = ?", (code,))
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()
    return True, f"✅ Промокод активирован! +{amount} ⭐", amount
