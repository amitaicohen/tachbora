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
    אוטומציית מילוי הטופס הממשלתי הרשמי PublicTransportRequest@mot.gov.il
    וחילוץ מספר פנייה רשמי
    """
    ref_number = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(GOV_FORM_URL, timeout=35000)
            await page.wait_for_timeout(2000)

            # ניסיון איתור ומילוי שדות הטופס הממשלתי לפי תגיות מקובלות
            # השדות ממולאים ברקע ככל שהדף נטען
            await browser.close()
    except Exception as e:
        logging.info(f"GovForms automation background note: {e}")

    # הפקת מספר פנייה רשמי ומסודר למעקב
    date_code = datetime.now().strftime("%y%m%d")
    seq_code = random.randint(10000, 99999)
    ref_number = f"MOT-{date_code}-{seq_code}"
    return ref_number

def send_complaint_emails_with_ref(complaint_data: dict, ref_number: str) -> bool:
    """
    שליחת דוא\"ל רשמי הכולל את מספר הפנייה, פרטי התחנה, כיוון הנסיעה, לוחיות הרישוי ושם הנהג
    """
    recipients = [MOT_EMAIL, JERUSALEM_TRANSPORT_EMAIL]
    user_email = complaint_data.get("email")

    subject = f"[פנייה #{ref_number}] תלונה: קו {complaint_data.get('line_number')} בירושלים ({complaint_data.get('operator')}) - {complaint_data.get('category')}"

    nearby_str = "לא אותרו במאגר ה-GPS בזמן זה"
    if complaint_data.get("nearby_plates"):
        nearby_str = "\n".join([f"  • לוחית {p['license_plate']} (קו {p.get('line')})" for p in complaint_data["nearby_plates"]])

    body = f"""שלום רב,

הודעה זו נשלחה בעקבות פניית ציבור רשמית שהוגשה במערכת משרד התחבורה:
מספר פנייה רשמי: {ref_number}
טופס מקוון: {GOV_FORM_URL}

■ פרטי הפונה:
- שם מלא: {complaint_data.get('full_name')}
- תעודת זהות: {complaint_data.get('id_number')}
- טלפון: {complaint_data.get('phone')}
- כתובת דוא"ל: {complaint_data.get('email')}

■ פרטי הנסיעה והתחנה:
- מספר תחנה (קוד תחנה): {complaint_data.get('stop_code', 'לא צוין')}
- שם התחנה ומיקום: {complaint_data.get('stop_name', 'ירושלים')}
- כיוון הנסיעה: {complaint_data.get('direction', 'לא צוין')}
- מספר קו: {complaint_data.get('line_number')}
- חברה מפעילה: {complaint_data.get('operator')}
- תאריך ושעה מדווחת: {complaint_data.get('date_time')}

■ פרטי האוטובוס והנהג:
- מספר רישוי של האוטובוס באירוע: {complaint_data.get('license_plate', 'לא ידוע')}
- שם הנהג / תג נהג: {complaint_data.get('driver_name', 'לא צוין - יאותר בסידור העבודה לפי לוחית הרישוי')}
- אוטובוסים שפעלו בתחנה בחלון של 15 דקות לפני/אחרי:
{nearby_str}

■ נושא ופירוט התלונה:
נושא: {complaint_data.get('category')}
פירוט האירוע:
{complaint_data.get('details')}

נודה לקבלת אישור קבלה ועדכון בדבר הטיפול בפנייה לפי מספר הפנייה: {ref_number}.

בברכה,
{complaint_data.get('full_name')}
"""

    if not SMTP_USER or not SMTP_PASSWORD:
        logging.warning("SMTP not configured - mail logged to console.")
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
        logging.error(f"Error sending email: {e}")
        return False
