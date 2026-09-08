import httpx
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

async def get_line_info(line_number: str):
    """
    מאתר את שם המפעיל ומסלול הקו מתוך מאגר משרד התחבורה (GTFS)
    """
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(
                f"{STRIDE_API_BASE}/gtfs_routes/list",
                params={"line_ref": line_number, "limit": 5},
                timeout=8.0
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
    return {"operator": "לא זוהה אוטומטית", "route_name": f"קו {line_number}"}

async def find_license_plates(line_number: str, target_time: datetime = None):
    """
    מאתר לוחיות רישוי של אוטובוסים שנסעו בקו בחלון הזמנים הרלוונטי (SIRI)
    """
    if target_time is None:
        target_time = datetime.now()

    time_from = (target_time - timedelta(minutes=45)).isoformat()
    time_to = (target_time + timedelta(minutes=45)).isoformat()

    async with httpx.AsyncClient() as client:
        try:
            res = await client.get(
                f"{STRIDE_API_BASE}/siri_rides/list",
                params={
                    "scheduled_start_time_from": time_from,
                    "scheduled_start_time_to": time_to,
                    "limit": 15
                },
                timeout=10.0
            )
            if res.status_code == 200:
                rides = res.json()
                plates = set()
                for ride in rides:
                    plate = ride.get("vehicle_license_plate")
                    if plate:
                        plates.add(str(plate))
                return list(plates)
        except Exception:
            pass
    return []
