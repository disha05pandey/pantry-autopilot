import logging
from datetime import timedelta

from telegram.error import TelegramError

from db import get_chats, items_expiring_on, list_shopping
from utils import today_ist

logger = logging.getLogger(__name__)


async def broadcast(bot, text):
    """Send one message to every saved chat. One failure never stops the rest."""
    chats = get_chats()
    if not chats:
        logger.info("No chats saved yet. Send /start to the bot first.")
        return
    for chat_id in chats:
        try:
            await bot.send_message(chat_id=chat_id, text=text)
        except TelegramError as error:
            logger.warning("Could not message chat %s: %s", chat_id, error)


async def send_expiry_alert(bot):
    tomorrow = today_ist() + timedelta(days=1)
    items = items_expiring_on(tomorrow.isoformat())
    if not items:
        return
    lines = [f"• {row['name']}" for row in items]
    await broadcast(bot, "⏰ Expiring tomorrow:\n" + "\n".join(lines) + "\n\nUse them up today!")


async def send_shopping_reminder(bot):
    items = list_shopping()
    if not items:
        return
    finished = [row["name"] for row in items if row["status"] == "finished"]
    low = [row["name"] for row in items if row["status"] == "low"]

    parts = ["🛒 Friday shopping reminder"]
    if finished:
        parts.append("🔴 Finished:\n" + "\n".join(f"• {name}" for name in finished))
    if low:
        parts.append("🟡 Running low:\n" + "\n".join(f"• {name}" for name in low))
    await broadcast(bot, "\n\n".join(parts))


# ----- Jobs: these are what the scheduler calls -----

async def expiry_alert_job(context):
    try:
        await send_expiry_alert(context.bot)
    except Exception:
        logger.exception("Expiry alert job failed")


async def friday_reminder_job(context):
    try:
        if today_ist().weekday() != 4:   # Monday=0 ... Friday=4
            return
        await send_shopping_reminder(context.bot)
    except Exception:
        logger.exception("Friday reminder job failed")