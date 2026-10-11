import logging
import os
import sqlite3
from datetime import time

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import NetworkError, TelegramError
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from alerts import (
    expiry_alert_job,
    friday_reminder_job,
    send_expiry_alert,
    send_shopping_reminder,
)
from categories import CATEGORIES, CATEGORY_EMOJI, guess_category
from db import (
    add_item, get_item, init_db, item_exists, list_items, list_shopping,
    list_uncategorized, remove_item, save_chat, set_category, set_status,
    set_status_by_id,
)
from utils import (
    format_date, parse_date, split_items, split_name_and_date, today_ist,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

STATUS_EMOJI = {"ok": "🟢", "low": "🟡", "finished": "🔴"}
PANTRY_PROMPT = "Tap an item to update it:"
MAX_BATCH = 50                                # most items accepted in one message
NAME, CATEGORY, EXPIRY, REMOVE_NAMES = range(4)   # steps of the conversations


# ---------- Screens (functions that build keyboards) ----------

def pantry_keyboard():
    buttons = [
        [InlineKeyboardButton(
            f"{STATUS_EMOJI[row['status']]} {row['name']}",
            callback_data=f"item:{row['id']}",
        )]
        for row in list_items()
    ]
    return InlineKeyboardMarkup(buttons)


def item_keyboard(item_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 OK", callback_data=f"set:{item_id}:ok"),
            InlineKeyboardButton("🟡 Low", callback_data=f"set:{item_id}:low"),
            InlineKeyboardButton("🔴 Finished", callback_data=f"set:{item_id}:finished"),
        ],
        [InlineKeyboardButton("⬅ Back", callback_data="back")],
    ])


def picker_keyboard(status):
    """One button per item; tapping sets that item to `status`."""
    buttons = [
        [InlineKeyboardButton(
            f"{STATUS_EMOJI[row['status']]} {row['name']}",
            callback_data=f"set:{row['id']}:{status}",
        )]
        for row in list_items()
    ]
    return InlineKeyboardMarkup(buttons)


def category_keyboard():
    buttons = [
        InlineKeyboardButton(f"{CATEGORY_EMOJI[name]} {name}", callback_data=f"cat:{index}")
        for index, name in enumerate(CATEGORIES)
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]   # 2 per row
    return InlineKeyboardMarkup(rows)


# ---------- Bulk helpers (plain functions, no Telegram inside) ----------

def add_many(entries):
    """Add several items. Returns (added, skipped, problems)."""
    added, skipped, problems = [], [], []
    for entry in entries:
        name, expiry = split_name_and_date(entry)
        if expiry and expiry < today_ist():
            problems.append(f"{name} (expiry date is in the past)")
            continue
        category = guess_category(name) or "Other"
        expiry_iso = expiry.isoformat() if expiry else None
        try:
            if add_item(name, category, expiry_iso):
                added.append((name, category, expiry_iso))
            else:
                skipped.append(name)
        except sqlite3.Error:
            logger.exception("Could not add %s", name)
            problems.append(f"{name} (database error)")
    return added, skipped, problems


def remove_many(names):
    """Remove several items. Returns (removed, missing, problems)."""
    removed, missing, problems = [], [], []
    for name in names:
        try:
            if remove_item(name) > 0:
                removed.append(name)
            else:
                missing.append(name)
        except sqlite3.Error:
            logger.exception("Could not remove %s", name)
            problems.append(f"{name} (database error)")
    return removed, missing, problems


def add_summary(added, skipped, problems):
    lines = []
    if added:
        lines.append(f"✅ Added {len(added)}:")
        for name, category, expiry_iso in added:
            expiry = f" (exp {format_date(expiry_iso)})" if expiry_iso else ""
            lines.append(f"   {CATEGORY_EMOJI[category]} {name}{expiry}")
        others = [name for name, category, _ in added if category == "Other"]
        if others:
            lines.append(f"\n📦 Filed under Other: {', '.join(others)}")
    if skipped:
        lines.append(f"\n↩ Already in your pantry: {', '.join(skipped)}")
    if problems:
        lines.append("\n⚠ Skipped: " + "; ".join(problems))
    return "\n".join(lines) or "Nothing to add."


def remove_summary(removed, missing, problems):
    lines = []
    if removed:
        lines.append(f"🗑 Removed {len(removed)}: {', '.join(removed)}")
    if missing:
        lines.append(f"❓ Not found: {', '.join(missing)}")
    if problems:
        lines.append("⚠ Skipped: " + "; ".join(problems))
    return "\n".join(lines) or "Nothing to remove."


# ---------- Simple commands ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_chat(update.effective_chat.id)   # this chat will receive alerts
    await update.message.reply_text(
        "Hi! I'm your pantry assistant.\n\n"
        "/add  – add items. Several at once: /add rice, onion, milk 15-10-2026\n"
        "/remove  – remove items: /remove onion, milk\n"
        "/pantry  – tap to update items\n"
        "/list  – items by category\n"
        "/shopping  – what to buy\n"
        "/low  /finished  /restocked  – update an item\n"
        "/categorize  – sort items that have no category\n"
        "/testalerts  – send the alerts now (test)"
    )


async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = list_items()
    if not items:
        await update.message.reply_text("Your pantry is empty. Add something with /add")
        return

    groups = {}
    for row in items:
        groups.setdefault(row["category"] or "Uncategorised", []).append(row)

    lines = []
    for category, rows in groups.items():
        lines.append(f"{CATEGORY_EMOJI.get(category, '📦')} {category}")
        for row in rows:
            expiry = f" (exp {format_date(row['expiry_on'])})" if row["expiry_on"] else ""
            lines.append(f"   {STATUS_EMOJI[row['status']]} {row['name']}{expiry}")
        lines.append("")
    await update.message.reply_text("\n".join(lines).strip())


async def change_status(update, context, status, wording):
    name = " ".join(context.args).strip()
    if not name:
        if not list_items():
            await update.message.reply_text("Your pantry is empty. Add something with /add")
            return
        await update.message.reply_text(
            f"Which item is {wording}? Tap one:", reply_markup=picker_keyboard(status)
        )
        return
    if set_status(name, status) == 0:
        await update.message.reply_text(f"I couldn't find '{name}'. Add it first with /add {name}")
    else:
        await update.message.reply_text(f"Marked {name} as {wording}.")


async def low(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await change_status(update, context, "low", "running low")


async def finished(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await change_status(update, context, "finished", "finished")


async def restocked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await change_status(update, context, "ok", "back in stock")


async def shopping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = list_shopping()
    if not items:
        await update.message.reply_text("Nothing to buy right now 🎉")
        return
    lines = [f"{STATUS_EMOJI[row['status']]} {row['name']}" for row in items]
    await update.message.reply_text("🛒 Shopping list:\n" + "\n".join(lines))


async def pantry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not list_items():
        await update.message.reply_text("Your pantry is empty. Add something with /add")
        return
    await update.message.reply_text(PANTRY_PROMPT, reply_markup=pantry_keyboard())


async def categorize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = list_uncategorized()
    if not rows:
        await update.message.reply_text("All items already have a category ✅")
        return
    done = []
    for row in rows:
        category = guess_category(row["name"]) or "Other"
        set_category(row["id"], category)
        done.append(f"• {row['name']} → {category}")
    await update.message.reply_text("Sorted:\n" + "\n".join(done))


async def test_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Sending test alerts to all saved chats...")
    await send_expiry_alert(context.bot)
    await send_shopping_reminder(context.bot)


# ---------- The /add and /remove conversations ----------

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Use the raw text (not context.args) so line breaks are kept.
    parts = update.message.text.split(maxsplit=1)
    if len(parts) > 1:
        return await handle_add_text(update, context, parts[1])
    await update.message.reply_text(
        "What would you like to add?\n"
        "Send one item, or several separated by commas or new lines.\n"
        "Tip: put an expiry date after a name, like: milk 15-10-2026\n"
        "(send /cancel to stop)"
    )
    return NAME


async def add_got_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_add_text(update, context, update.message.text)


async def handle_add_text(update, context, text):
    chat = update.effective_chat
    entries = split_items(text)
    if not entries:
        await chat.send_message("Please type at least one item, e.g. rice, onion")
        return NAME
    if len(entries) > MAX_BATCH:
        await chat.send_message(f"That's a lot! Please send at most {MAX_BATCH} items at a time.")
        return NAME

    one_plain_item = len(entries) == 1 and split_name_and_date(entries[0])[1] is None
    if one_plain_item:
        return await process_name(update, context, entries[0])   # ask for details

    added, skipped, problems = add_many(entries)
    await chat.send_message(add_summary(added, skipped, problems))
    return ConversationHandler.END


async def process_name(update, context, name):
    chat = update.effective_chat
    if item_exists(name):
        await chat.send_message(f"{name} is already in your pantry.")
        return ConversationHandler.END

    context.user_data["new_item"] = {"name": name}
    category = guess_category(name)
    if category is None:
        await chat.send_message(
            f"I'm not sure which category '{name}' belongs to. Please choose:",
            reply_markup=category_keyboard(),
        )
        return CATEGORY

    context.user_data["new_item"]["category"] = category
    return await ask_expiry(update, context)


async def add_got_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        category = CATEGORIES[int(query.data.split(":")[1])]
    except (ValueError, IndexError):
        return CATEGORY                   # ignore a bad button, stay on this step

    item = context.user_data.get("new_item")
    if item is None:
        await query.edit_message_text("Something went wrong. Please start again with /add.")
        return ConversationHandler.END

    item["category"] = category
    await query.edit_message_text(f"Category: {CATEGORY_EMOJI[category]} {category}")
    return await ask_expiry(update, context)


async def ask_expiry(update, context):
    item = context.user_data["new_item"]
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Skip (no expiry date)", callback_data="skip_expiry")]]
    )
    await update.effective_chat.send_message(
        f"{item['name']} → {CATEGORY_EMOJI[item['category']]} {item['category']}\n\n"
        "When does it expire? Send a date like 25-12-2026, or tap Skip.",
        reply_markup=keyboard,
    )
    return EXPIRY


async def add_got_expiry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    expiry = parse_date(update.message.text)
    if expiry is None:
        await update.message.reply_text(
            "I couldn't read that date. Please use DD-MM-YYYY, e.g. 25-12-2026, or tap Skip."
        )
        return EXPIRY
    if expiry < today_ist():
        await update.message.reply_text("That date is in the past. Please send a future date, or tap Skip.")
        return EXPIRY
    return await finish_add(update, context, expiry)


async def add_skip_expiry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(reply_markup=None)   # remove the button
    return await finish_add(update, context, None)


async def finish_add(update, context, expiry):
    chat = update.effective_chat
    item = context.user_data.pop("new_item", None)
    if item is None:
        await chat.send_message("Something went wrong. Please start again with /add.")
        return ConversationHandler.END

    expiry_iso = expiry.isoformat() if expiry else None
    if not add_item(item["name"], item["category"], expiry_iso):
        await chat.send_message(f"{item['name']} is already in your pantry.")
        return ConversationHandler.END

    text = f"Added {item['name']} ✅  ({CATEGORY_EMOJI[item['category']]} {item['category']})"
    if expiry:
        text += f"\nExpires: {format_date(expiry_iso)}"
    await chat.send_message(text)
    return ConversationHandler.END


async def remove_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = update.message.text.split(maxsplit=1)
    if len(parts) > 1:
        return await handle_remove_text(update, parts[1])
    await update.message.reply_text(
        "Which items should I remove?\n"
        "Send names separated by commas or new lines. (/cancel to stop)"
    )
    return REMOVE_NAMES


async def remove_got_names(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await handle_remove_text(update, update.message.text)


async def handle_remove_text(update, text):
    chat = update.effective_chat
    names = split_items(text)
    if not names:
        await chat.send_message("Please send at least one item name.")
        return REMOVE_NAMES
    if len(names) > MAX_BATCH:
        await chat.send_message(f"Please send at most {MAX_BATCH} items at a time.")
        return REMOVE_NAMES

    removed, missing, problems = remove_many(names)
    await chat.send_message(remove_summary(removed, missing, problems))
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("new_item", None)
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


# ---------- Button taps for /pantry and the pickers ----------

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back":
        await query.edit_message_text(PANTRY_PROMPT, reply_markup=pantry_keyboard())

    elif data.startswith("item:"):
        try:
            item_id = int(data.split(":")[1])
        except ValueError:
            return
        item = get_item(item_id)
        if item is None:
            await query.edit_message_text("That item no longer exists.")
            return
        await query.edit_message_text(
            f"{item['name']} is currently {item['status']}. Choose a new status:",
            reply_markup=item_keyboard(item_id),
        )

    elif data.startswith("set:"):
        try:
            _, item_id, status = data.split(":")
            item_id = int(item_id)
        except ValueError:
            return
        if status not in STATUS_EMOJI:
            return
        set_status_by_id(item_id, status)
        await query.edit_message_text(
            "Updated ✅  " + PANTRY_PROMPT, reply_markup=pantry_keyboard()
        )


# ---------- Safety net for unexpected errors ----------

async def on_error(update, context: ContextTypes.DEFAULT_TYPE):
    error = context.error
    if isinstance(error, NetworkError):
        logger.warning("Network problem (the bot will keep retrying): %s", error)
        return
    logger.error("Unhandled error", exc_info=error)
    if isinstance(update, Update) and update.effective_chat:
        try:
            await update.effective_chat.send_message("Sorry, something went wrong. Please try again.")
        except TelegramError:
            pass


# ---------- Scheduling ----------

def schedule_jobs(app):
    if app.job_queue is None:
        logger.warning(
            'Alerts are OFF. Install the scheduler: python -m pip install "python-telegram-bot[job-queue]"'
        )
        return
    # The scheduler uses UTC. IST = UTC + 5:30.
    app.job_queue.run_daily(expiry_alert_job, time=time(hour=3, minute=30), name="expiry_alert")      # 09:00 IST
    app.job_queue.run_daily(friday_reminder_job, time=time(hour=11, minute=30), name="friday_reminder")  # 17:00 IST


def main():
    if not TOKEN:
        raise SystemExit("BOT_TOKEN not found. Check that .env is in this folder and contains BOT_TOKEN=...")

    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    # ONE conversation handles both /add and /remove, so they can't get mixed up.
    pantry_conversation = ConversationHandler(
        entry_points=[
            CommandHandler("add", add_start),
            CommandHandler("remove", remove_start),
        ],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_got_name)],
            CATEGORY: [CallbackQueryHandler(add_got_category, pattern=r"^cat:")],
            EXPIRY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_got_expiry),
                CallbackQueryHandler(add_skip_expiry, pattern=r"^skip_expiry$"),
            ],
            REMOVE_NAMES: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_got_names)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(pantry_conversation)       # must come before the general button handler
    app.add_handler(CommandHandler("list", show_list))
    app.add_handler(CommandHandler("low", low))
    app.add_handler(CommandHandler("finished", finished))
    app.add_handler(CommandHandler("restocked", restocked))
    app.add_handler(CommandHandler("shopping", shopping))
    app.add_handler(CommandHandler("pantry", pantry))
    app.add_handler(CommandHandler("categorize", categorize))
    app.add_handler(CommandHandler("testalerts", test_alerts))
    app.add_handler(CallbackQueryHandler(on_button, pattern=r"^(item:|set:|back$)"))
    app.add_error_handler(on_error)

    schedule_jobs(app)
    logger.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling(bootstrap_retries=-1)


if __name__ == "__main__":
    main()