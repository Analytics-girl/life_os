from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import database
from pydantic import BaseModel
from typing import Optional
import requests, os, shutil
from datetime import datetime

app = FastAPI(title="Life OS API")
app.mount("/static", StaticFiles(directory="static"), name="static")

UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ── Helpers ──────────────────────────────────────────────
def now(): return datetime.utcnow().isoformat()

def month_start():
    d = datetime.utcnow()
    return f"{d.year}-{d.month:02d}-01T00:00:00"

def log_timeline(conn, title: str, log_type: str, description: str = ""):
    conn.cursor().execute(
        "INSERT INTO timeline (title, type, description, date) VALUES (?,?,?,?)",
        (title, log_type, description, now()))

def send_telegram(text: str):
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='TELEGRAM_TOKEN'")
    r1 = c.fetchone()
    c.execute("SELECT value FROM settings WHERE key='TELEGRAM_CHAT_ID'")
    r2 = c.fetchone()
    conn.close()
    if r1 and r2:
        try:
            requests.post(f"https://api.telegram.org/bot{r1['value']}/sendMessage",
                          json={"chat_id": r2['value'], "text": text}, timeout=5)
        except: pass

# ── Root ─────────────────────────────────────────────────
@app.get("/")
async def root(): return FileResponse("static/index.html")

# ── Dashboard ────────────────────────────────────────────
@app.get("/api/dashboard")
def dashboard():
    conn = database.get_db_connection()
    c = conn.cursor()

    # Today's expenses
    today = datetime.utcnow().strftime("%Y-%m-%d")
    c.execute("SELECT COALESCE(SUM(amount),0) as t FROM expenses WHERE date>=?", (today+"T00:00:00",))
    today_exp = c.fetchone()["t"]

    # Monthly expenses
    c.execute("SELECT COALESCE(SUM(amount),0) as t FROM expenses WHERE date>=?", (month_start(),))
    month_exp = c.fetchone()["t"]

    # Total budget this month
    c.execute("SELECT COALESCE(SUM(monthly_budget),0) as t FROM categories")
    total_budget = c.fetchone()["t"]

    # Pending tasks
    c.execute("SELECT COUNT(*) as cnt FROM tasks WHERE completed=0")
    pending_tasks = c.fetchone()["cnt"]
    c.execute("SELECT COUNT(*) as cnt FROM tasks")
    total_tasks = c.fetchone()["cnt"]

    # Total savings
    c.execute("SELECT COALESCE(SUM(current_amount),0) as t FROM savings")
    total_saved = c.fetchone()["t"]
    c.execute("SELECT COALESCE(SUM(target_amount),0) as t FROM savings")
    total_target = c.fetchone()["t"]

    # Learning streak: count consecutive days with a log
    c.execute("SELECT DISTINCT date(date) as d FROM learning_logs ORDER BY d DESC")
    rows = c.fetchall()
    streak = 0
    check = datetime.utcnow().date()
    for row in rows:
        from datetime import date, timedelta
        d = date.fromisoformat(row["d"])
        if d == check:
            streak += 1
            check = check - timedelta(days=1)
        else:
            break

    # Diary streak
    c.execute("SELECT DISTINCT date(date) as d FROM diary_entries ORDER BY d DESC")
    rows2 = c.fetchall()
    from datetime import date, timedelta
    diary_streak = 0
    check2 = datetime.utcnow().date()
    for row in rows2:
        d = date.fromisoformat(row["d"])
        if d == check2:
            diary_streak += 1
            check2 = check2 - timedelta(days=1)
        else:
            break

    conn.close()
    return {
        "today_expenses": today_exp,
        "month_expenses": month_exp,
        "total_budget": total_budget,
        "pending_tasks": pending_tasks,
        "total_tasks": total_tasks,
        "total_saved": total_saved,
        "total_target": total_target,
        "learning_streak": streak,
        "diary_streak": diary_streak
    }

# ── Timeline ──────────────────────────────────────────────
@app.get("/api/timeline")
def get_timeline():
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM timeline ORDER BY date DESC LIMIT 30")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

# ── Settings & Telegram ───────────────────────────────────
class SettingsIn(BaseModel):
    telegram_token: str
    telegram_chat_id: str

@app.get("/api/settings")
def get_settings():
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT key, value FROM settings")
    s = {r["key"]: r["value"] for r in c.fetchall()}
    conn.close()
    return s

@app.post("/api/settings")
def save_settings(s: SettingsIn):
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings VALUES ('TELEGRAM_TOKEN',?)", (s.telegram_token,))
    c.execute("INSERT OR REPLACE INTO settings VALUES ('TELEGRAM_CHAT_ID',?)", (s.telegram_chat_id,))
    conn.commit()
    conn.close()
    return {"status": "saved"}

@app.post("/api/telegram/validate")
def validate_telegram(s: SettingsIn):
    # Step 1: Validate token
    r = requests.get(f"https://api.telegram.org/bot{s.telegram_token}/getMe", timeout=5)
    if not r.ok or not r.json().get("ok"):
        raise HTTPException(400, "Invalid Bot Token")
    bot_name = r.json()["result"]["first_name"]
    # Step 2: Send test message
    r2 = requests.post(f"https://api.telegram.org/bot{s.telegram_token}/sendMessage",
                       json={"chat_id": s.telegram_chat_id,
                             "text": "✅ Life OS Connected Successfully!\nYou'll receive reminders here."}, timeout=5)
    if not r2.ok:
        raise HTTPException(400, "Invalid Chat ID or message failed")
    # Save after validation
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings VALUES ('TELEGRAM_TOKEN',?)", (s.telegram_token,))
    c.execute("INSERT OR REPLACE INTO settings VALUES ('TELEGRAM_CHAT_ID',?)", (s.telegram_chat_id,))
    conn.commit()
    conn.close()
    return {"status": "connected", "bot_name": bot_name}

# ── Categories (Expenses) ─────────────────────────────────
class CategoryIn(BaseModel):
    name: str; monthly_budget: float; icon: str; color: str = "#7c3aed"

@app.get("/api/categories")
def get_categories():
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM categories")
    cats = [dict(r) for r in c.fetchall()]
    for cat in cats:
        c.execute("SELECT COALESCE(SUM(amount),0) as used FROM expenses WHERE category_id=? AND date>=?",
                  (cat["id"], month_start()))
        cat["used"] = c.fetchone()["used"]
    conn.close()
    return cats

@app.post("/api/categories")
def add_category(cat: CategoryIn):
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO categories (name,monthly_budget,icon,color) VALUES (?,?,?,?)",
              (cat.name, cat.monthly_budget, cat.icon, cat.color))
    log_timeline(conn, f"Created budget category: {cat.icon} {cat.name}", "Expense",
                 f"Monthly budget: ₹{cat.monthly_budget}")
    conn.commit(); conn.close()
    return {"status": "ok"}

# ── Expenses ──────────────────────────────────────────────
class ExpenseIn(BaseModel):
    amount: float; category_id: int; note: str = ""

@app.get("/api/expenses")
def get_expenses():
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("""SELECT e.*, cat.name as cat_name, cat.icon as cat_icon
                 FROM expenses e LEFT JOIN categories cat ON e.category_id=cat.id
                 WHERE e.date>=? ORDER BY e.date DESC""", (month_start(),))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

@app.get("/api/expenses/category/{cat_id}")
def get_cat_expenses(cat_id: int):
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM expenses WHERE category_id=? AND date>=? ORDER BY date DESC",
              (cat_id, month_start()))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

@app.post("/api/expenses")
def add_expense(exp: ExpenseIn):
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT name, icon FROM categories WHERE id=?", (exp.category_id,))
    cat = c.fetchone()
    c.execute("INSERT INTO expenses (amount,category_id,note,date) VALUES (?,?,?,?)",
              (exp.amount, exp.category_id, exp.note, now()))
    log_timeline(conn, f"💰 Added Expense: ₹{exp.amount}", "Expense",
                 f"{cat['icon'] if cat else ''} {cat['name'] if cat else ''} — {exp.note}")
    conn.commit(); conn.close()
    return {"status": "ok"}

# ── Tasks ─────────────────────────────────────────────────
class TaskIn(BaseModel):
    title: str; priority: str = "Medium"; due_date: str = ""; telegram_reminder: bool = False

@app.get("/api/tasks")
def get_tasks():
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM tasks ORDER BY completed ASC, id DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    for r in rows:
        r["completed"] = bool(r["completed"])
        r["telegram_reminder"] = bool(r["telegram_reminder"])
    return rows

@app.post("/api/tasks")
def add_task(t: TaskIn):
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO tasks (title,priority,due_date,telegram_reminder) VALUES (?,?,?,?)",
              (t.title, t.priority, t.due_date, int(t.telegram_reminder)))
    log_timeline(conn, f"✅ Added Task: {t.title}", "Task",
                 f"Priority: {t.priority}" + (f" | Due: {t.due_date}" if t.due_date else ""))
    conn.commit(); conn.close()
    if t.telegram_reminder:
        send_telegram(f"🔔 New Task: {t.title}\nDue: {t.due_date or 'No deadline'}")
    return {"status": "ok"}

@app.put("/api/tasks/{tid}")
def toggle_task(tid: int):
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT completed, title FROM tasks WHERE id=?", (tid,))
    row = c.fetchone()
    if not row: raise HTTPException(404, "Not found")
    new = 0 if row["completed"] else 1
    c.execute("UPDATE tasks SET completed=? WHERE id=?", (new, tid))
    if new: log_timeline(conn, f"✅ Completed Task: {row['title']}", "Task", "")
    conn.commit(); conn.close()
    return {"status": "ok"}

@app.delete("/api/tasks/{tid}")
def delete_task(tid: int):
    conn = database.get_db_connection()
    conn.cursor().execute("DELETE FROM tasks WHERE id=?", (tid,))
    conn.commit(); conn.close()
    return {"status": "ok"}

# ── Savings ───────────────────────────────────────────────
class SavingsIn(BaseModel):
    name: str; target_amount: float; monthly_contribution: float = 0
    target_date: str = ""; icon: str = "💰"; color: str = "#06b6d4"; notes: str = ""

class ContribIn(BaseModel):
    amount: float; note: str = ""

@app.get("/api/savings")
def get_savings():
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM savings ORDER BY id DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

@app.post("/api/savings")
def add_savings(s: SavingsIn):
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO savings (name,target_amount,monthly_contribution,target_date,icon,color,notes) VALUES (?,?,?,?,?,?,?)",
              (s.name, s.target_amount, s.monthly_contribution, s.target_date, s.icon, s.color, s.notes))
    log_timeline(conn, f"{s.icon} Created Savings Goal: {s.name}", "Savings",
                 f"Target: ₹{s.target_amount}")
    conn.commit(); conn.close()
    return {"status": "ok"}

@app.post("/api/savings/{gid}/contribute")
def add_contribution(gid: int, data: ContribIn):
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT name, icon FROM savings WHERE id=?", (gid,))
    goal = c.fetchone()
    c.execute("UPDATE savings SET current_amount=current_amount+? WHERE id=?", (data.amount, gid))
    c.execute("INSERT INTO savings_contributions (savings_id,amount,note,date) VALUES (?,?,?,?)",
              (gid, data.amount, data.note, now()))
    log_timeline(conn, f"💵 Added ₹{data.amount} to {goal['icon']} {goal['name']}", "Savings", data.note)
    conn.commit(); conn.close()
    return {"status": "ok"}

@app.get("/api/savings/{gid}/history")
def savings_history(gid: int):
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM savings_contributions WHERE savings_id=? ORDER BY date DESC", (gid,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

# ── Learning Categories ───────────────────────────────────
class LearnCatIn(BaseModel):
    name: str; skill_level: str = "Beginner"; goal: str = ""; icon: str = "📚"; color: str = "#10b981"

@app.get("/api/learning/categories")
def get_learn_cats():
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM learning_categories ORDER BY id DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

@app.post("/api/learning/categories")
def add_learn_cat(cat: LearnCatIn):
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO learning_categories (name,skill_level,goal,icon,color) VALUES (?,?,?,?,?)",
              (cat.name, cat.skill_level, cat.goal, cat.icon, cat.color))
    log_timeline(conn, f"{cat.icon} Started Learning: {cat.name}", "Learning", f"Goal: {cat.goal}")
    conn.commit(); conn.close()
    return {"status": "ok"}

# ── Learning Logs ─────────────────────────────────────────
class LearnLogIn(BaseModel):
    category_id: Optional[int] = None
    what_went_well: str = ""; impediments: str = ""; learnings: str = ""
    happiness: int = 3; tomorrow_plan: str = ""; hours: float = 0

@app.get("/api/learning/logs")
def get_learn_logs():
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("""SELECT l.*, lc.name as cat_name, lc.icon as cat_icon
                 FROM learning_logs l LEFT JOIN learning_categories lc ON l.category_id=lc.id
                 ORDER BY l.date DESC LIMIT 30""")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

@app.post("/api/learning/logs")
def add_learn_log(log: LearnLogIn):
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO learning_logs (category_id,what_went_well,impediments,learnings,
                 happiness,tomorrow_plan,hours,date) VALUES (?,?,?,?,?,?,?,?)""",
              (log.category_id, log.what_went_well, log.impediments, log.learnings,
               log.happiness, log.tomorrow_plan, log.hours, now()))
    happiness_labels = {1:"😞 Very Low",2:"😐 Low",3:"😊 Okay",4:"😄 Good",5:"🚀 Amazing"}
    log_timeline(conn, f"📚 Learning Log — {log.hours}h", "Learning",
                 f"Happiness: {happiness_labels.get(log.happiness,'')} | {log.learnings[:60]}")
    conn.commit(); conn.close()
    return {"status": "ok"}

# ── Learning Todos ────────────────────────────────────────
class LearnTodoIn(BaseModel):
    title: str; category_id: Optional[int] = None; priority: str = "Medium"
    deadline: str = ""; telegram_reminder: bool = False

@app.get("/api/learning/todos")
def get_learn_todos():
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("""SELECT t.*, lc.name as cat_name, lc.icon as cat_icon
                 FROM learning_todos t LEFT JOIN learning_categories lc ON t.category_id=lc.id
                 ORDER BY t.completed ASC, t.id DESC""")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    for r in rows:
        r["completed"] = bool(r["completed"])
        r["telegram_reminder"] = bool(r["telegram_reminder"])
    return rows

@app.post("/api/learning/todos")
def add_learn_todo(t: LearnTodoIn):
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO learning_todos (title,category_id,priority,deadline,telegram_reminder,created_at) VALUES (?,?,?,?,?,?)",
              (t.title, t.category_id, t.priority, t.deadline, int(t.telegram_reminder), now()))
    log_timeline(conn, f"🧠 Learning Todo: {t.title}", "Learning", f"Priority: {t.priority}")
    conn.commit(); conn.close()
    if t.telegram_reminder:
        send_telegram(f"🧠 Learning Reminder: {t.title}\nDeadline: {t.deadline or 'None'}")
    return {"status": "ok"}

@app.put("/api/learning/todos/{tid}")
def toggle_learn_todo(tid: int):
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT completed, title FROM learning_todos WHERE id=?", (tid,))
    row = c.fetchone()
    if not row: raise HTTPException(404, "Not found")
    new = 0 if row["completed"] else 1
    c.execute("UPDATE learning_todos SET completed=? WHERE id=?", (new, tid))
    if new: log_timeline(conn, f"🧠 Completed Learning Todo: {row['title']}", "Learning", "")
    conn.commit(); conn.close()
    return {"status": "ok"}

# ── Diary ─────────────────────────────────────────────────
class DiaryIn(BaseModel):
    title: str; mood: str = "neutral"; activities: str = ""
    thoughts: str = ""; reflections: str = ""; tags: str = ""

@app.get("/api/diary")
def get_diary():
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM diary_entries ORDER BY date DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

@app.post("/api/diary")
def add_diary(entry: DiaryIn):
    conn = database.get_db_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO diary_entries (title,mood,activities,thoughts,reflections,tags,date)
                 VALUES (?,?,?,?,?,?,?)""",
              (entry.title, entry.mood, entry.activities, entry.thoughts,
               entry.reflections, entry.tags, now()))
    entry_id = c.lastrowid
    moods = {"happy":"😊","sad":"😞","neutral":"😐","excited":"🚀","calm":"😌","stressed":"😤"}
    emoji = moods.get(entry.mood, "📖")
    log_timeline(conn, f"{emoji} Diary: {entry.title}", "Diary", f"Mood: {entry.mood}")
    conn.commit(); conn.close()
    return {"status": "ok", "id": entry_id}

@app.post("/api/diary/{entry_id}/media")
async def upload_media(entry_id: int, file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1]
    fname = f"diary_{entry_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{ext}"
    fpath = f"{UPLOAD_DIR}/{fname}"
    with open(fpath, "wb") as f:
        shutil.copyfileobj(file.file, f)
    conn = database.get_db_connection()
    c = conn.cursor()
    mtype = "image" if ext.lower() in [".jpg",".jpeg",".png",".gif",".webp"] else "document"
    c.execute("INSERT INTO diary_media (entry_id,filename,filepath,media_type,uploaded_at) VALUES (?,?,?,?,?)",
              (entry_id, fname, fpath, mtype, now()))
    conn.commit(); conn.close()
    return {"status": "ok", "filename": fname, "url": f"/static/uploads/{fname}"}
