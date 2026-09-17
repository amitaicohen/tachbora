import os
import httpx
import logging
from datetime import datetime

# מזהה גיליון ה-Google Sheets שלך
SPREADSHEET_ID = "1_PuD4dOsZvWLYcIhiaZIQ6y4DFZZu93B4CKrv08tFkE"
SPREADSHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
SHEETS_WEBHOOK_URL = os.getenv("SHEETS_WEBHOOK_URL", "")

async def append_complaint_to_google_sheets(data: dict, ref_number: str) -> bool:
    nearby = ", ".join([f"{p['license_plate']} ({p.get('line')})" for p in data.get('nearby_plates', [])])

    payload = {
        "ref_number": ref_number,
        "created_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "full_name": data.get("full_name", ""),
        "id_number": data.get("id_number", ""),
        "phone": data.get("phone", ""),
        "email": data.get("email", ""),
        "line_number": data.get("line_number", ""),
        "operator": data.get("operator", ""),
        "stop_code": data.get("stop_code", ""),
        "stop_name": data.get("stop_name", ""),
        "direction": data.get("direction", ""),
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
        return True

    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(SHEETS_WEBHOOK_URL, json=payload, timeout=10.0)
            return res.status_code == 200
    except Exception as e:
        logging.error(f"שגיאה בסנכרון ל-Google Sheets: {e}")
        return False
