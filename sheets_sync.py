import os
import httpx
import logging
from datetime import datetime

SPREADSHEET_ID = "1_PuD4dOsZvWLYcIhiaZIQ6y4DFZZu93B4CKrv08tFkE"
SPREADSHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
SHEETS_WEBHOOK_URL = os.getenv("SHEETS_WEBHOOK_URL", "")

async def append_complaint_and_send_email_via_google(data: dict, ref_number: str) -> dict:
    """
    שולח את פרטי התלונה ל-Google Apps Script Webhook
    ה-Webhook מבצע שני דברים במקביל:
    1. כותב שורה ב-Google Sheets
    2. שולח מייל רשמי מתוך ה-Gmail של המשתמש למשרד התחבורה, עיריית ירושלים ועותק למתלונן
    """
    nearby = ", ".join([f"{p['license_plate']} ({p.get('line')})" for p in data.get('nearby_plates', [])])
    first_name = data.get("first_name", "")
    last_name = data.get("last_name", "")
    full_name = data.get("full_name") or f"{first_name} {last_name}".strip()

    payload = {
        "ref_number": ref_number,
        "created_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "id_number": data.get("id_number", ""),
        "phone": data.get("phone", ""),
        "email": data.get("email", ""),
        "city": data.get("city", "ירושלים"),
        "street": data.get("street", ""),
        "line_number": data.get("line_number", ""),
        "operator": data.get("operator", ""),
        "stop_code": data.get("stop_code", ""),
        "stop_name": data.get("stop_name", ""),
        "direction": data.get("direction", ""),
        "incident_date": data.get("incident_date", ""),
        "incident_time": data.get("incident_time", ""),
        "date_time": data.get("date_time", ""),
        "license_plate": data.get("license_plate", ""),
        "driver_name": data.get("driver_name", ""),
        "nearby_plates": nearby,
        "category": data.get("category", ""),
        "details": data.get("details", ""),
        "status": "הוגש למשרד התחבורה ולעירייה"
    }

    # גיבוי מקומי מהיר לקובץ CSV
    try:
        csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "complaints_backup.csv")
        with open(csv_path, "a", encoding="utf-8") as f:
            line = f'"{ref_number}","{payload["created_at"]}","{payload["full_name"]}","{payload["phone"]}","{payload["line_number"]}","{payload["operator"]}","{payload["stop_code"]}","{payload["category"]}"\n'
            f.write(line)
    except Exception:
        pass

    if not SHEETS_WEBHOOK_URL:
        return {"success": False, "reason": "no_webhook", "message": "SHEETS_WEBHOOK_URL not configured"}

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            res = await client.post(SHEETS_WEBHOOK_URL, json=payload, timeout=15.0)
            if res.status_code == 200:
                resp_json = res.json()
                return {"success": True, "email_sent": resp_json.get("email_sent", True)}
    except Exception as e:
        logging.error(f"שגיאה בסנכרון ל-Google Sheets/Gmail: {e}")
        return {"success": False, "reason": "network_error", "message": str(e)}

    return {"success": False, "reason": "unknown"}
