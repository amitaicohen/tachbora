import re
from datetime import datetime, timedelta

HEBREW_DAYS = {
    "ראשון": 6,   # Sunday in Python weekday: Mon=0, Sun=6
    "שני": 0,     # Monday
    "שלישי": 1,   # Tuesday
    "רביעי": 2,   # Wednesday
    "חמישי": 3,   # Thursday
    "שישי": 4,    # Friday
    "שבת": 5      # Saturday
}

def parse_hebrew_datetime(text: str) -> datetime:
    """
    מפענח ביטויים כמו 'חמישי ב-7:20', 'אתמול ב-08:30', 'היום ב-14:15', '12/09 ב-10:00'
    ומחזיר אובייקט datetime מלא.
    """
    now = datetime.now()
    text = text.strip()

    # חילוץ שעה ודקות
    time_match = re.search(r'(\d{1,2})[:.](\d{2})', text)
    hour = int(time_match.group(1)) if time_match else now.hour
    minute = int(time_match.group(2)) if time_match else now.minute

    target_date = now.date()

    if "אתמול" in text:
        target_date = now.date() - timedelta(days=1)
    elif "שלשום" in text:
        target_date = now.date() - timedelta(days=2)
    elif "היום" in text:
        target_date = now.date()
    else:
        # בדיקה של יום בשבוע (לדוגמה 'חמישי האחרון' או 'חמישי ב-7:20')
        day_found = False
        for day_name, day_idx in HEBREW_DAYS.items():
            if day_name in text:
                # מציאת יום זה בשבוע שחלף
                current_weekday = now.weekday()
                days_ago = (current_weekday - day_idx) % 7
                if days_ago == 0 and (hour > now.hour or (hour == now.hour and minute > now.minute)):
                    # אם זה אותו יום בשבוע אך שעה עתידית, הכוונה לשבוע שעבר
                    days_ago = 7
                elif days_ago == 0 and "היום" not in text and "האחרון" in text:
                    days_ago = 7
                target_date = now.date() - timedelta(days=days_ago)
                day_found = True
                break

        if not day_found:
            # בדיקת תאריך מפורש כגון 10/09 או 10.09
            date_match = re.search(r'(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?', text)
            if date_match:
                d = int(date_match.group(1))
                m = int(date_match.group(2))
                y = int(date_match.group(3)) if date_match.group(3) else now.year
                if y < 100:
                    y += 2000
                try:
                    target_date = datetime(y, m, d).date()
                except ValueError:
                    pass

    return datetime(target_date.year, target_date.month, target_date.day, hour, minute)
