import os
from dotenv import load_dotenv

load_dotenv()

# טוקן הבוט של Tachborabot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8738080530:AAGUQMcYuv6UxX1UCQC4fV7yijnIVuYZCr4")

# יעדי הדיווח
MOT_EMAIL = os.getenv("MOT_EMAIL", "pniotcrm@mot.gov.il")
JERUSALEM_TRANSPORT_EMAIL = os.getenv("JERUSALEM_TRANSPORT_EMAIL", "david_zo@jerusalem.muni.il")

# שרת דוא"ל (SMTP) - במידה ומוגדר ישלח מייל ישירות; אם לא מוגדר ייצר תבנית לשליחה
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")

# כתובת מאגר משרד התחבורה (Open Bus Stride API)
STRIDE_API_BASE = "https://open-bus-stride-api.hasadna.org.il"
