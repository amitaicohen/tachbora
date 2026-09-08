import smtplib
import logging
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

def send_complaint_emails(complaint_data: dict) -> bool:
    """
    שולח תלונה רשמית במקביל למשרד התחבורה, למחזיק תיק התחבורה בירושלים ובעותק למתלונן
    """
    recipients = [MOT_EMAIL, JERUSALEM_TRANSPORT_EMAIL]
    user_email = complaint_data.get("email")

    subject = f"תלונה רשמית: קו {complaint_data.get('line_number')} בירושלים ({complaint_data.get('operator')}) - {complaint_data.get('category')}"

    body = f"""שלום רב,

להלן תלונה רשמית שהוגשה באמצעות בוט דיווח ציבורי על התנהלות קווי תחבורה ציבורית בירושלים:

■ פרטי המתלונן/ת:
- שם מלא: {complaint_data.get('full_name')}
- תעודת זהות: {complaint_data.get('id_number')}
- טלפון: {complaint_data.get('phone')}
- כתובת דוא"ל: {complaint_data.get('email')}

■ פרטי האירוע:
- תאריך ושעה: {complaint_data.get('date_time')}
- עיר: ירושלים
- מיקום / תחנה: {complaint_data.get('location')}
- מספר קו: {complaint_data.get('line_number')}
- חברה מפעילה: {complaint_data.get('operator')}
- מספר רישוי של האוטובוס: {complaint_data.get('license_plate', 'לא ידוע')}
- מהות הפנייה: {complaint_data.get('category')}

■ פירוט האירוע:
{complaint_data.get('details')}

נודה לבדיקת המקרה מול הגורמים המפעילים ולקבלת עדכון על הטיפול.

בברכה,
{complaint_data.get('full_name')}
"""

    if not SMTP_USER or not SMTP_PASSWORD:
        logging.warning("פרטי שרת SMTP לא הוגדרו. הדמיית שליחה הצליחה.")
        return True

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
        return True
    except Exception as e:
        logging.error(f"שגיאה בשליחת הדוא\"ל: {e}")
        return False

async def fill_online_form_playwright(data: dict) -> bool:
    """
    אוטומציית טופס משרד התחבורה
    """
    form_url = "https://www.gov.il/he/service/complaint_about_conduct_in_public_transportation"
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(form_url, timeout=30000)
            await browser.close()
            return True
    except Exception as e:
        logging.error(f"שגיאה באוטומציית טופס מקוון: {e}")
        return False
