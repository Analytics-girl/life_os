import sqlite3
from datetime import datetime

DB_FILE = "life_os.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    # Settings (Telegram, user prefs)
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, value TEXT NOT NULL)''')

    # Global Timeline
    c.execute('''CREATE TABLE IF NOT EXISTS timeline (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL, type TEXT NOT NULL,
        description TEXT DEFAULT '',
        date TEXT NOT NULL)''')

    # Budget Categories
    c.execute('''CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, monthly_budget REAL NOT NULL,
        icon TEXT NOT NULL, color TEXT DEFAULT '#7c3aed')''')

    # Expenses
    c.execute('''CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        amount REAL NOT NULL, category_id INTEGER NOT NULL,
        note TEXT DEFAULT '', date TEXT NOT NULL)''')

    # Tasks
    c.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL, priority TEXT DEFAULT 'Medium',
        due_date TEXT DEFAULT '', completed INTEGER DEFAULT 0,
        telegram_reminder INTEGER DEFAULT 0)''')

    # Savings Goals (independent)
    c.execute('''CREATE TABLE IF NOT EXISTS savings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, target_amount REAL NOT NULL,
        current_amount REAL DEFAULT 0,
        monthly_contribution REAL DEFAULT 0,
        target_date TEXT DEFAULT '',
        icon TEXT DEFAULT '💰', color TEXT DEFAULT '#06b6d4',
        notes TEXT DEFAULT '')''')

    # Savings Contributions history
    c.execute('''CREATE TABLE IF NOT EXISTS savings_contributions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        savings_id INTEGER NOT NULL,
        amount REAL NOT NULL, note TEXT DEFAULT '',
        date TEXT NOT NULL)''')

    # Learning Categories
    c.execute('''CREATE TABLE IF NOT EXISTS learning_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL, skill_level TEXT DEFAULT 'Beginner',
        goal TEXT DEFAULT '', icon TEXT DEFAULT '📚',
        color TEXT DEFAULT '#10b981')''')

    # Daily Learning Logs
    c.execute('''CREATE TABLE IF NOT EXISTS learning_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_id INTEGER,
        what_went_well TEXT DEFAULT '',
        impediments TEXT DEFAULT '',
        learnings TEXT DEFAULT '',
        happiness INTEGER DEFAULT 3,
        tomorrow_plan TEXT DEFAULT '',
        hours REAL DEFAULT 0,
        date TEXT NOT NULL)''')

    # Learning Todos (separate from tasks)
    c.execute('''CREATE TABLE IF NOT EXISTS learning_todos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        category_id INTEGER,
        priority TEXT DEFAULT 'Medium',
        deadline TEXT DEFAULT '',
        completed INTEGER DEFAULT 0,
        telegram_reminder INTEGER DEFAULT 0,
        created_at TEXT NOT NULL)''')

    # Diary Entries
    c.execute('''CREATE TABLE IF NOT EXISTS diary_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        mood TEXT DEFAULT 'neutral',
        activities TEXT DEFAULT '',
        thoughts TEXT DEFAULT '',
        reflections TEXT DEFAULT '',
        tags TEXT DEFAULT '',
        date TEXT NOT NULL)''')

    # Diary Media
    c.execute('''CREATE TABLE IF NOT EXISTS diary_media (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entry_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        filepath TEXT NOT NULL,
        media_type TEXT DEFAULT 'image',
        uploaded_at TEXT NOT NULL)''')

    conn.commit()
    conn.close()

init_db()
