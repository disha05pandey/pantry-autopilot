import re
from datetime import date, datetime, timedelta, timezone

# India Standard Time = UTC + 5:30 (no daylight saving)
IST = timezone(timedelta(hours=5, minutes=30))


def today_ist() -> date:
    return datetime.now(IST).date()


def parse_date(text):
    """Turn '25-12-2026' (or 25/12/2026, 25.12.2026) into a date, or None."""
    cleaned = text.strip().replace("/", "-").replace(".", "-")
    try:
        return datetime.strptime(cleaned, "%d-%m-%Y").date()
    except ValueError:
        return None


def format_date(iso_text):
    """Turn '2026-12-25' into '25-12-2026' for display."""
    if not iso_text:
        return ""
    try:
        return datetime.strptime(iso_text, "%Y-%m-%d").strftime("%d-%m-%Y")
    except ValueError:
        return iso_text


def split_items(text):
    """'rice, toor dal\\n- onion' -> ['rice', 'toor dal', 'onion'] (no blanks, no repeats)."""
    parts = re.split(r"[,\n;]+", text)
    cleaned = []
    seen = set()
    for part in parts:
        name = " ".join(part.split())          # collapse extra spaces
        name = name.lstrip("-•* ")             # drop bullet marks
        key = name.lower()
        if name and key not in seen:
            seen.add(key)
            cleaned.append(name)
    return cleaned


def split_name_and_date(entry):
    """'milk 15-10-2026' -> ('milk', date). 'rice' -> ('rice', None)."""
    words = entry.split()
    if len(words) > 1:
        possible_date = parse_date(words[-1])
        if possible_date:
            return " ".join(words[:-1]), possible_date
    return entry, None