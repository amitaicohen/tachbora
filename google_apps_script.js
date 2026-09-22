/**
 * =========================================================================
 * חבילת Google Apps Script מלאה לתחבורה ציבורית ירושלים (קו 61 ובוט תלונות)
 * =========================================================================
 * להדבקה ב-Google Sheet שלך תחת: הרחבות (Extensions) -> Apps Script
 *
 * כולל שני רכיבים מרכזיים:
 * 1. Webhook (doPost): שמירת תלונות מהבוט ושליחת דוא"ל רשמי דרך Gmail.
 * 2. סנכרון קו 61 (syncLine61Arrivals): שליפת נתוני אמת מ-OpenBus (הסדנא)
 *    לנסיעות קו 61 מהר הצופים לרמות בתחנה 1412 (זמני אמת, איחורים ולוחיות).
 */

var OPENBUS_BASE_URL = "https://open-bus-stride-api.hasadna.org.il";

// =========================================================================
// רכיב 1: קליטת תלונות מבוט הטלגרם ושליחת דוא"ל רשמי
// =========================================================================
function doPost(e) {
  try {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
    var d = JSON.parse(e.postData.contents);
    
    // שמירה ב-Google Sheets
    sheet.appendRow([
      d.ref_number,
      d.created_at,
      d.first_name || "",
      d.last_name || "",
      d.id_number,
      d.phone,
      d.email,
      (d.street || "") + ", " + (d.city || "ירושלים"),
      d.line_number,
      d.operator,
      d.stop_code,
      d.stop_name,
      d.direction,
      d.incident_date || d.date_time,
      d.incident_time || "",
      d.license_plate,
      d.driver_name,
      d.nearby_plates,
      d.category,
      d.details,
      d.status
    ]);
    
    // שליחת אימייל רשמי ישירות מתיבת ה-Gmail של המשתמש
    var motEmail = "pniotcrm@mot.gov.il";
    var jlmEmail = "david_zo@jerusalem.muni.il";
    var userEmail = d.email || "amitai.co@gmail.com";
    var fullName = d.full_name || ((d.first_name || "") + " " + (d.last_name || "")).trim();
    
    var subject = "[פנייה #" + d.ref_number + "] תלונה: קו " + d.line_number + " בירושלים (" + d.operator + ") - " + d.category;
    
    var body = "שלום רב,\n\n" +
      "להלן פניית ציבור רשמית בנושא תחבורה ציבורית, המוגשת בהתאם לשדות הנדרשים בנוהל משרד התחבורה:\n" +
      "מספר פנייה למעקב: " + d.ref_number + "\n" +
      "קישור לטופס מקוון: https://govforms.gov.il/mw/forms/PublicTransportRequest@mot.gov.il?gbxid=0\n\n" +
      "■ פרטי הפונה (המתלונן):\n" +
      "- שם פרטי: " + (d.first_name || "") + "\n" +
      "- שם משפחה: " + (d.last_name || "") + "\n" +
      "- תעודת זהות: " + d.id_number + "\n" +
      "- טלפון נייד: " + d.phone + "\n" +
      "- דוא\"ל: " + d.email + "\n" +
      "- כתובת למשלוח דואר: " + (d.street || "") + ", " + (d.city || "ירושלים") + "\n\n" +
      "■ פרטי הנסיעה והאירוע:\n" +
      "- אמצעי תחבורה: אוטובוס עירוני\n" +
      "- קו: " + d.line_number + " (" + d.operator + ")\n" +
      "- כיוון נסיעה / יעד: " + (d.direction || "לא צוין") + "\n" +
      "- תאריך האירוע: " + (d.incident_date || d.date_time) + "\n" +
      "- שעת האירוע: " + (d.incident_time || "") + "\n" +
      "- תחנת עלייה / מיקום: " + d.stop_name + " (קוד תחנה: " + d.stop_code + ")\n\n" +
      "■ פרטי האוטובוס והנהג:\n" +
      "- מספר רישוי: " + d.license_plate + "\n" +
      "- שם הנהג / תג: " + d.driver_name + "\n" +
      "- אוטובוסים שחלפו בתחנה בטווח 15 דקות (נתוני אמת): \n" + (d.nearby_plates || "לא אותרו במאגר") + "\n\n" +
      "■ מהות התלונה ופירוט האירוע:\n" +
      "נושא: " + d.category + "\n" +
      "פירוט:\n" + d.details + "\n\n" +
      "נודה לקבלת אישור קבלה ועדכון בדבר הטיפול לפי מספר הפנייה המצוין לעיל.\n\n" +
      "בברכה,\n" + fullName + "\nטלפון: " + d.phone;

    MailApp.sendEmail({
      to: motEmail + ", " + jlmEmail,
      cc: userEmail,
      subject: subject,
      body: body
    });

    return ContentService.createTextOutput(JSON.stringify({
      result: "success",
      email_sent: true,
      ref_number: d.ref_number
    })).setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({
      result: "error",
      error: err.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  }
}

// =========================================================================
// רכיב 2: סנכרון נתוני אמת לקו 61 בתחנה 1412 מ-OpenBus Stride API
// =========================================================================

/**
 * פונקציית בדיקה מהירה לקשר מול שרתי OpenBus
 */
function testOpenBusConnection() {
  Logger.log("בודק חיבור ל-OpenBus Stride API...");
  var res = UrlFetchApp.fetch(OPENBUS_BASE_URL + "/gtfs_routes/list?route_short_name=61&limit=5", { muteHttpExceptions: true });
  Logger.log("קוד תשובה: " + res.getResponseCode());
  var routes = JSON.parse(res.getContentText());
  Logger.log("נמצאו " + routes.length + " מסלולים לקו 61.");
  if (routes.length > 0) {
    Logger.log("מסלול ראשון: line_ref=" + routes[0].line_ref + ", operator_ref=" + routes[0].operator_ref);
  }
}

/**
 * עדכון הגעות בפועל, איחורים ולוחיות רישוי בגיליון מעקב קו 61
 * מעבד מנה של עד 40 שורות בכל ריצה (למניעת Timeout)
 */
function syncLine61Arrivals() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var displayData = sheet.getDataRange().getDisplayValues();
  
  var countProcessed = 0;
  var maxBatch = 40;

  // 1. איתור line_ref רשמי של קו 61 מהר הצופים לרמות
  var routesRes = UrlFetchApp.fetch(OPENBUS_BASE_URL + "/gtfs_routes/list?route_short_name=61&limit=8", { muteHttpExceptions: true });
  var lineRefs = [];
  var operatorRef = "40"; // אקסטרה ירושלים

  if (routesRes.getResponseCode() === 200) {
    var routes = JSON.parse(routesRes.getContentText());
    for (var r = 0; r < routes.length; r++) {
      if (routes[r].line_ref && lineRefs.indexOf(routes[r].line_ref) === -1) {
        lineRefs.push(routes[r].line_ref);
      }
      if (routes[r].operator_ref) {
        operatorRef = routes[r].operator_ref;
      }
    }
  }

  Logger.log("line_refs עבור קו 61: " + JSON.stringify(lineRefs));

  // 2. מעבר על שורות הגיליון
  for (var i = 1; i < displayData.length; i++) {
    if (countProcessed >= maxBatch) {
      Logger.log("הסתיימה מנה של " + maxBatch + " שורות.");
      break;
    }

    var rawDate = displayData[i][0];        // A: תאריך
    var stopCode = displayData[i][5];       // F: קוד תחנה (1412)
    var plannedDep = displayData[i][7];     // H: יציאה מתוכננת ממוצא (הר הצופים)
    var plannedArr = displayData[i][8];     // I: הגעה מתוכננת לתחנה 1412
    var existingActual = displayData[i][9]; // J: הגעה בפועל

    // דילוג אם כבר עודכן זמן הגעה בפועל
    if (!rawDate || !plannedDep || (existingActual && existingActual.trim() !== "")) {
      continue;
    }

    // המרת תאריך ל-YYYY-MM-DD
    var parts = rawDate.trim().split("/");
    if (parts.length !== 3) continue;
    var day = parts[0].length === 1 ? "0" + parts[0] : parts[0];
    var month = parts[1].length === 1 ? "0" + parts[1] : parts[1];
    var year = parts[2];

    // המרת שעת יציאה ל-UTC (הפחתת 3 שעות לשעון קיץ)
    var tParts = plannedDep.trim().split(":");
    var localH = parseInt(tParts[0], 10);
    var localM = parseInt(tParts[1], 10);

    var depUtc = new Date(Date.UTC(parseInt(year, 10), parseInt(month, 10) - 1, parseInt(day, 10), localH - 3, localM, 0));
    var fromIso = new Date(depUtc.getTime() - 10 * 60000).toISOString();
    var toIso = new Date(depUtc.getTime() + 25 * 60000).toISOString();

    try {
      var rides = [];
      for (var l = 0; l < lineRefs.length; l++) {
        var queryUrl = OPENBUS_BASE_URL + "/siri_rides/list?scheduled_start_time_from=" + encodeURIComponent(fromIso) +
                       "&scheduled_start_time_to=" + encodeURIComponent(toIso) +
                       "&siri_route__line_ref=" + encodeURIComponent(lineRefs[l]) +
                       "&limit=5";
        var rRes = UrlFetchApp.fetch(queryUrl, { muteHttpExceptions: true });
        if (rRes.getResponseCode() === 200) {
          var rData = JSON.parse(rRes.getContentText());
          if (rData && rData.length > 0) {
            rides = rData;
            break;
          }
        }
      }

      if (rides.length === 0 && operatorRef) {
        var fbUrl = OPENBUS_BASE_URL + "/siri_rides/list?scheduled_start_time_from=" + encodeURIComponent(fromIso) +
                    "&scheduled_start_time_to=" + encodeURIComponent(toIso) +
                    "&siri_route__operator_ref=" + encodeURIComponent(operatorRef) +
                    "&limit=10";
        var fbRes = UrlFetchApp.fetch(fbUrl, { muteHttpExceptions: true });
        if (fbRes.getResponseCode() === 200) {
          var fbData = JSON.parse(fbRes.getContentText());
          if (fbData && fbData.length > 0) rides = fbData;
        }
      }

      if (rides.length > 0) {
        var ride = rides[0];
        var sUrl = OPENBUS_BASE_URL + "/siri_ride_stops/list?siri_ride_id=" + ride.id + "&gtfs_stop__code=" + encodeURIComponent(stopCode);
        var sRes = UrlFetchApp.fetch(sUrl, { muteHttpExceptions: true });

        if (sRes.getResponseCode() === 200) {
          var stops = JSON.parse(sRes.getContentText());
          if (stops && stops.length > 0) {
            var recTime = stops[0].nearest_siri_vehicle_location__recorded_at_time || stops[0].actual_arrival_time;
            if (recTime) {
              var actObj = new Date(recTime);
              var actTime = Utilities.formatDate(actObj, "Asia/Jerusalem", "HH:mm");

              var pParts = plannedArr.trim().split(":");
              var planMinutes = parseInt(pParts[0], 10) * 60 + parseInt(pParts[1], 10);
              var actMinutes = actObj.getHours() * 60 + actObj.getMinutes();
              var diff = actMinutes - planMinutes;

              sheet.getRange(i + 1, 10).setValue(actTime);
              sheet.getRange(i + 1, 11).setValue(diff);
              sheet.getRange(i + 1, 12).setValue(ride.vehicle_ref || "");
              sheet.getRange(i + 1, 13).setValue(diff > 15 ? "איחור חמור (" + diff + " דק')" : (diff > 5 ? "איחור (" + diff + " דק')" : "תקין"));
            } else {
              sheet.getRange(i + 1, 13).setValue("אין איכון מדויק בתחנה");
            }
          } else {
            sheet.getRange(i + 1, 13).setValue("אין דיגום בתחנה זו");
          }
        }
      } else {
        sheet.getRange(i + 1, 13).setValue("לא אותרה יציאה ב-SIRI");
      }

      countProcessed++;
      Utilities.sleep(120);
    } catch (err) {
      Logger.log("שגיאה בשורה " + (i + 1) + ": " + err);
    }
  }

  SpreadsheetApp.flush();
  Logger.log("סיום ריצה. שורות שעובדו: " + countProcessed);
}
