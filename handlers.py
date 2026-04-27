import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from database import Database

logger = logging.getLogger(__name__)

db = Database()

# Состояния ConversationHandler
ADDING_TASK, EDITING_TASK = range(2)

# --- Вспомогательные функции ---

NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def num_emoji(n: int) -> str:
    return NUMBER_EMOJIS[n - 1] if 1 <= n <= 10 else f"{n}."


def build_list_keyboard(tasks: list) -> InlineKeyboardMarkup:
    rows = []
    for task in tasks:
        toggle_btn = (
            InlineKeyboardButton("↩️", callback_data=f"undo:{task['id']}")
            if task["completed"]
            else InlineKeyboardButton("✅", callback_data=f"done:{task['id']}")
        )
        rows.append([
            toggle_btn,
            InlineKeyboardButton("🗑️", callback_data=f"delete:{task['id']}"),
            InlineKeyboardButton("📝", callback_data=f"edit:{task['id']}"),
        ])
    return InlineKeyboardMarkup(rows)


def format_task_line(index: int, task: dict) -> str:
    status = "✅" if task["completed"] else "❌"
    return f"{num_emoji(index)} {status} {task['text']}"


def format_full_list(tasks: list, filter: str | None = None) -> str:
    header = {
        "active": f"❌ <b>Активные задачи ({len(tasks)}):</b>",
        "completed": f"✅ <b>Выполненные задачи ({len(tasks)}):</b>",
    }.get(filter, f"📋 <b>Все твои задачи ({len(tasks)}):</b>")
    lines = [header, ""]
    for i, task in enumerate(tasks, 1):
        lines.append(format_task_line(i, task))
    lines += ["", "✅ выполнить  🗑️ удалить  📝 редактировать"]
    return "\n".join(lines)


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    buttons = [
        ["📋 /list", "➕ /add"],
        ["❌ /active", "✅ /completed"],
        ["📊 /stats", "🗑️ /clear"],
        ["❓ /help"],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


# --- Команды ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.register_user(user.id, user.username)
    logger.info("Пользователь %s запустил бота", user.id)
    await update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n\n"
        "Я твой персональный Todo-бот. Помогу не забыть ни одну задачу!\n\n"
        "📌 Основные команды:\n"
        "➕ /add — добавить задачу\n"
        "📋 /list — список всех задач\n"
        "❌ /active — только активные\n"
        "✅ /completed — только выполненные\n"
        "📊 /stats — статистика\n"
        "🗑️ /clear — удалить все задачи\n"
        "❓ /help — помощь\n\n"
        "Начни с команды /add!",
        reply_markup=main_menu_keyboard(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ <b>Справка по командам:</b>\n\n"
        "/start — главное меню\n"
        "/add — добавить новую задачу\n"
        "/list — все задачи с кнопками управления\n"
        "/active — только невыполненные задачи\n"
        "/completed — только выполненные задачи\n"
        "/stats — статистика по задачам\n"
        "/clear — удалить все задачи\n"
        "/cancel — отменить текущее действие\n\n"
        "💡 В списке задач нажимай кнопки под каждой задачей:\n"
        "✅ — отметить выполненной\n"
        "↩️ — вернуть в активные\n"
        "🗑️ — удалить задачу\n"
        "📝 — редактировать текст",
        parse_mode="HTML",
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    s = db.get_stats(user_id)
    await update.message.reply_text(
        f"📊 <b>Твоя статистика:</b>\n\n"
        f"📝 Всего задач: <b>{s['total']}</b>\n"
        f"❌ Активных: <b>{s['active']}</b>\n"
        f"✅ Выполненных: <b>{s['completed']}</b>\n"
        f"🏆 Выполнено: <b>{s['percent']}%</b>",
        parse_mode="HTML",
    )


async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE, filter: str | None = None):
    user_id = update.effective_user.id
    tasks = db.get_tasks(user_id, filter=filter)

    if not tasks:
        label = {"active": "активных", "completed": "выполненных"}.get(filter, "")
        await update.message.reply_text(
            f"📭 У тебя пока нет {label} задач.\n"
            "Добавь первую с помощью /add!"
        )
        return

    await update.message.reply_text(
        format_full_list(tasks, filter),
        parse_mode="HTML",
        reply_markup=build_list_keyboard(tasks),
    )


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await list_tasks(update, context)


async def active_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await list_tasks(update, context, filter="active")


async def completed_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await list_tasks(update, context, filter="completed")


# --- Диалог добавления задачи ---

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 Введи текст задачи:")
    return ADDING_TASK


async def receive_task_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("⚠️ Текст не может быть пустым. Попробуй ещё раз:")
        return ADDING_TASK
    user_id = update.effective_user.id
    task_id = db.add_task(user_id, text)
    await update.message.reply_text(
        f"✅ Задача добавлена!\n\n📝 <b>{text}</b>\n\n"
        "Смотри все задачи с помощью /list",
        parse_mode="HTML",
    )
    return ConversationHandler.END


# --- Диалог редактирования задачи ---

async def edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split(":")[1])
    context.user_data["editing_task_id"] = task_id
    task = db.get_task(task_id, query.from_user.id)
    if not task:
        await query.edit_message_text("⚠️ Задача не найдена.")
        return ConversationHandler.END
    await query.edit_message_text(
        f"📝 Редактирую задачу:\n<b>{task['text']}</b>\n\nВведи новый текст:",
        parse_mode="HTML",
    )
    return EDITING_TASK


async def receive_edit_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_text = update.message.text.strip()
    if not new_text:
        await update.message.reply_text("⚠️ Текст не может быть пустым. Попробуй ещё раз:")
        return EDITING_TASK
    task_id = context.user_data.get("editing_task_id")
    user_id = update.effective_user.id
    if db.edit_task(task_id, user_id, new_text):
        await update.message.reply_text(
            f"✅ Задача обновлена!\n\n📝 <b>{new_text}</b>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("⚠️ Не удалось обновить задачу.")
    context.user_data.pop("editing_task_id", None)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Действие отменено.")
    return ConversationHandler.END


# --- Команда /clear ---

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tasks = db.get_tasks(user_id)
    if not tasks:
        await update.message.reply_text("📭 У тебя нет задач для удаления.")
        return
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Да, удалить всё", callback_data="clear_confirm"),
            InlineKeyboardButton("❌ Отмена", callback_data="clear_cancel"),
        ]
    ])
    await update.message.reply_text(
        f"⚠️ Ты уверен? Будут удалены все <b>{len(tasks)}</b> задач(и).",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


# --- Обработчики inline-кнопок ---

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    try:
        if data.startswith("done:") or data.startswith("undo:"):
            task_id = int(data.split(":")[1])
            db.toggle_task(task_id, user_id)
            tasks = db.get_tasks(user_id)
            if tasks:
                await query.edit_message_text(
                    format_full_list(tasks),
                    parse_mode="HTML",
                    reply_markup=build_list_keyboard(tasks),
                )
            else:
                await query.edit_message_text("📭 Задач больше нет. Добавь новую с помощью /add!")

        elif data.startswith("delete:"):
            task_id = int(data.split(":")[1])
            task = db.get_task(task_id, user_id)
            task_text = task["text"] if task else "?"
            if db.delete_task(task_id, user_id):
                tasks = db.get_tasks(user_id)
                if tasks:
                    await query.edit_message_text(
                        f"🗑️ <b>{task_text}</b> удалена.\n\n" + format_full_list(tasks),
                        parse_mode="HTML",
                        reply_markup=build_list_keyboard(tasks),
                    )
                else:
                    await query.edit_message_text("🗑️ Задача удалена. Список пуст!")
            else:
                await query.edit_message_text("⚠️ Задача не найдена.")

        elif data == "clear_confirm":
            count = db.clear_tasks(user_id)
            await query.edit_message_text(f"🗑️ Удалено задач: <b>{count}</b>. Список очищен!", parse_mode="HTML")

        elif data == "clear_cancel":
            await query.edit_message_text("❌ Удаление отменено.")

    except Exception as e:
        logger.error("Ошибка в callback_handler: %s", e)
        await query.edit_message_text("⚠️ Произошла ошибка. Попробуй ещё раз.")


# --- Сборка хендлеров ---

def get_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("add", add_start),
            CallbackQueryHandler(edit_start, pattern=r"^edit:\d+$"),
        ],
        states={
            ADDING_TASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task_text)],
            EDITING_TASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edit_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )


def register_handlers(application):
    application.add_handler(get_conversation_handler())
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CommandHandler("active", active_command))
    application.add_handler(CommandHandler("completed", completed_command))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CallbackQueryHandler(callback_handler))
