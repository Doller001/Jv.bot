import sqlite3
from datetime import date
import os

# Try temp disk first, fallback to memory
DB_PATH = "/tmp/jarvis.db"

def get_db():
    try:
        # test write permission
        open(DB_PATH, "a").close()
        return DB_PATH
    except:
        return ":memory:"

DB = get_db()

def connect():
    return sqlite3.connect(DB, check_same_thread=False)

def init():
    con = connect()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER PRIMARY KEY,
        username TEXT,
        name TEXT,
        blocked INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS usage (
        chat_id INTEGER,
        cmd TEXT,
        day TEXT,
        count INTEGER,
        PRIMARY KEY (chat_id, cmd, day)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS limits (
        cmd TEXT PRIMARY KEY,
        max INTEGER
    )
    """)

    # default limits
    cur.execute("INSERT OR IGNORE INTO limits VALUES ('chat', 20)")
    cur.execute("INSERT OR IGNORE INTO limits VALUES ('img', 5)")
    cur.execute("INSERT OR IGNORE INTO limits VALUES ('video', 2)")

    con.commit()
    con.close()

def add_user(chat_id, username, name):
    con = connect()
    cur = con.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO users(chat_id, username, name, blocked) VALUES (?, ?, ?, 0)",
        (chat_id, username or "", name or "")
    )
    con.commit()
    con.close()

def is_blocked(chat_id):
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT blocked FROM users WHERE chat_id=?", (chat_id,))
    r = cur.fetchone()
    con.close()
    if not r:
        return False
    return r[0] == 1

def block(chat_id, val: bool):
    con = connect()
    cur = con.cursor()
    cur.execute("UPDATE users SET blocked=? WHERE chat_id=?", (1 if val else 0, chat_id))
    con.commit()
    con.close()

def get_limit(cmd):
    con = connect()
    cur = con.cursor()
    cur.execute("SELECT max FROM limits WHERE cmd=?", (cmd,))
    r = cur.fetchone()
    con.close()
    return r[0] if r else 0

def set_limit(cmd, val):
    con = connect()
    cur = con.cursor()
    cur.execute("INSERT OR REPLACE INTO limits(cmd, max) VALUES (?, ?)", (cmd, val))
    con.commit()
    con.close()

def can_use(chat_id, cmd):
    today = date.today().isoformat()
    limit = get_limit(cmd)

    con = connect()
    cur = con.cursor()

    cur.execute(
        "SELECT count FROM usage WHERE chat_id=? AND cmd=? AND day=?",
        (chat_id, cmd, today)
    )
    r = cur.fetchone()
    con.close()

    if not r:
        return True

    return r[0] < limit

def increase(chat_id, cmd):
    today = date.today().isoformat()
    con = connect()
    cur = con.cursor()

    cur.execute(
        "SELECT count FROM usage WHERE chat_id=? AND cmd=? AND day=?",
        (chat_id, cmd, today)
    )
    r = cur.fetchone()

    if not r:
        cur.execute(
            "INSERT INTO usage(chat_id, cmd, day, count) VALUES (?, ?, ?, 1)",
            (chat_id, cmd, today)
        )
    else:
        cur.execute(
            "UPDATE usage SET count = count + 1 WHERE chat_id=? AND cmd=? AND day=?",
            (chat_id, cmd, today)
        )

    con.commit()
    con.close()

def stats():
    con = connect()
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM users WHERE blocked=1")
    blocked = cur.fetchone()[0]

    con.close()

    return {"total": total, "blocked": blocked}