import os
import sqlite3
import logging
from datetime import datetime

DB_PATH = os.getenv("SQLITE_DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "complaints.db"))

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # טבלת משתמשים - זיכרון משתמשים שדיווחו בעבר
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                full_name TEXT,
                id_number TEXT,
                phone TEXT,
                email TEXT,
                last_updated TEXT
            )
        ''')

        # טבלת תלונות מלאה
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ref_number TEXT UNIQUE,
                created_at TEXT,
                telegram_id INTEGER,
                full_name TEXT,
                id_number TEXT,
                phone TEXT,
                email TEXT,
                line_number TEXT,
                operator TEXT,
                stop_code TEXT,
                stop_name TEXT,
                direction TEXT,
                date_time TEXT,
                license_plate TEXT,
                driver_name TEXT,
                nearby_plates TEXT,
                category TEXT,
                details TEXT,
                status TEXT DEFAULT 'הוגש למשרד התחבורה ולעירייה'
            )
        ''')
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
        cursor.execute('SELECT full_name, id_number, phone, email FROM users WHERE telegram_id = ?', (telegram_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "full_name": row[0],
                "id_number": row[1],
                "phone": row[2],
                "email": row[3]
            }
    except Exception as e:
        logging.error(f"שגיאה בשליפת משתמש: {e}")
    return None

def save_user_profile(telegram_id: int, full_name: str, id_number: str, phone: str, email: str):
    """
    שומר או מעדכן פרטי משתמש בזיכרון
    """
    try:
        init_db()
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (telegram_id, full_name, id_number, phone, email, last_updated)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                full_name=excluded.full_name,
                id_number=excluded.id_number,
                phone=excluded.phone,
                email=excluded.email,
                last_updated=excluded.last_updated
        ''', (telegram_id, full_name, id_number, phone, email, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
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

        cursor.execute('''
            INSERT INTO complaints (
                ref_number, created_at, telegram_id, full_name, id_number, phone, email,
                line_number, operator, stop_code, stop_name, direction,
                date_time, license_plate, driver_name, nearby_plates,
                category, details, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            ref_number,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            data.get('telegram_id', 0),
            data.get('full_name', ''),
            data.get('id_number', ''),
            data.get('phone', ''),
            data.get('email', ''),
            data.get('line_number', ''),
            data.get('operator', ''),
            data.get('stop_code', ''),
            data.get('stop_name', ''),
            data.get('direction', ''),
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
