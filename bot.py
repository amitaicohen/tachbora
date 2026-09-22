import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from config import TELEGRAM_BOT_TOKEN, MOT_EMAIL, JERUSALEM_TRANSPORT_EMAIL
from transit_api import get_line_info, get_stop_info, search_stops_by_name, find_station_arrivals_15min, get_line_61_live_status
from notifier import submit_mot_complaint_and_get_ref, send_complaint_emails_with_ref, GOV_FORM_URL
from database import save_complaint, get_user_profile, save_user_profile
from sheets_sync import append_complaint_and_send_email_via_google, SPREADSHEET_URL, SHEETS_WEBHOOK_URL
from date_parser import parse_hebrew_datetime

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

(
    CONFIRM_SAVED_USER,
    FIRST_NAME,
    LAST_NAME,
    ID_NUMBER,
    PHONE,
    EMAIL,
    CITY,
    STREET,
    LINE_NUMBER,
    STOP_CODE,
    SELECT_STOP,
    DIRECTION,
    DATE_TIME,
    SELECT_PLATE,
    DRIVER_NAME,
    CATEGORY,
    DETAILS,
    CONFIRMATION
) = range(18)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data['telegram_id'] = user_id

    # בדיקה האם המשתמש כבר שמור במערכת
    profile = get_user_profile(user_id)
    if profile:
        context.user_data.update(profile)
        buttons = [
            [InlineKeyboardButton("כן, השתמש בפרטים אלו", callback_data="user_use_saved")],
            [InlineKeyboardButton("לא, עדכן פרטים אישיים", callback_data="user_edit")]
        ]
        msg = (
            f"👋 שלום {profile['first_name']} {profile['last_name']}! זיהיתי אותך במערכת.\n"
            f"• תעודת זהות: {profile['id_number']}\n"
            f"• טלפון נייד: {profile['phone']}\n"
            f"• דוא\"ל: {profile['email']}\n"
            f"• כתובת למשלוח דואר: {profile['street']}, {profile['city']}\n\n"
            "האם להשתמש בפרטים אלו עבור התלונה?"
        )
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(buttons))
        return CONFIRM_SAVED_USER
    else:
        await update.message.reply_text(
            "👋 שלום! אני הבוט לרישום תלונות על אוטובוסים בירושלים.\n"
            "הפנייה מועברת למשרד התחבורה ולעירייה בהתאם למבנה השדות הרשמי של טופס משרד התחבורה.\n\n"
            "נתחיל בכמה פרטי זיהוי אישיים (שיישמרו לפניות עתידיות):\n"
            "מה **שמך הפרטי**?",
            parse_mode="Markdown"
        )
        return FIRST_NAME

async def confirm_saved_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "user_use_saved":
        await query.edit_message_text(f"מעולה, נמשיך עם פרטי הזיהוי של {context.user_data.get('first_name', '')}.")
        await query.message.reply_text("מה **מספר קו האוטובוס** שעליו תרצה לדווח? (למשל: 61, 68, 15):", parse_mode="Markdown")
        return LINE_NUMBER
    else:
        await query.edit_message_text("בסדר, נעדכן את הפרטים מחדש.")
        await query.message.reply_text("מה **שמך הפרטי**?", parse_mode="Markdown")
        return FIRST_NAME

async def get_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['first_name'] = update.message.text.strip()
    await update.message.reply_text("מה **שם המשפחה** שלך?", parse_mode="Markdown")
    return LAST_NAME

async def get_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['last_name'] = update.message.text.strip()
    context.user_data['full_name'] = f"{context.user_data['first_name']} {context.user_data['last_name']}".strip()
    await update.message.reply_text("מה **מספר תעודת הזהות** שלך? (9 ספרות - שדה חובה במשרד התחבורה):", parse_mode="Markdown")
    return ID_NUMBER

async def get_id_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['id_number'] = update.message.text.strip()
    await update.message.reply_text("מה **מספר הטלפון הנייד** שלך?", parse_mode="Markdown")
    return PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['phone'] = update.message.text.strip()
    await update.message.reply_text("מה **כתובת הדוא\"ל** שלך? (לקבלת אישור ומספר פנייה):", parse_mode="Markdown")
    return EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['email'] = update.message.text.strip()
    await update.message.reply_text("מה **עיר / יישוב המגורים** שלך? (למשל: ירושלים):", parse_mode="Markdown")
    return CITY

async def get_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['city'] = update.message.text.strip()
    await update.message.reply_text("מה **הרחוב ומספר הבית** שלך? (שדה חובה בטופס משרד התחבורה למשלוח דואר):", parse_mode="Markdown")
    return STREET

async def get_street(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['street'] = update.message.text.strip()

    # שמירת הפרופיל המלא במסד הנתונים
    save_user_profile(
        context.user_data['telegram_id'],
        context.user_data['first_name'],
        context.user_data['last_name'],
        context.user_data['id_number'],
        context.user_data['phone'],
        context.user_data['email'],
        context.user_data['city'],
        context.user_data['street']
    )

    await update.message.reply_text(
        "✅ פרטי הזיהוי והכתובת שלך נשמרו במערכת לפניות עתידיות!\n\n"
        "מה **מספר קו האוטובוס** שעליו תרצה לדווח? (למשל: 61, 68, 77):",
        parse_mode="Markdown"
    )
    return LINE_NUMBER

async def get_line_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    line_number = update.message.text.strip()
    context.user_data['line_number'] = line_number

    # זיהוי אוטומטי של המפעיל
    info = await get_line_info(line_number)
    context.user_data['operator'] = info['operator']

    await update.message.reply_text(
        f"✅ קו {line_number} מופעל על ידי **{info['operator']}**.\n\n"
        "מה **מספר התחנה (קוד תחנה)** שבה אירע המקרה?\n"
        "(הקלד מספר תחנה כמו `2135` או הקלד את שם התחנה/הרחוב כגון: 'ההגנה', 'בר כוכבא', 'מרכז מסחרי')",
        parse_mode="Markdown"
    )
    return STOP_CODE

async def get_stop_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # אם המשתמש הזין ספרות - מדובר בקוד תחנה ישיר
    if text.isdigit():
        context.user_data['stop_code'] = text
        stop_info = await get_stop_info(text)
        context.user_data['stop_name'] = stop_info['stop_name']
        await update.message.reply_text(
            f"🚏 תחנה #{text}: **{stop_info['stop_name']}** (זוהתה בהצלחה).\n\n"
            "לאיזה **כיוון נסיעה** נסע האוטובוס? (למשל: לכיוון גבעת התחמושת, מרכז העיר, תלפיות):",
            parse_mode="Markdown"
        )
        return DIRECTION

    # אם המשתמש הזין שם/טקסט - חיפוש תחנות תואמות במאגר OpenBus
    await update.message.reply_text(f"🔍 מחפש תחנות התואמות ל-'**{text}**' במאגר התחבורה הציבורית...", parse_mode="Markdown")
    matching_stops = await search_stops_by_name(text, city=context.user_data.get('city', 'ירושלים'), limit=6)

    if not matching_stops:
        context.user_data['stop_code'] = "לא צוין"
        context.user_data['stop_name'] = text
        await update.message.reply_text(
            f"🚏 נרשם מיקום חופשי: **{text}**.\n\n"
            "לאיזה **כיוון נסיעה** נסע האוטובוס? (למשל: לכיוון מרכז העיר, גבעת התחמושת):",
            parse_mode="Markdown"
        )
        return DIRECTION

    # יצירת כפתורי בחירה לתחנות שנמצאו
    keyboard = []
    for s in matching_stops:
        btn_text = f"🚏 {s['code']}: {s['name']}"
        cb_data = f"stop_{s['code']}|{s['name'][:30]}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=cb_data)])

    keyboard.append([InlineKeyboardButton("המשך ללא קוד תחנה (מיקום חופשי)", callback_data="stop_manual")])

    context.user_data['temp_stop_query'] = text
    await update.message.reply_text(
        "נמצאו מספר תחנות תואמות. אנא בחר את התחנה המדויקת:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_STOP

async def select_stop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "stop_manual":
        context.user_data['stop_code'] = "לא צוין"
        context.user_data['stop_name'] = context.user_data.get('temp_stop_query', 'ירושלים')
        await query.edit_message_text(f"נרשם מיקום חופשי: {context.user_data['stop_name']}")
    else:
        raw_data = query.data.replace("stop_", "")
        parts = raw_data.split("|")
        code = parts[0]
        name = parts[1] if len(parts) > 1 else f"תחנה {code}"
        context.user_data['stop_code'] = code
        context.user_data['stop_name'] = name
        await query.edit_message_text(f"🚏 נבחרה תחנה #{code}: **{name}**", parse_mode="Markdown")

    await query.message.reply_text(
        "לאיזה **כיוון נסיעה** נסע האוטובוס?\n(למשל: לכיוון מרכז העיר, לכיוון גבעת התחמושת):",
        parse_mode="Markdown"
    )
    return DIRECTION

async def get_direction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['direction'] = update.message.text.strip()
    await update.message.reply_text(
        "מתי אירע המקרה?\n"
        "אפשר לכתוב בשפה חופשית (למשל: 'היום ב-08:15', 'אתמול ב-14:30', 'חמישי ב-7:20'):"
    )
    return DATE_TIME

async def get_date_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_time = update.message.text.strip()
    parsed_dt = parse_hebrew_datetime(raw_time)

    # פיצול תאריך ושעה בנפרד בהתאם לטופס משרד התחבורה
    incident_date = parsed_dt.strftime("%d/%m/%Y")
    incident_time = parsed_dt.strftime("%H:%M")
    formatted_dt = f"{incident_date} {incident_time}"

    context.user_data['incident_date'] = incident_date
    context.user_data['incident_time'] = incident_time
    context.user_data['date_time'] = formatted_dt
    context.user_data['parsed_dt'] = parsed_dt

    await update.message.reply_text(
        f"📅 מועד שזוהה: **{formatted_dt}** (תאריך: {incident_date}, שעה: {incident_time}).\n"
        "בודק כעת במאגר זמן אמת (SIRI) את כל האוטובוסים שחלפו בתחנה בחלון של 15 דקות לפני ואחרי...",
        parse_mode="Markdown"
    )

    stop_code = context.user_data.get('stop_code')
    line_num = context.user_data.get('line_number')
    arrivals = await find_station_arrivals_15min(stop_code, line_num, parsed_dt)
    context.user_data['nearby_plates'] = arrivals

    keyboard = []
    if arrivals:
        for arr in arrivals[:8]:
            p = arr['license_plate']
            keyboard.append([InlineKeyboardButton(f"🚌 לוחית: {p} (קו {arr.get('line')})", callback_data=f"plate_{p}")])

    keyboard.append([InlineKeyboardButton("הקלד לוחית רישוי ידנית", callback_data="plate_manual")])
    keyboard.append([InlineKeyboardButton("מספר הרישוי אינו ידוע", callback_data="plate_unknown")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "בחר את מספר הרישוי של האוטובוס (או בחר הזנה ידנית / לא ידוע):",
        reply_markup=reply_markup
    )
    return SELECT_PLATE

async def select_plate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "plate_unknown":
        context.user_data['license_plate'] = "לא ידוע"
        await query.edit_message_text("נרשם: מספר רישוי לא ידוע.")
        return await ask_driver_name(query.message)
    elif query.data == "plate_manual":
        await query.edit_message_text("אנא הקלד כעת את מספר לוחית הרישוי של האוטובוס:")
        return SELECT_PLATE
    else:
        plate = query.data.replace("plate_", "")
        context.user_data['license_plate'] = plate
        await query.edit_message_text(f"מספר רישוי שנבחר: {plate}")
        return await ask_driver_name(query.message)

async def get_manual_plate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['license_plate'] = update.message.text.strip()
    return await ask_driver_name(update.message)

async def ask_driver_name(message):
    await message.reply_text(
        "האם ידוע לך **שם הנהג או מספר תג הנהג**?\n"
        "(במשרד התחבורה שמות הנהגים אינם פומביים, אך לפי לוחית הרישוי והשעה המפעיל מאתר את הנהג בסידור העבודה. אם אינו ידוע, השב 'לא'):",
        parse_mode="Markdown"
    )
    return DRIVER_NAME

async def get_driver_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() in ["לא", "אין", "לא יודע", "לא ידוע"]:
        context.user_data['driver_name'] = "לא צוין (יאותר במשרד התחבורה לפי מספר הרישוי וסידור העבודה)"
    else:
        context.user_data['driver_name'] = text

    # קטגוריות תלונה רשמיות לפי טופס משרד התחבורה
    categories = [
        [InlineKeyboardButton("אי-עצירה בתחנה / דילוג על תחנה", callback_data="cat_אי-עצירה בתחנה")],
        [InlineKeyboardButton("אי-יציאה של הקו / איחור משמעותי", callback_data="cat_אי-יציאה או איחור")],
        [InlineKeyboardButton("התנהגות נהג ושירות", callback_data="cat_התנהגות נהג ושירות")],
        [InlineKeyboardButton("נהיגה מסוכנת / דילוג על מסלול", callback_data="cat_נהיגה מסוכנת")],
        [InlineKeyboardButton("עומס חריג / אי-העלאת נוסעים", callback_data="cat_עומס חריג")],
        [InlineKeyboardButton("אחר", callback_data="cat_נושא אחר")]
    ]
    await update.message.reply_text(
        "בחר את **מהות התלונה העיקרית**:",
        reply_markup=InlineKeyboardMarkup(categories),
        parse_mode="Markdown"
    )
    return CATEGORY

async def select_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("cat_", "")
    context.user_data['category'] = category

    await query.edit_message_text(f"מהות התלונה: **{category}**", parse_mode="Markdown")
    await query.message.reply_text("אנא פרט בקצרה מה בדיוק קרה באירוע:")
    return DETAILS

async def get_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['details'] = update.message.text.strip()
    data = context.user_data

    summary = (
        "📋 **סיכום התלונה לפי מבנה טופס משרד התחבורה:**\n\n"
        "■ **פרטי הפונה (המתלונן):**\n"
        f"• שם מלא: {data.get('first_name')} {data.get('last_name')} (ת\"ז: {data.get('id_number')})\n"
        f"• טלפון נייד: {data.get('phone')} | דוא\"ל: {data.get('email')}\n"
        f"• כתובת למשלוח דואר: {data.get('street')}, {data.get('city')}\n\n"
        "■ **פרטי הנסיעה והאירוע:**\n"
        f"• קו ומפעיל: קו {data.get('line_number')} ({data.get('operator')})\n"
        f"• תחנת עלייה: {data.get('stop_name')} (קוד: {data.get('stop_code')})\n"
        f"• כיוון נסיעה / יעד: {data.get('direction')}\n"
        f"• תאריך ושעה: {data.get('incident_date')} בשעה {data.get('incident_time')}\n"
        f"• מספר רישוי של האוטובוס: {data.get('license_plate')}\n"
        f"• פרטי הנהג: {data.get('driver_name')}\n\n"
        "■ **מהות התלונה ופירוט:**\n"
        f"• נושא: {data.get('category')}\n"
        f"• פירוט: {data.get('details')}\n\n"
        "בלחיצה על 'שגר תלונה', הנתונים יישמרו במסד הנתונים וב-Google Sheets, וישוגר דוא\"ל רשמי מובנה למשרד התחבורה ולעירייה עם מספר מעקב ייחודי."
    )

    confirm_buttons = [
        [InlineKeyboardButton("🚀 אשר ושגר תלונה רשמית", callback_data="confirm_send")],
        [InlineKeyboardButton("❌ בטל", callback_data="confirm_cancel")]
    ]
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(confirm_buttons), parse_mode="Markdown")
    return CONFIRMATION

async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_send":
        await query.edit_message_text("מפיק מספר פנייה, שומר את הנתונים ומשגר את הדוא\"ל הרשמי...")

        # 1. הפקת מספר פנייה ייחודי למעקב
        ref_number = await submit_mot_complaint_and_get_ref(context.user_data)

        # 2. שמירה במסד הנתונים המקומי (SQLite)
        save_complaint(context.user_data, ref_number)

        # 3. סנכרון ל-Google Sheets ושליחת מייל דרך Google Apps Script (אם מוגדר)
        google_result = await append_complaint_and_send_email_via_google(context.user_data, ref_number)

        # 4. ניסיון שליחה דרך SMTP
        smtp_result = send_complaint_emails_with_ref(context.user_data, ref_number)

        mail_delivered = google_result.get("success") or smtp_result.get("success")

        email_status_msg = ""
        if mail_delivered:
            email_status_msg = f"✉️ **נשלח אימייל רשמי עם מספר הפנייה אל:** `{context.user_data.get('email')}` ומשרד התחבורה."
        else:
            email_status_msg = (
                "ℹ️ **סטטוס שליחת המייל:**\n"
                "הפנייה נשמרה בהצלחה במערכת וב-Google Sheets. טרם הוגדר Webhook של Google Apps Script או פרטי SMTP לשליחת דוא\"ל אוטומטי."
            )

        await query.message.reply_text(
            f"✅ **הפנייה נוצרה ונשמרה בהצלחה!**\n\n"
            f"📌 **מספר פנייה למעקב:** `{ref_number}`\n"
            f"{email_status_msg}\n\n"
            f"📊 **גיליון המעקב שלך ב-Google Sheets:**\n[קישור לצפייה בגיליון]({SPREADSHEET_URL})\n\n"
            f"🔗 קישור ישיר לטופס משרד התחבורה: [טופס פניות הציבור המקוון]({GOV_FORM_URL})\n\n"
            "שים לב: מספר הפנייה ישמש אותך למעקב ישיר מול פניות הציבור במשרד התחבורה.",
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text("הפעולה בוטלה.")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("התהליך בוטל.")
    return ConversationHandler.END



async def line61_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 בודק נתוני אמת ב-OpenBus עבור קו 61 בתחנה 1412 (מרכז מסחרי / ההגנה)...")
    live_buses = await get_line_61_live_status("1412")
    if live_buses:
        msg = "🚌 **סטטוס זמן אמת לקו 61 (הר הצופים -> רמות | תחנה 1412):**\n\n"
        for b in live_buses[:6]:
            plate = b.get("license_plate", "")
            sched = b.get("scheduled_time", "")
            msg += f"• לוחית רישוי: `{plate}` | שעת יציאה: {sched}\n"
        msg += f"\n📊 לצפייה בגיליון המעקב המלא ל-30 יום אחורה:\n[קישור לגיליון Google Sheets]({SPREADSHEET_URL})"
        await update.message.reply_text(msg, parse_mode="Markdown")
    else:
        await update.message.reply_text(
            f"🚌 **קו 61 בירושלים (אקסטרה ירושלים)**\n"
            f"מסלול: מהר הצופים לכיוון רמות (מסוף אצ\"ג) דרך תחנה 1412 (מרכז מסחרי/ההגנה).\n\n"
            f"📊 לצפייה בגיליון המעקב המלא הכולל 850+ נסיעות והשוואת זמני אמת:\n"
            f"[קישור לגיליון Google Sheets]({SPREADSHEET_URL})",
            parse_mode="Markdown"
        )

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CONFIRM_SAVED_USER: [CallbackQueryHandler(confirm_saved_user_callback, pattern="^user_")],
            FIRST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_first_name)],
            LAST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_last_name)],
            ID_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_id_number)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
            CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_city)],
            STREET: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_street)],
            LINE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_line_number)],
            STOP_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_stop_code)],
            SELECT_STOP: [CallbackQueryHandler(select_stop_callback, pattern="^stop_")],
            DIRECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_direction)],
            DATE_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date_time)],
            SELECT_PLATE: [
                CallbackQueryHandler(select_plate_callback, pattern="^plate_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_manual_plate)
            ],
            DRIVER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_driver_name)],
            CATEGORY: [CallbackQueryHandler(select_category_callback, pattern="^cat_")],
            DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_details)],
            CONFIRMATION: [CallbackQueryHandler(handle_confirmation, pattern="^confirm_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("line61", line61_command))
    print("הבוט פועל ומאזין...")
    app.run_polling()

if __name__ == "__main__":
    main()
