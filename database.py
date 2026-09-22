import os
import sqlite3
import logging
from datetime import datetime

DEFAULT_DB_PATH = os.getenv("SQLITE_DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "complaints.db"))

def get_connection():
    try:
        conn = sqlite3.connect(DEFAULT_DB_PATH, timeout=5)
        # בדיקת נעילה וכתיבה במערכת הקבצים
        conn.execute("CREATE TABLE IF NOT EXISTS _fs_test (id INT)")
        conn.commit()
        return conn
    except sqlite3.OperationalError:
        # אם מערכת הקבצים לא תומכת בנעילת SQLite (כמו רשת/NFS), שימוש בנתיב מקומי בטוח
        fallback_path = os.path.join("/tmp", "tachborabot_complaints.db")
        return sqlite3.connect(fallback_path, timeout=5)

def init_db():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # טבלת משתמשים - שמירת פרטי זיהוי מלאים לפי טופס משרד התחבורה
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                id_number TEXT,
                phone TEXT,
                email TEXT,
                city TEXT,
                street TEXT,
                last_updated TEXT
            )
        ''')

        # מיגרציה אוטומטית לעמודות חדשות אם הטבלה כבר נוצרה בעבר
        cursor.execute("PRAGMA table_info(users)")
        existing_user_cols = [c[1] for c in cursor.fetchall()]
        for col, ctype in [("first_name", "TEXT"), ("last_name", "TEXT"), ("city", "TEXT"), ("street", "TEXT")]:
            if col not in existing_user_cols:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {ctype}")

        # טבלת תלונות מלאה התואמת את מבנה משרד התחבורה
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ref_number TEXT UNIQUE,
                created_at TEXT,
                telegram_id INTEGER,
                first_name TEXT,
                last_name TEXT,
                full_name TEXT,
                id_number TEXT,
                phone TEXT,
                email TEXT,
                city TEXT,
                street TEXT,
                line_number TEXT,
                operator TEXT,
                stop_code TEXT,
                stop_name TEXT,
                direction TEXT,
                incident_date TEXT,
                incident_time TEXT,
                date_time TEXT,
                license_plate TEXT,
                driver_name TEXT,
                nearby_plates TEXT,
                category TEXT,
                details TEXT,
                status TEXT DEFAULT 'הוגש למשרד התחבורה ולעירייה'
            )
        ''')

        cursor.execute("PRAGMA table_info(complaints)")
        existing_comp_cols = [c[1] for c in cursor.fetchall()]
        for col, ctype in [
            ("first_name", "TEXT"), ("last_name", "TEXT"), ("city", "TEXT"),
            ("street", "TEXT"), ("incident_date", "TEXT"), ("incident_time", "TEXT")
        ]:
            if col not in existing_comp_cols:
                cursor.execute(f"ALTER TABLE complaints ADD COLUMN {col} {ctype}")

        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"שגיאה באתחול טבלאות ב-SQLite: {e}")

def get_user_profile(telegram_id: int):
    """
    שולף פרטי משתמש קיים לפי מזהה טלגרם
    """
    try:
        init_db()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT first_name, last_name, id_number, phone, email, city, street 
            FROM users WHERE telegram_id = ?
        ''', (telegram_id,))
        row = cursor.fetchone()
        conn.close()
        if row and (row[0] or row[2]):
            first_name = row[0] or ""
            last_name = row[1] or ""
            full_name = f"{first_name} {last_name}".strip()
            return {
                "first_name": first_name,
                "last_name": last_name,
                "full_name": full_name,
                "id_number": row[2] or "",
                "phone": row[3] or "",
                "email": row[4] or "",
                "city": row[5] or "ירושלים",
                "street": row[6] or ""
            }
    except Exception as e:
        logging.error(f"שגיאה בשליפת משתמש: {e}")
    return None

def save_user_profile(telegram_id: int, first_name: str, last_name: str, id_number: str, phone: str, email: str, city: str = "ירושלים", street: str = ""):
    """
    שומר או מעדכן פרטי משתמש בזיכרון
    """
    try:
        init_db()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (telegram_id, first_name, last_name, id_number, phone, email, city, street, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                first_name=excluded.first_name,
                last_name=excluded.last_name,
                id_number=excluded.id_number,
                phone=excluded.phone,
                email=excluded.email,
                city=excluded.city,
                street=excluded.street,
                last_updated=excluded.last_updated
        ''', (
            telegram_id,
            first_name.strip(),
            last_name.strip(),
            id_number.strip(),
            phone.strip(),
            email.strip(),
            city.strip(),
            street.strip(),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"שגיאה בעדכון פרופיל משתמש: {e}")

def save_complaint(data: dict, ref_number: str) -> bool:
    try:
        init_db()
        conn = get_connection()
        cursor = conn.cursor()

        nearby = ", ".join([f"{p['license_plate']} ({p.get('line')})" for p in data.get('nearby_plates', [])])
        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')
        full_name = data.get('full_name') or f"{first_name} {last_name}".strip()

        cursor.execute('''
            INSERT INTO complaints (
                ref_number, created_at, telegram_id, first_name, last_name, full_name,
                id_number, phone, email, city, street,
                line_number, operator, stop_code, stop_name, direction,
                incident_date, incident_time, date_time, license_plate, driver_name, nearby_plates,
                category, details, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            ref_number,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            data.get('telegram_id', 0),
            first_name,
            last_name,
            full_name,
            data.get('id_number', ''),
            data.get('phone', ''),
            data.get('email', ''),
            data.get('city', 'ירושלים'),
            data.get('street', ''),
            data.get('line_number', ''),
            data.get('operator', ''),
            data.get('stop_code', ''),
            data.get('stop_name', ''),
            data.get('direction', ''),
            data.get('incident_date', ''),
            data.get('incident_time', ''),
            data.get('date_time', ''),
            data.get('license_plate', ''),
            data.get('driver_name', ''),
            nearby,
            data.get('category', ''),
            data.get('details', ''),
            'הוגש למשרד התחבורה ולעירייה'
        ))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"שגיאה בשמירת התלונה ב-SQLite: {e}")
        return False
