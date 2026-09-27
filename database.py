import sqlite3
from datetime import datetime, timedelta, date
from config import DB, DEFAULTS, REFERRAL_DAYS, JOIN_REQUEST_HOURS


def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0, last_bonus TEXT, referrer_id INTEGER, registered_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS referrals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, referrer_id INTEGER, created_at TEXT, reminded INTEGER DEFAULT 0, status TEXT DEFAULT 'pending')""")
    cur.execute("""CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, gift TEXT, status TEXT DEFAULT 'pending', created_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS promos (code TEXT PRIMARY KEY, amount REAL, max_uses INTEGER, used INTEGER DEFAULT 0, active INTEGER DEFAULT 1)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS promo_uses (code TEXT, user_id INTEGER, used_at TEXT, PRIMARY KEY (code, user_id))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS custom_ops (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, link TEXT, type TEXT, active INTEGER DEFAULT 1)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS bh_rewards (user_id INTEGER, link TEXT, done_at TEXT, PRIMARY KEY (user_id, link))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS custom_tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, link TEXT, reward INTEGER DEFAULT 10, active INTEGER DEFAULT 1)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS custom_tasks_done (user_id INTEGER, task_id INTEGER, done_at TEXT, PRIMARY KEY (user_id, task_id))""")

    # --- ref_progress: прогресс реферала по 5 заданиям ---
    cur.execute("""CREATE TABLE IF NOT EXISTS ref_progress (
        user_id INTEGER PRIMARY KEY,
        referrer_id INTEGER,
        tasks_done INTEGER DEFAULT 0,
        started_at TEXT,
        notified_5min INTEGER DEFAULT 0,
        notified_10min INTEGER DEFAULT 0,
        notified_done INTEGER DEFAULT 0,
        paid INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active'
    )""")

    # --- миграция custom_tasks ---
    cur.execute("PRAGMA table_info(custom_tasks)")
    cols = {r[1] for r in cur.fetchall()}
    if "check_type" not in cols:
        cur.execute("ALTER TABLE custom_tasks ADD COLUMN check_type TEXT DEFAULT 'bot'")
    if "check_target" not in cols:
        cur.execute("ALTER TABLE custom_tasks ADD COLUMN check_target TEXT DEFAULT ''")

    # --- миграция users: баланс REAL (если старая таблица с INTEGER — данные не сломаются,
    #     SQLite хранит числа с плавающей точкой и в INTEGER-колонке тоже) ---
    # Ничего делать не нужно: SQLite динамически типизирован.

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


def get_user_display(user_id):
    """Возвращает @username, или first_name, или ID xxx — что-то одно для отображения."""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT username FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row and row[0]:
        return f"@{row[0]}"
    return f"ID {user_id}"


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
    """Считаем только тех, кто прошёл 5/5 (ref_progress.status = 'done')."""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM ref_progress WHERE referrer_id = ? AND status = 'done'",
        (referrer_id,),
    )
    n = cur.fetchone()[0]
    conn.close()
    return n


def get_user_referrals(referrer_id, limit=100):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        """SELECT rp.user_id, u.username, rp.started_at, rp.status
           FROM ref_progress rp LEFT JOIN users u ON u.user_id = rp.user_id
           WHERE rp.referrer_id = ?
           ORDER BY rp.started_at DESC LIMIT ?""",
        (referrer_id, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def expire_old_referrals():
    """Старая схема (referrals) больше не используется, оставлено для совместимости."""
    return []


def get_refs_to_remind():
    return []


def mark_reminded(rid):
    pass


# ================== REF_PROGRESS (5 заданий) ==================
def create_ref_progress(user_id, referrer_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO ref_progress "
        "(user_id, referrer_id, tasks_done, started_at, status) "
        "VALUES (?, ?, 0, ?, 'active')",
        (user_id, referrer_id, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_ref_progress(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, referrer_id, tasks_done, started_at, notified_5min, "
        "notified_10min, notified_done, paid, status FROM ref_progress WHERE user_id = ?",
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()
    return row


def increment_ref_tasks(user_id):
    """Увеличивает счётчик выполненных заданий.
       Возвращает (new_done, referrer_id, just_reached_goal)."""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT tasks_done, referrer_id, status FROM ref_progress WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None, None, False
    tasks_done, referrer_id, status = row
    if status != "active":
        conn.close()
        return tasks_done, None, False
    new_done = tasks_done + 1
    cur.execute("UPDATE ref_progress SET tasks_done = ? WHERE user_id = ?", (new_done, user_id))
    conn.commit()
    conn.close()
    return new_done, referrer_id, False


def set_ref_notified(user_id, field):
    if field not in ("notified_5min", "notified_10min", "notified_done"):
        return
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(f"UPDATE ref_progress SET {field} = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def mark_ref_paid(user_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("UPDATE ref_progress SET paid = 1, status = 'done' WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_refs_to_notify_5min():
    """Активные рефы, у которых прошло >= 5 минут, уведомление не отправлено."""
    threshold = (datetime.now() - timedelta(minutes=5)).isoformat()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, referrer_id, tasks_done FROM ref_progress "
        "WHERE status = 'active' AND notified_5min = 0 AND started_at < ?",
        (threshold,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_refs_to_notify_10min():
    """Активные рефы, у которых прошло >= 10 минут и не отправлено."""
    threshold = (datetime.now() - timedelta(minutes=10)).isoformat()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, referrer_id, tasks_done FROM ref_progress "
        "WHERE status = 'active' AND notified_10min = 0 AND started_at < ?",
        (threshold,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def expire_old_ref_progress(days=7):
    """Помечает expired активные рефы, если прошло > days дней."""
    threshold = (datetime.now() - timedelta(days=days)).isoformat()
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, referrer_id FROM ref_progress "
        "WHERE status = 'active' AND started_at < ?",
        (threshold,),
    )
    rows = cur.fetchall()
    for uid, _ in rows:
        cur.execute("UPDATE ref_progress SET status = 'expired' WHERE user_id = ?", (uid,))
    conn.commit()
    conn.close()
    return rows


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
    cur.execute("SELECT COUNT(*) FROM ref_progress WHERE status = 'done'")
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
    cur.execute(
        """SELECT u.user_id, u.username, COUNT(rp.user_id) as refs
           FROM users u
           LEFT JOIN ref_progress rp ON rp.referrer_id = u.user_id AND rp.status = 'done'
           GROUP BY u.user_id HAVING refs > 0
           ORDER BY refs DESC LIMIT ?""",
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


# ================== PROMOS ==================
def create_promo(code, amount, max_uses):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO promos (code, amount, max_uses, used, active) VALUES (?, ?, ?, 0, 1)",
                (code.upper(), amount, max_uses))
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
    cur.execute("INSERT INTO promo_uses (code, user_id, used_at) VALUES (?, ?, ?)",
                (code, user_id, datetime.now().isoformat()))
    cur.execute("UPDATE promos SET used = used + 1 WHERE code = ?", (code,))
    cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()
    return True, f"✅ Промокод активирован! +{amount} ⭐", amount


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
        (title, link, check_type, check_target),
    )
    conn.commit()
    conn.close()


def list_custom_tasks():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, title, link, reward, active, check_type, check_target "
                "FROM custom_tasks ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_custom_task(task_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT id, title, link, reward, active, check_type, check_target "
                "FROM custom_tasks WHERE id = ?", (task_id,))
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
        "(SELECT task_id FROM custom_tasks_done WHERE user_id = ?) "
        "ORDER BY id LIMIT 1",
        (user_id,),
    )
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


# ================== COUNT: сколько заданий юзер выполнил ==================
def get_total_tasks_done(user_id):
    """Общее число выполненных заданий: свои + Botohub."""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM custom_tasks_done WHERE user_id = ?", (user_id,))
    custom_done = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM bh_rewards WHERE user_id = ?", (user_id,))
    bh_done = cur.fetchone()[0]
    conn.close()
    return custom_done + bh_done
