import os, json, random, logging, re
from datetime import time as dtime, date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("BOT_TOKEN", "")

# ─── Данные ───────────────────────────────────────────────────────────────────
DATA_FILE = "data.json"

def load():
    try:
        with open(DATA_FILE) as f: return json.load(f)
    except: return {}

def save(data):
    with open(DATA_FILE, "w") as f: json.dump(data, f, ensure_ascii=False, indent=2)

def get_user(data, uid):
    uid = str(uid)
    if uid not in data:
        data[uid] = {"habits": [], "next_id": 1}
    return data[uid]

def ensure_habit_fields(h):
    """Добавляет новые поля к старым привычкам, если их ещё нет."""
    h.setdefault("history", [])
    h.setdefault("track_number", False)
    h.setdefault("counts", {})
    return h

def today_str():
    return date.today().isoformat()

def mark_done_today(h, value=None):
    t = today_str()
    if t not in h["history"]:
        h["history"].append(t)
    if value is not None:
        h["counts"][t] = value

def unmark_today(h):
    t = today_str()
    if t in h["history"]:
        h["history"].remove(t)
    h["counts"].pop(t, None)

def compute_streak(history):
    dates_set = set(history)
    d = date.today()
    if d.isoformat() not in dates_set:
        d -= timedelta(days=1)
    streak = 0
    while d.isoformat() in dates_set:
        streak += 1
        d -= timedelta(days=1)
    return streak

def week_completion(history):
    """Сколько раз выполнено за последние 7 дней."""
    dates_set = set(history)
    count = 0
    for i in range(7):
        d = (date.today() - timedelta(days=i)).isoformat()
        if d in dates_set:
            count += 1
    return count

# ─── Тексты ───────────────────────────────────────────────────────────────────
PRAISE = [
    "Красавчик! 🔥", "Вот это да! Так держать! 💪", "Ты машина! ⚡",
    "Гордишься собой? Правильно делаешь! 😎", "Ай да молодец! 🎉",
    "Не остановить тебя! 🚀", "Шаг за шагом — ты делаешь это! 👊",
    "Легенда! ✨", "Вот это дисциплина! 🏆", "Зачёт! Уважение 🫡",
    "Топ! Продолжай в том же духе! 💯", "Ты сделал это! 🎯"
]

FUNNY = {
    "вода":    ["Бегом пить, пока не высох! 💧", "Твои клетки умирают от жажды! 😱", "Вода сама себя не выпьет, давай! 🚰"],
    "отжим":   ["Вставай, слабак, и отжимайся! 💪", "Грудь сама себя не накачает! 🏋️", "Пол скучает по твоим рукам. Давай! 👐"],
    "присяд":  ["Ноги не для красоты! Приседай! 🦵", "Встал-сел, встал-сел. Ты знаешь что делать! 🔄", "Ягодицы сами себя не накачают! 🍑"],
    "пробежк": ["Ноги есть — беги! Диван подождёт 🏃", "Кроссовки не для красоты куплены! 👟", "Выйди из берлоги и беги! 🌿"],
    "медитац": ["Стоп, выдохни. Мозгу нужен перерыв 🧘", "5 минут тишины — это не лень, это здоровье ☮️", "Сядь. Закрой глаза. Дыши. Ты справишься 🌬️"],
    "чита":    ["Книга сама себя не прочитает! 📚", "Открывай, умнеть пора! 🧠", "30 страниц и ты уже лучше, чем вчера 📖"],
    "сон":     ["Ложись уже, завтра будешь бодрым! 😴", "Телефон вниз, голову на подушку! 🛁", "Твоё тело хочет спать. Слушай его! 🌙"],
    "зарядк":  ["Подъём! Тело требует движения! ⚡", "5 минут — и день начнётся правильно! ☀️", "Лень — это не ты. Вставай! 🔥"],
}

def get_funny(name):
    n = name.lower()
    for key, msgs in FUNNY.items():
        if key in n:
            return random.choice(msgs)
    return random.choice([
        "Эй, не забудь про своё дело! ⏰",
        "Время действовать, пока не забыл! 💡",
        "Это твоё напоминание. Ты знаешь что делать 👊",
    ])

# ─── Клавиатуры ───────────────────────────────────────────────────────────────
EMOJIS = ["💪","💧","🏃","📚","🧘","🥗","😴","✍️","🌿","🛁","🌅","🎵","🚴","🏋️","🤸","🍎","☕","🦷","🧠","❤️","🎯","⚡","🔥","🏆","✅","🚀","🎉","🌊","🧹","🥤"]

def habits_keyboard(habits):
    rows = []
    sorted_habits = sorted(habits, key=lambda h: h["time"] if h.get("time") else "99:99")
    for h in sorted_habits:
        check = "✅" if h["done"] else "⬜"
        streak = compute_streak(h.get("history", []))
        streak_str = f"  🔥{streak}" if streak > 0 else ""
        rows.append([InlineKeyboardButton(
            f"{check} {h['emoji']} {h['name']}" + (f"  ⏰{h['time']}" if h.get('time') else "") + streak_str,
            callback_data=f"toggle:{h['id']}"
        )])
    rows.append([
        InlineKeyboardButton("➕ Добавить", callback_data="add"),
        InlineKeyboardButton("⚙️ Настройки", callback_data="settings"),
    ])
    rows.append([InlineKeyboardButton("📊 Статистика", callback_data="stats")])
    return InlineKeyboardMarkup(rows)

def settings_keyboard(habits):
    rows = []
    sorted_habits = sorted(habits, key=lambda h: h["time"] if h.get("time") else "99:99")
    for h in sorted_habits:
        rows.append([InlineKeyboardButton(
            f"{h['emoji']} {h['name']}", callback_data=f"edit:{h['id']}"
        )])
    rows.append([InlineKeyboardButton("« Назад", callback_data="back")])
    return InlineKeyboardMarkup(rows)

def edit_keyboard(h):
    count_label = "🔢 Считать число: Вкл ✓" if h.get("track_number") else "🔢 Считать число: Выкл"
    rows = [
        [InlineKeyboardButton("✏️ Переименовать", callback_data=f"rename:{h['id']}")],
        [InlineKeyboardButton("⏰ Изменить время", callback_data=f"settime:{h['id']}")],
        [InlineKeyboardButton("😀 Сменить смайлик", callback_data=f"setemoji:{h['id']}")],
        [InlineKeyboardButton(count_label, callback_data=f"togglecount:{h['id']}")],
        [InlineKeyboardButton("🗑 Удалить", callback_data=f"delete:{h['id']}")],
        [InlineKeyboardButton("« Назад", callback_data="settings")],
    ]
    return InlineKeyboardMarkup(rows)

def emoji_keyboard(hid):
    rows = []
    row = []
    for i, e in enumerate(EMOJIS):
        row.append(InlineKeyboardButton(e, callback_data=f"emoji:{hid}:{e}"))
        if len(row) == 5:
            rows.append(row); row = []
    if row: rows.append(row)
    rows.append([InlineKeyboardButton("« Назад", callback_data=f"edit:{hid}")])
    return InlineKeyboardMarkup(rows)

# ─── Статистика ───────────────────────────────────────────────────────────────
def progress_text(habits):
    if not habits: return "Пока нет привычек. Нажми ➕ чтобы добавить!"
    done = sum(1 for h in habits if h["done"])
    total = len(habits)
    pct = int(done / total * 100)
    bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
    if pct == 100:
        return f"[{bar}] {done}/{total}\n\n🎉 Все привычки выполнены! Ты легенда!"
    return f"[{bar}] {done}/{total} — {pct}%"

def main_text(habits):
    return f"📋 *Мои привычки*\n\n{progress_text(habits)}"

def stats_text(habits):
    if not habits:
        return "📊 *Статистика*\n\nПока нет привычек для статистики."
    lines = ["📊 *Статистика*\n"]
    total_week = 0
    max_possible = len(habits) * 7
    for h in sorted(habits, key=lambda x: -compute_streak(x.get("history", []))):
        streak = compute_streak(h.get("history", []))
        week = week_completion(h.get("history", []))
        total_week += week
        streak_part = f"🔥{streak}" if streak > 0 else "—"
        lines.append(f"{h['emoji']} {h['name']}: {week}/7 за неделю, стрик {streak_part}")
    if max_possible > 0:
        pct = int(total_week / max_possible * 100)
        lines.append(f"\nОбщий результат за неделю: {pct}%")
    return "\n".join(lines)

# ─── Состояния диалога ────────────────────────────────────────────────────────
WAITING_NAME, WAITING_TIME, WAITING_RENAME, WAITING_NEW_TIME = range(4)
user_state = {}  # uid -> {action, habit_id}

# ─── Хендлеры ─────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    u = get_user(data, update.effective_user.id)
    for h in u["habits"]:
        ensure_habit_fields(h)
    save(data)
    await update.message.reply_text(
        main_text(u["habits"]),
        reply_markup=habits_keyboard(u["habits"]),
        parse_mode="Markdown"
    )

async def stats_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load()
    u = get_user(data, update.effective_user.id)
    for h in u["habits"]:
        ensure_habit_fields(h)
    save(data)
    await update.message.reply_text(
        stats_text(u["habits"]),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Назад", callback_data="back")]]),
        parse_mode="Markdown"
    )

async def button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = str(q.from_user.id)
    data = load()
    u = get_user(data, uid)
    cb = q.data

    # Отметить / снять привычку
    if cb.startswith("toggle:"):
        hid = int(cb.split(":")[1])
        h = next((x for x in u["habits"] if x["id"] == hid), None)
        if not h: return
        ensure_habit_fields(h)

        if not h["done"] and h.get("track_number"):
            # Спрашиваем число перед тем как отметить выполненной
            user_state[uid] = {"action": "enter_count", "hid": hid}
            save(data)
            await q.edit_message_text(
                f"{h['emoji']} *{h['name']}*\n\nСколько раз/повторений? Введи число:",
                parse_mode="Markdown"
            )
            return

        h["done"] = not h["done"]
        praise = None
        if h["done"]:
            mark_done_today(h)
            praise = random.choice(PRAISE)
            streak = compute_streak(h["history"])
            if streak > 1:
                praise += f"\n🔥 Стрик: {streak} {'день' if streak==1 else 'дня' if streak<5 else 'дней'} подряд!"
        else:
            unmark_today(h)
        save(data)
        await q.edit_message_text(
            main_text(u["habits"]),
            reply_markup=habits_keyboard(u["habits"]),
            parse_mode="Markdown"
        )
        if praise:
            await ctx.bot.send_message(chat_id=q.message.chat_id, text=praise)

    # Статистика
    elif cb == "stats":
        await q.edit_message_text(
            stats_text(u["habits"]),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Назад", callback_data="back")]]),
            parse_mode="Markdown"
        )

    # Переключить учёт числа
    elif cb.startswith("togglecount:"):
        hid = int(cb.split(":")[1])
        for h in u["habits"]:
            if h["id"] == hid:
                ensure_habit_fields(h)
                h["track_number"] = not h["track_number"]
                break
        save(data)
        h = next((x for x in u["habits"] if x["id"] == hid), None)
        if h:
            time_str = f"⏰ Время: {h['time']}" if h.get("time") else "⏰ Время: не задано"
            await q.edit_message_text(f"{h['emoji']} *{h['name']}*\n{time_str}", reply_markup=edit_keyboard(h), parse_mode="Markdown")

    # Добавить привычку
    elif cb == "add":
        user_state[uid] = {"action": "add"}
        await q.edit_message_text(
            "Как называется привычка?\n\n"
            "Можешь сразу указать время через пробел:\n"
            "*Отжимания 07:30*\n\n"
            "Или просто название, время спрошу отдельно:\n"
            "*Выпить воду*",
            parse_mode="Markdown"
        )

    # Настройки
    elif cb == "settings":
        if not u["habits"]:
            await q.answer("Пока нет привычек!", show_alert=True)
            return
        await q.edit_message_text("⚙️ *Настройки*\n\nВыбери привычку:", reply_markup=settings_keyboard(u["habits"]), parse_mode="Markdown")

    # Назад
    elif cb == "back":
        await q.edit_message_text(main_text(u["habits"]), reply_markup=habits_keyboard(u["habits"]), parse_mode="Markdown")

    # Редактировать привычку
    elif cb.startswith("edit:"):
        hid = int(cb.split(":")[1])
        h = next((x for x in u["habits"] if x["id"] == hid), None)
        if not h: return
        time_str = f"⏰ Время: {h['time']}" if h.get("time") else "⏰ Время: не задано"
        await q.edit_message_text(
            f"{h['emoji']} *{h['name']}*\n{time_str}",
            reply_markup=edit_keyboard(h),
            parse_mode="Markdown"
        )

    # Удалить
    elif cb.startswith("delete:"):
        hid = int(cb.split(":")[1])
        u["habits"] = [x for x in u["habits"] if x["id"] != hid]
        save(data)
        reschedule(ctx.application, uid, u["habits"])
        await q.edit_message_text(main_text(u["habits"]), reply_markup=habits_keyboard(u["habits"]), parse_mode="Markdown")

    # Переименовать
    elif cb.startswith("rename:"):
        hid = int(cb.split(":")[1])
        user_state[uid] = {"action": "rename", "hid": hid}
        await q.edit_message_text("Введи новое название:")

    # Установить время
    elif cb.startswith("settime:"):
        hid = int(cb.split(":")[1])
        user_state[uid] = {"action": "settime", "hid": hid}
        await q.edit_message_text("Введи время напоминания в формате *ЧЧ:ММ*\nНапример: `07:30` или `21:00`\n\nЧтобы убрать напоминание — отправь `-`", parse_mode="Markdown")

    # Выбор смайлика — показать панель
    elif cb.startswith("setemoji:"):
        hid = int(cb.split(":")[1])
        await q.edit_message_text("Выбери смайлик:", reply_markup=emoji_keyboard(hid))

    # Смайлик выбран
    elif cb.startswith("emoji:"):
        _, hid, emoji = cb.split(":", 2)
        hid = int(hid)
        for h in u["habits"]:
            if h["id"] == hid:
                h["emoji"] = emoji; break
        save(data)
        h = next((x for x in u["habits"] if x["id"] == hid), None)
        if h:
            time_str = f"⏰ Время: {h['time']}" if h.get("time") else "⏰ Время: не задано"
            await q.edit_message_text(f"{h['emoji']} *{h['name']}*\n{time_str}", reply_markup=edit_keyboard(h), parse_mode="Markdown")

async def message_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    text = update.message.text.strip()
    state = user_state.get(uid)
    if not state:
        await start(update, ctx)
        return

    data = load()
    u = get_user(data, uid)

    if state["action"] == "add":
        name, time_str = parse_name_and_time(text)
        if time_str:
            # Название и время указаны сразу
            habit = {
                "id": u["next_id"],
                "name": name,
                "emoji": "✅",
                "time": time_str,
                "done": False
            }
            u["habits"].append(habit)
            u["next_id"] += 1
            save(data)
            user_state.pop(uid, None)
            reschedule(ctx.application, uid, u["habits"])
            await update.message.reply_text(
                main_text(u["habits"]),
                reply_markup=habits_keyboard(u["habits"]),
                parse_mode="Markdown"
            )
        else:
            # Время не указано — спрашиваем отдельно
            user_state[uid] = {"action": "add_time", "name": name, "emoji": "✅"}
            await update.message.reply_text(
                f"Привычка: *{name}*\n\nТеперь введи время напоминания в формате *ЧЧ:ММ*\nНапример: `07:30`\n\nЕсли напоминание не нужно — отправь `-`",
                parse_mode="Markdown"
            )

    elif state["action"] == "add_time":
        t = text if text != "-" else ""
        if t and not valid_time(t):
            await update.message.reply_text("Неверный формат. Введи время как `07:30` или `-` если не нужно:", parse_mode="Markdown")
            return
        habit = {
            "id": u["next_id"],
            "name": state["name"],
            "emoji": "✅",
            "time": t,
            "done": False
        }
        u["habits"].append(habit)
        u["next_id"] += 1
        save(data)
        user_state.pop(uid, None)
        reschedule(ctx.application, uid, u["habits"])
        await update.message.reply_text(
            main_text(u["habits"]),
            reply_markup=habits_keyboard(u["habits"]),
            parse_mode="Markdown"
        )

    elif state["action"] == "enter_count":
        hid = state["hid"]
        num_match = re.search(r'\d+', text)
        if not num_match:
            await update.message.reply_text("Не понял число. Введи просто цифру, например `20`:", parse_mode="Markdown")
            return
        value = int(num_match.group())
        h = next((x for x in u["habits"] if x["id"] == hid), None)
        if h:
            h["done"] = True
            mark_done_today(h, value)
            save(data)
            user_state.pop(uid, None)
            praise = random.choice(PRAISE) + f"\n{h['emoji']} Записано: {value}"
            streak = compute_streak(h["history"])
            if streak > 1:
                praise += f"\n🔥 Стрик: {streak} {'день' if streak==1 else 'дня' if streak<5 else 'дней'} подряд!"
            await update.message.reply_text(
                main_text(u["habits"]),
                reply_markup=habits_keyboard(u["habits"]),
                parse_mode="Markdown"
            )
            await update.message.reply_text(praise)

    elif state["action"] == "rename":
        hid = state["hid"]
        for h in u["habits"]:
            if h["id"] == hid: h["name"] = text; break
        save(data)
        user_state.pop(uid, None)
        await update.message.reply_text(main_text(u["habits"]), reply_markup=habits_keyboard(u["habits"]), parse_mode="Markdown")

    elif state["action"] == "settime":
        hid = state["hid"]
        t = text if text != "-" else ""
        if t and not valid_time(t):
            await update.message.reply_text("Неверный формат. Введи время как `07:30` или `-` чтобы убрать:", parse_mode="Markdown")
            return
        for h in u["habits"]:
            if h["id"] == hid: h["time"] = t; break
        save(data)
        user_state.pop(uid, None)
        reschedule(ctx.application, uid, u["habits"])
        await update.message.reply_text(main_text(u["habits"]), reply_markup=habits_keyboard(u["habits"]), parse_mode="Markdown")

def valid_time(t):
    try:
        h, m = t.split(":")
        return 0 <= int(h) <= 23 and 0 <= int(m) <= 59
    except: return False

def parse_name_and_time(text):
    """Пытается найти время (ЧЧ:ММ) в конце строки и отделить его от названия."""
    match = re.search(r'(\d{1,2}):(\d{2})\s*$', text)
    if match:
        time_str = f"{int(match.group(1)):02d}:{match.group(2)}"
        if valid_time(time_str):
            name = text[:match.start()].strip(" -,")
            if name:
                return name, time_str
    return text.strip(), None

# ─── Планировщик уведомлений ──────────────────────────────────────────────────
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

def reschedule(app, uid, habits):
    # Удаляем старые джобы этого юзера
    for job in scheduler.get_jobs():
        if job.id.startswith(f"habit_{uid}_"):
            job.remove()
    # Добавляем новые
    for h in habits:
        if h.get("time"):
            try:
                hh, mm = map(int, h["time"].split(":"))
                scheduler.add_job(
                    send_reminder,
                    trigger="cron",
                    hour=hh, minute=mm,
                    args=[app, uid, h["id"]],
                    id=f"habit_{uid}_{h['id']}",
                    replace_existing=True
                )
            except: pass

async def send_reminder(app, uid, hid):
    data = load()
    u = data.get(str(uid))
    if not u: return
    h = next((x for x in u["habits"] if x["id"] == hid), None)
    if not h or h["done"]: return
    text = f"{h['emoji']} *{h['name']}*\n\n{get_funny(h['name'])}"
    try:
        await app.bot.send_message(chat_id=int(uid), text=text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Reminder error: {e}")

async def midnight_reset(app):
    data = load()
    for uid, u in data.items():
        for h in u["habits"]:
            h["done"] = False
    save(data)

def restore_jobs(app):
    data = load()
    for uid, u in data.items():
        reschedule(app, uid, u["habits"])

async def on_startup(app):
    restore_jobs(app)

# ─── Запуск ───────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TOKEN).post_init(on_startup).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    scheduler.add_job(midnight_reset, "cron", hour=0, minute=0, args=[app], id="midnight")
    scheduler.start()

    logging.info("Bot started")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
