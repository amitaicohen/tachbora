#!/usr/bin/env python3
"""
סקריפט מלא לשליפת מקסימום נתונים על קו 61 בירושלים
מהר הצופים לכיוון רמות (מסוף אצ"ג) בתחנה 1412 (מרכז מסחרי / ההגנה, גבעה צרפתית)
מתוך OpenBus Stride API (הסדנא לידע ציבורי)
"""

import sys
import os
import json
import csv
import argparse
import asyncio
from datetime import datetime, timedelta

try:
    import httpx
except ImportError:
    print("[-] חבילת httpx אינה מותקנת. הרץ בטרמינל: pip install httpx")
    sys.exit(1)

BASE_URL = "https://open-bus-stride-api.hasadna.org.il"
DEFAULT_LINE = "61"
DEFAULT_STOP_CODE = "1412"
DEFAULT_STOP_NAME = "מרכז מסחרי / ההגנה (הגבעה הצרפתית)"
DEFAULT_DIRECTION = "לרמות (מסוף אצ\"ג)"
JERUSALEM_TZ_OFFSET = 3

async def fetch_json(client, url, params=None):
    try:
        res = await client.get(url, params=params, timeout=12.0)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"[-] שגיאה בכתובת {url}: {e}", file=sys.stderr)
    return []

async def get_line_61_routes(client, target_date_str):
    url = f"{BASE_URL}/gtfs_routes/list"
    params = {"route_short_name": DEFAULT_LINE, "date": target_date_str, "limit": 10}
    routes = await fetch_json(client, url, params)
    target_routes = [r for r in routes if "רמות" in r.get("route_long_name", "")]
    return target_routes if target_routes else routes

async def extract_day_data(client, date_obj, line_refs, operator_ref="40"):
    date_str = date_obj.strftime("%Y-%m-%d")
    date_display = date_obj.strftime("%d/%m/%Y")
    day_name = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"][date_obj.weekday()]

    from_time_utc = f"{date_str}T03:00:00Z"
    to_time_utc = f"{date_str}T21:00:00Z"
    results = []
    rides = []

    for line_ref in line_refs:
        url = f"{BASE_URL}/siri_rides/list"
        params = {
            "scheduled_start_time_from": from_time_utc,
            "scheduled_start_time_to": to_time_utc,
            "siri_route__line_ref": line_ref,
            "limit": 100
        }
        res_rides = await fetch_json(client, url, params)
        if res_rides:
            rides.extend(res_rides)

    if not rides and operator_ref:
        url = f"{BASE_URL}/siri_rides/list"
        params = {
            "scheduled_start_time_from": from_time_utc,
            "scheduled_start_time_to": to_time_utc,
            "siri_route__operator_ref": operator_ref,
            "limit": 150
        }
        rides = await fetch_json(client, url, params)

    rides.sort(key=lambda x: x.get("scheduled_start_time") or "")

    for r in rides:
        ride_id = r.get("id")
        sched_start = r.get("scheduled_start_time")
        plate = r.get("vehicle_ref") or r.get("vehicle_license_plate") or "לא זוהה"

        sched_local_str = ""
        if sched_start:
            try:
                dt_utc = datetime.fromisoformat(sched_start.replace("Z", "+00:00"))
                sched_local_str = (dt_utc + timedelta(hours=JERUSALEM_TZ_OFFSET)).strftime("%H:%M")
            except Exception:
                sched_local_str = str(sched_start)[11:16]

        planned_arr_minutes = 0
        planned_arrival_str = ""
        if sched_local_str:
            try:
                sh, sm = map(int, sched_local_str.split(":"))
                planned_arr_minutes = sh * 60 + sm + 8
                planned_arrival_str = f"{planned_arr_minutes // 60:02d}:{planned_arr_minutes % 60:02d}"
            except Exception:
                pass

        stop_url = f"{BASE_URL}/siri_ride_stops/list"
        stop_params = {"siri_ride_id": ride_id, "gtfs_stop__code": DEFAULT_STOP_CODE}
        stops_res = await fetch_json(client, stop_url, stop_params)

        actual_arrival_str = ""
        delay_minutes = ""
        status = "לא אותרה נסיעה ב-SIRI"
        velocity = None

        if stops_res:
            s_data = stops_res[0]
            rec_time = s_data.get("nearest_siri_vehicle_location__recorded_at_time") or s_data.get("actual_arrival_time")
            velocity = s_data.get("nearest_siri_vehicle_location__velocity")

            if rec_time:
                try:
                    act_utc = datetime.fromisoformat(rec_time.replace("Z", "+00:00"))
                    act_local = act_utc + timedelta(hours=JERUSALEM_TZ_OFFSET)
                    actual_arrival_str = act_local.strftime("%H:%M")
                    act_minutes = act_local.hour * 60 + act_local.minute

                    if planned_arr_minutes > 0:
                        diff = act_minutes - planned_arr_minutes
                        delay_minutes = diff
                        if diff > 15:
                            status = f"איחור חמור ({diff} דק')"
                        elif diff > 5:
                            status = f"איחור ({diff} דק')"
                        elif diff < -2:
                            status = f"הקדים ({abs(diff)} דק')"
                        else:
                            status = "תקין (בזמן)"
                except Exception:
                    actual_arrival_str = str(rec_time)[11:16]
                    status = "נמדד איכון"
            else:
                status = "הרכב לא שידר איכון בתחנה"
        else:
            status = "אין דיגום בתחנה זו"

        results.append({
            "תאריך": date_display,
            "יום": day_name,
            "קו": DEFAULT_LINE,
            "מפעיל": "אקסטרה ירושלים",
            "כיוון": DEFAULT_DIRECTION,
            "קוד_תחנה": DEFAULT_STOP_CODE,
            "שם_תחנה": DEFAULT_STOP_NAME,
            "יציאה_מתוכננת_מוצא": sched_local_str,
            "הגעה_מתוכננת_לתחנה": planned_arrival_str,
            "הגעה_בפועל_לתחנה": actual_arrival_str,
            "הפרש_דקות": delay_minutes,
            "מספר_רישוי": plate,
            "מהירות_קמש": velocity if velocity is not None else "",
            "סטטוס_ביצוע": status
        })

    return results

async def run_extraction(days=1, output_csv="line_61_report.csv"):
    print("=" * 65)
    print("🚌 מחלץ נתוני קו 61 בירושלים (הר הצופים -> רמות | תחנה 1412)")
    print("מקור: OpenBus Stride API (הסדנא לידע ציבורי)")
    print("=" * 65)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        today = datetime.now()
        yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        routes = await get_line_61_routes(client, yesterday_str)
        line_refs = [r.get("line_ref") for r in routes if r.get("line_ref")]
        operator_ref = routes[0].get("operator_ref", "40") if routes else "40"

        all_records = []
        for i in range(1, days + 1):
            target_date = today - timedelta(days=i)
            if target_date.weekday() == 5:
                continue
            date_str = target_date.strftime("%d/%m/%Y")
            print(f"[*] שולף נתונים לתאריך {date_str}...", end="", flush=True)
            day_records = await extract_day_data(client, target_date, line_refs, operator_ref)
            print(f" נמצאו {len(day_records)} נסיעות.")
            all_records.extend(day_records)

    if not all_records:
        print("[-] לא אותרו נתונים.")
        return

    keys = list(all_records[0].keys())
    with open(output_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(all_records)

    print(f"\n[✓] הושלם! הדוח נשמר בהצלחה כקובץ: {output_csv}")
    print(f"סך נסיעות שנותחו: {len(all_records)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--csv", type=str, default="line_61_report.csv")
    args = parser.parse_args()
    asyncio.run(run_extraction(days=args.days, output_csv=args.csv))
