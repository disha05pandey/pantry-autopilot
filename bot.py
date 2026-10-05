import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from db import init_db, add_item, list_items

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi! I'm your pantry assistant.\nTry: /add rice  or  /list"
    )


async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = " ".join(context.args).strip()
    if not name:
        await update.message.reply_text("Usage: /add rice")
        return
    add_item(name)
    await update.message.reply_text(f"Added {name} ✅")


async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = list_items()
    if not items:
        await update.message.reply_text("Your pantry is empty.")
        return
    lines = [f"• {row['name']} ({row['status']})" for row in items]
    await update.message.reply_text("\n".join(lines))


def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("list", show_list))
    app.run_polling()


if __name__ == "__main__":
    main()

