/**
 * קוד להדבקה ב-Google Apps Script בתוך ה-Google Sheet
 * תפריט: הרחבות (Extensions) -> Apps Script -> הדבק קוד זה -> פריסה (Deploy) -> יישום אינטרנט חדש (New Web App)
 * הגדר: גישה לכל אחד (Anyone)
 * העתק את ה-URL המתקבל והדבק ב-.env כ-SHEETS_WEBHOOK_URL
 */
function doPost(e) {
  try {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
    var data = JSON.parse(e.postData.contents);
    
    sheet.appendRow([
      data.ref_number,
      data.created_at,
      data.full_name,
      data.id_number,
      data.phone,
      data.email,
      data.line_number,
      data.operator,
      data.stop_code,
      data.stop_name,
      data.direction,
      data.date_time,
      data.license_plate,
      data.driver_name,
      data.nearby_plates,
      data.category,
      data.details,
      data.status,
      "" // הערות מעקב
    ]);
    
    return ContentService.createTextOutput(JSON.stringify({result: "success"})).setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({result: "error", error: err.toString()})).setMimeType(ContentService.MimeType.JSON);
  }
}
