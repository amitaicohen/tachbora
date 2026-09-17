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

# מאגר תחנות מקומי בירושלים
JERUSALEM_STOPS = {
    "2134": "בר כוכבא / מבוא העשרה (הגבעה הצרפתית)",
    "2135": "ההגנה / בר כוכבא",
    "2136": "החי\"ל / אבא ברדיצ'ב",
    "2137": "החי\"ל / משה הס",
    "2138": "לוחמי הגטאות / קלרמון גאנו",
    "1800": "תחנה מרכזית ירושלים",
    "1801": "תחנה מרכזית ירושלים / הורדה",
    "3000": "צומת בר אילן",
    "5000": "הר חוצבים / שדרות גולדה מאיר",
    "6000": "גבעת התחמושת"
}

async def get_stop_info(stop_code: str):
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

async def get_line_info(line_number: str):
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(
                f"{STRIDE_API_BASE}/gtfs_routes/list",
                params={"line_ref": line_number, "limit": 5},
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
        "68": "סופרבוס", "77": "סופרבוס", "77א": "סופרבוס", "15": "אקסטרה ירושלים",
        "19": "אגד", "25": "אגד", "31": "אגד", "32": "סופרבוס", "59": "אגד", "74": "אגד"
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
            # שליפה לפי טווח זמנים
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
