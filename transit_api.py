import httpx
import logging
from datetime import datetime, timedelta
from config import STRIDE_API_BASE

OPERATORS_MAP = {
    "3": "אגד",
    "5": "דן",
    "14": "נתיב אקספרס",
    "15": "מטרופולין",
    "16": "סופרבוס",
    "18": "קווים",
    "25": "אלקטרה אפיקים",
    "31": "דן בדרום",
    "32": "דן באר שבע",
    "35": "תנופה",
    "37": "בית שמש אקספרס",
    "40": "אקסטרה ירושלים"
}

# מאגר תחנות מקומי בירושלים (חיפוש מהיר ואופליין)
JERUSALEM_STOPS = {
    "1412": "מרכז מסחרי / ההגנה (הגבעה הצרפתית)",
    "2134": "בר כוכבא / מבוא העשרה (הגבעה הצרפתית)",
    "2135": "ההגנה / בר כוכבא (הגבעה הצרפתית)",
    "2136": 'החי"ל / אבא ברדיצ\'ב (הגבעה הצרפתית)',
    "2137": 'החי"ל / משה הס (הגבעה הצרפתית)',
    "2138": "לוחמי הגטאות / קלרמון גאנו (הגבעה הצרפתית)",
    "1800": "תחנה מרכזית ירושלים",
    "1801": "תחנה מרכזית ירושלים / הורדה",
    "3000": "צומת בר אילן",
    "5000": "הר חוצבים / שדרות גולדה מאיר",
    "6000": "גבעת התחמושת",
    "6001": "גבעת התחמושת / שדרות לוי אשכול",
    "6100": "צומת הגבעה הצרפתית / שדרות לוי אשכול"
}

async def get_stop_info(stop_code: str):
    """
    קבלת פרטי תחנה לפי קוד תחנה (1-5 ספרות)
    """
    code = str(stop_code).strip()
    if code in JERUSALEM_STOPS:
        return {"stop_name": JERUSALEM_STOPS[code], "city": "ירושלים", "code": code}

    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(
                f"{STRIDE_API_BASE}/gtfs_stops/list",
                params={"code": code, "limit": 1},
                timeout=6.0
            )
            if res.status_code == 200:
                stops = res.json()
                if stops:
                    return {
                        "stop_name": stops[0].get("name", f"תחנה {code}"),
                        "city": stops[0].get("city", "ירושלים"),
                        "code": code
                    }
        except Exception as e:
            logging.warning(f"Stop lookup error: {e}")

    return {"stop_name": f"תחנה מספר {code}", "city": "ירושלים", "code": code}

async def search_stops_by_name(query_name: str, city: str = "ירושלים", limit: int = 6):
    """
    איתור תחנות לפי שם או רחוב מתוך OpenBus Stride API ומאגר מקומי:
    מחזיר רשימה של תחנות תואמות לבחירת המשתמש.
    """
    clean_query = query_name.strip().replace('"', '').replace("'", "")
    results = []
    seen_codes = set()

    # 1. חיפוש מהיר במאגר המקומי
    for code, name in JERUSALEM_STOPS.items():
        if clean_query in name or clean_query in code:
            seen_codes.add(code)
            results.append({
                "code": code,
                "name": name,
                "city": "ירושלים"
            })

    # 2. שאילתה ל-OpenBus Stride API
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(
                f"{STRIDE_API_BASE}/gtfs_stops/list",
                params={"city": city, "limit": 200},
                timeout=6.0
            )
            if res.status_code == 200:
                stops = res.json()
                for s in stops:
                    s_name = s.get("name", "")
                    s_code = str(s.get("code", ""))
                    if clean_query in s_name and s_code not in seen_codes:
                        seen_codes.add(s_code)
                        results.append({
                            "code": s_code,
                            "name": s_name,
                            "city": s.get("city", city)
                        })
                        if len(results) >= limit:
                            break
        except Exception as e:
            logging.warning(f"Stride API stop search error: {e}")

    return results[:limit]

async def get_line_info(line_number: str):
    """
    זיהוי מפעיל הקו ושם המסלול
    """
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(
                f"{STRIDE_API_BASE}/gtfs_routes/list",
                params={"route_short_name": line_number, "limit": 5},
                timeout=6.0
            )
            if res.status_code == 200:
                routes = res.json()
                if routes:
                    op_ref = str(routes[0].get("operator_ref", ""))
                    operator_name = OPERATORS_MAP.get(op_ref, f"מפעיל {op_ref}")
                    return {
                        "operator": operator_name,
                        "route_name": routes[0].get("route_long_name", f"קו {line_number}")
                    }
        except Exception:
            pass

    # מיפוי ברירת מחדל לקווי ירושלים פופולריים
    default_jerusalem = {
        "61": "אקסטרה ירושלים", "68": "סופרבוס", "77": "סופרבוס", "77א": "סופרבוס",
        "15": "אקסטרה ירושלים", "19": "אגד", "25": "אגד", "31": "אגד",
        "32": "סופרבוס", "59": "אגד", "74": "אגד"
    }
    op = default_jerusalem.get(line_number, "מפעיל תחבורה ציבורית")
    return {"operator": op, "route_name": f"קו {line_number}"}

async def find_station_arrivals_15min(stop_code: str, line_number: str, target_time: datetime):
    """
    איתור לוחיות רישוי בחלון של 15 דקות לפני ו-15 דקות אחרי המועד המבוקש
    """
    time_from = (target_time - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")
    time_to = (target_time + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")

    results = []
    seen = set()

    async with httpx.AsyncClient() as client:
        try:
            params = {
                "scheduled_start_time_from": time_from,
                "scheduled_start_time_to": time_to,
                "limit": 30
            }
            res = await client.get(f"{STRIDE_API_BASE}/siri_rides/list", params=params, timeout=7.0)
            if res.status_code == 200:
                rides = res.json()
                for r in rides:
                    plate = r.get("vehicle_license_plate")
                    line_ref = r.get("siri_route__line_ref") or line_number
                    if plate and plate not in seen:
                        seen.add(plate)
                        results.append({
                            "license_plate": str(plate),
                            "line": str(line_ref)
                        })
        except Exception as e:
            logging.warning(f"SIRI fetch error: {e}")

    return results


async def get_line_61_live_status(stop_code: str = "1412"):
    """
    שליפת סטטוס חי של קו 61 (הר הצופים -> רמות) בתחנה 1412
    """
    now = datetime.now()
    time_from = (now - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    time_to = (now + timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M:%SZ")

    results = []
    async with httpx.AsyncClient() as client:
        try:
            # שליפת נסיעות קו 61 סביב השעה הנוכחית
            res = await client.get(
                f"{STRIDE_API_BASE}/siri_rides/list",
                params={
                    "scheduled_start_time_from": time_from,
                    "scheduled_start_time_to": time_to,
                    "limit": 25
                },
                timeout=7.0
            )
            if res.status_code == 200:
                rides = res.json()
                for r in rides:
                    plate = r.get("vehicle_ref") or r.get("vehicle_license_plate")
                    sched = r.get("scheduled_start_time", "")
                    if plate:
                        results.append({
                            "license_plate": str(plate),
                            "scheduled_time": sched[11:16] if len(sched) >= 16 else sched,
                            "ride_id": r.get("id")
                        })
        except Exception as e:
            logging.warning(f"Error fetching live line 61: {e}")

    return results
