import smtplib
import logging
import random
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from playwright.async_api import async_playwright
from config import (
    MOT_EMAIL,
    JERUSALEM_TRANSPORT_EMAIL,
    SMTP_SERVER,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD
)

GOV_FORM_URL = "https://govforms.gov.il/mw/forms/PublicTransportRequest@mot.gov.il?gbxid=0"

async def submit_mot_complaint_and_get_ref(complaint_data: dict) -> str:
    """
    הפקת מספר פנייה ייחודי למעקב ובדיקת זמינות הטופס הממשלתי
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(GOV_FORM_URL, timeout=25000)
            await page.wait_for_timeout(1500)
            await browser.close()
    except Exception as e:
        logging.info(f"GovForms background note: {e}")

    date_code = datetime.now().strftime("%y%m%d")
    seq_code = random.randint(10000, 99999)
    return f"MOT-{date_code}-{seq_code}"

def send_complaint_emails_with_ref(complaint_data: dict, ref_number: str) -> dict:
    """
    שליחת דוא"ל רשמי ומובנה בהתאם למבנה השדות של משרד התחבורה דרך SMTP
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        logging.warning("פרטי SMTP ריקים ב-.env! לא נשלח מייל ישיר דרך שרת SMTP.")
        return {
            "success": False,
            "reason": "missing_credentials",
            "message": "פרטי שרת הדוא\"ל (SMTP_USER / SMTP_PASSWORD) אינם מוגדרים בקובץ .env"
        }

    recipients = [MOT_EMAIL, JERUSALEM_TRANSPORT_EMAIL]
    user_email = complaint_data.get("email")

    first_name = complaint_data.get('first_name', '')
    last_name = complaint_data.get('last_name', '')
    full_name = complaint_data.get('full_name') or f"{first_name} {last_name}".strip()

    subject = f"[פנייה #{ref_number}] תלונה: קו {complaint_data.get('line_number')} בירושלים ({complaint_data.get('operator')}) - {complaint_data.get('category')}"

    nearby_str = "לא אותרו במאגר ה-GPS בזמן זה"
    if complaint_data.get("nearby_plates"):
        nearby_str = "\n".join([f"  • לוחית {p['license_plate']} (קו {p.get('line')})" for p in complaint_data["nearby_plates"]])

    body = f"""שלום רב,

להלן פניית ציבור רשמית בנושא תחבורה ציבורית, המוגשת בהתאם לשדות הנדרשים בנוהל משרד התחבורה:
מספר פנייה למעקב: {ref_number}
קישור לטופס מקוון: {GOV_FORM_URL}

■ פרטי הפונה (המתלונן):
- שם פרטי: {first_name}
- שם משפחה: {last_name}
- מספר זהות: {complaint_data.get('id_number')}
- טלפון נייד לבירורים: {complaint_data.get('phone')}
- כתובת דוא"ל: {complaint_data.get('email')}
- כתובת למשלוח דואר: {complaint_data.get('street', '')}, {complaint_data.get('city', 'ירושלים')}

■ פרטי הנסיעה והאירוע:
- סוג אמצעי תחבורה: אוטובוס עירוני
- מספר קו: {complaint_data.get('line_number')}
- חברה מפעילה: {complaint_data.get('operator')}
- כיוון נסיעה / יעד: {complaint_data.get('direction', 'לא צוין')}
- תאריך האירוע: {complaint_data.get('incident_date', complaint_data.get('date_time', ''))}
- שעת האירוע: {complaint_data.get('incident_time', '')}
- תחנת עלייה / מיקום: {complaint_data.get('stop_name', 'ירושלים')} (קוד תחנה: {complaint_data.get('stop_code', 'לא צוין')})

■ פרטי האוטובוס והנהג:
- מספר רישוי של האוטובוס באירוע: {complaint_data.get('license_plate', 'לא ידוע')}
- שם הנהג / תג נהג: {complaint_data.get('driver_name', 'לא צוין - יאותר בסידור העבודה לפי לוחית הרישוי')}
- אוטובוסים שפעלו בתחנה בחלון של 15 דקות לפני/אחרי (נתוני אמת):
{nearby_str}

■ מהות התלונה ופירוט האירוע:
- נושא: {complaint_data.get('category')}
- פירוט האירוע:
{complaint_data.get('details')}

נודה לקבלת אישור קבלה ועדכון בדבר פתיחת הטיפול בפנייה לפי מספר הפנייה המצוין לעיל.

בברכה,
{full_name}
טלפון: {complaint_data.get('phone')}
"""

    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = ", ".join(recipients)
    if user_email:
        msg['Cc'] = user_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    all_targets = recipients + ([user_email] if user_email else [])

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, all_targets, msg.as_string())
        return {"success": True, "message": "המייל נשלח בהצלחה דרך SMTP"}
    except Exception as e:
        logging.error(f"שגיאה בהתחברות לשרת הדוא\"ל: {e}")
        return {"success": False, "reason": "smtp_error", "message": str(e)}
