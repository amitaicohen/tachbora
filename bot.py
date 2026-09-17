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
from transit_api import get_line_info, get_stop_info, find_station_arrivals_15min
from notifier import submit_mot_complaint_and_get_ref, send_complaint_emails_with_ref, GOV_FORM_URL
from database import save_complaint, get_user_profile, save_user_profile
from sheets_sync import append_complaint_to_google_sheets, SPREADSHEET_URL
from date_parser import parse_hebrew_datetime

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

(
    CONFIRM_SAVED_USER,
    FULL_NAME,
    ID_NUMBER,
    PHONE,
    EMAIL,
    LINE_NUMBER,
    STOP_CODE,
    DIRECTION,
    DATE_TIME,
    SELECT_PLATE,
    DRIVER_NAME,
    CATEGORY,
    DETAILS,
    CONFIRMATION
) = range(14)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data['telegram_id'] = user_id

    # בדיקה האם המשתמש כבר שמור במערכת
    profile = get_user_profile(user_id)
    if profile:
        context.user_data.update(profile)
        buttons = [
            [InlineKeyboardButton(f"כן, השתמש בפרטים אלו", callback_data="user_use_saved")],
            [InlineKeyboardButton("לא, עדכן פרטים אישיים", callback_data="user_edit")]
        ]
        msg = (
            f"👋 שלום {profile['full_name']}! זיהיתי אותך במערכת.\n"
            f"• תעודת זהות: {profile['id_number']}\n"
            f"• טלפון: {profile['phone']}\n"
            f"• דוא\"ל: {profile['email']}\n\n"
            "האם להשתמש בפרטים אלו עבור התלונה?"
        )
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(buttons))
        return CONFIRM_SAVED_USER
    else:
        await update.message.reply_text(
            "👋 שלום! אני הבוט לרישום תלונות על אוטובוסים בירושלים.\n"
            "התלונה מועברת למערכת משרד התחבורה ולמחזיק תיק התחבורה בעירייה, ומספר הפנייה יישלח למייל שלך.\n\n"
            "נתחיל: מה שמך המלא?"
        )
        return FULL_NAME

async def confirm_saved_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "user_use_saved":
        await query.edit_message_text(f"מעולה, נמשיך עם פרטי הזיהוי של {context.user_data['full_name']}.")
        await query.message.reply_text("מה מספר קו האוטובוס שעליו תרצה לדווח?")
        return LINE_NUMBER
    else:
        await query.edit_message_text("בסדר, נעדכן את הפרטים.")
        await query.message.reply_text("מה שמך המלא?")
        return FULL_NAME

async def get_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['full_name'] = update.message.text.strip()
    await update.message.reply_text("מה מספר תעודת הזהות שלך?")
    return ID_NUMBER

async def get_id_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['id_number'] = update.message.text.strip()
    await update.message.reply_text("מה מספר הטלפון הנייד שלך?")
    return PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['phone'] = update.message.text.strip()
    await update.message.reply_text("מה כתובת האימייל שלך? (לקבלת העתק ומספר פנייה)")
    return EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['email'] = update.message.text.strip()

    # שמירת פרטי המשתמש במסד הנתונים כדי שיזכור אותו בפעמים הבאות!
    save_user_profile(
        context.user_data['telegram_id'],
        context.user_data['full_name'],
        context.user_data['id_number'],
        context.user_data['phone'],
        context.user_data['email']
    )

    await update.message.reply_text(
        "✅ פרטי הזיהוי שלך נשמרו במערכת לפניות עתידיות.\n\n"
        "מה מספר קו האוטובוס שעליו תרצה לדווח?"
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
        "(לדוגמה: 2134, או כתוב את שם הרחוב/צומת אם המספר לא ידוע)",
        parse_mode="Markdown"
    )
    return STOP_CODE

async def get_stop_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.isdigit():
        context.user_data['stop_code'] = text
        stop_info = await get_stop_info(text)
        context.user_data['stop_name'] = stop_info['stop_name']
        msg = f"🚏 תחנה #{text}: **{stop_info['stop_name']}** (זוהתה אוטומטית)."
    else:
        context.user_data['stop_code'] = "לא צוין"
        context.user_data['stop_name'] = text
        msg = f"🚏 מיקום התחנה: **{text}**."

    await update.message.reply_text(
        f"{msg}\n\n"
        "לאיזה **כיוון נסיעה** נסע האוטובוס?\n"
        "(לדוגמה: לכיוון מרכז העיר, לכיוון תלפיות, לכיוון הגבעה הצרפתית):",
        parse_mode="Markdown"
    )
    return DIRECTION

async def get_direction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['direction'] = update.message.text.strip()
    await update.message.reply_text(
        "מתי אירע המקרה?\n"
        "אפשר לכתוב בשפה חופשית (למשל: 'חמישי ב-7:20', 'אתמול ב-14:30', 'היום ב-08:15'):"
    )
    return DATE_TIME

async def get_date_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_time = update.message.text.strip()
    parsed_dt = parse_hebrew_datetime(raw_time)
    formatted_dt = parsed_dt.strftime("%d/%m/%Y %H:%M")
    context.user_data['date_time'] = formatted_dt
    context.user_data['parsed_dt'] = parsed_dt

    await update.message.reply_text(
        f"📅 מועד שזוהה: **{formatted_dt}**.\n"
        "בודק כעת במערכות משרד התחבורה (SIRI) את כל האוטובוסים שחלפו בתחנה בחלון של 15 דקות לפני ואחרי...",
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
        "בחר את מספר הרישוי של האוטובוס (או בחר ידני/לא ידוע):",
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
        "(הערה: שמות נהגים אינם פומביים במאגר משרד התחבורה מטעמי פרטיות, אך לפי מספר הרישוי והשעה המפעיל מאתר את הנהג בסידור העבודה. אם אינו ידוע, השב 'לא'):",
        parse_mode="Markdown"
    )
    return DRIVER_NAME

async def get_driver_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() in ["לא", "אין", "לא יודע", "לא ידוע"]:
        context.user_data['driver_name'] = "לא צוין (יאותר במשרד התחבורה לפי מספר הרישוי וסידור העבודה)"
    else:
        context.user_data['driver_name'] = text

    categories = [
        [InlineKeyboardButton("אי-עצירה בתחנה", callback_data="cat_אי-עצירה בתחנה")],
        [InlineKeyboardButton("איחור משמעותי / אי-יציאה של הקו", callback_data="cat_איחור או אי-יציאה")],
        [InlineKeyboardButton("התנהגות נהג ושירות", callback_data="cat_התנהגות נהג")],
        [InlineKeyboardButton("דילוג על מסלול / נהיגה מסוכנת", callback_data="cat_נהיגה מסוכנת")],
    ]
    await update.message.reply_text(
        "בחר את מהות התלונה העיקרית:",
        reply_markup=InlineKeyboardMarkup(categories)
    )
    return CATEGORY

async def select_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("cat_", "")
    context.user_data['category'] = category

    await query.edit_message_text(f"מהות התלונה: {category}")
    await query.message.reply_text("אנא פרט בקצרה מה בדיוק קרה באירוע:")
    return DETAILS

async def get_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['details'] = update.message.text.strip()
    data = context.user_data

    summary = (
        "📋 **סיכום התלונה ליצירת פנייה רשמית:**\n\n"
        f"• **מתלונן:** {data.get('full_name')} (ת\"ז: {data.get('id_number')})\n"
        f"• **טלפון ודוא\"ל:** {data.get('phone')} | {data.get('email')}\n"
        f"• **קו ומפעיל:** קו {data.get('line_number')} ({data.get('operator')})\n"
        f"• **תחנה:** {data.get('stop_name')} (קוד: {data.get('stop_code')})\n"
        f"• **כיוון נסיעה:** {data.get('direction')}\n"
        f"• **מועד מדווח:** {data.get('date_time')}\n"
        f"• **מספר רישוי:** {data.get('license_plate')}\n"
        f"• **פרטי נהג:** {data.get('driver_name')}\n"
        f"• **נושא התלונה:** {data.get('category')}\n"
        f"• **פירוט:** {data.get('details')}\n\n"
        "בלחיצה על אישור, המערכת תיצור פנייה רשמית במשרד התחבורה, תשמור את הנתונים ב-Google Sheets וב-SQLite, ותשלח את מספר הפנייה למייל שלך."
    )

    confirm_buttons = [
        [InlineKeyboardButton("🚀 צור פנייה ושגר תלונה", callback_data="confirm_send")],
        [InlineKeyboardButton("❌ בטל", callback_data="confirm_cancel")]
    ]
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(confirm_buttons), parse_mode="Markdown")
    return CONFIRMATION

async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_send":
        await query.edit_message_text("יוצר פנייה רשמית במערכת משרד התחבורה ושולח את מספר הפנייה למייל...")
        
        # 1. הפקת מספר פנייה ומילוי טופס משרד התחבורה
        ref_number = await submit_mot_complaint_and_get_ref(context.user_data)

        # 2. שמירה במסד הנתונים המקומי (SQLite)
        save_complaint(context.user_data, ref_number)

        # 3. סנכרון ישיר ל-Google Sheets
        await append_complaint_to_google_sheets(context.user_data, ref_number)

        # 4. שליחת דוא\"ל רשמי עם מספר הפנייה למתלונן, למשרד התחבורה ולעירייה
        send_complaint_emails_with_ref(context.user_data, ref_number)

        await query.message.reply_text(
            f"✅ **הפנייה נוצרה ונשמרה בהצלחה!**\n\n"
            f"📌 **מספר פנייה רשמי:** `{ref_number}`\n"
            f"📊 **התלונה נשמרה בבסיס הנתונים וסונכרנה ל-Google Sheets:**\n[קישור לגיליון המעקב שלך]({SPREADSHEET_URL})\n\n"
            f"🔗 קישור לטופס: [טופס פניות הציבור במשרד התחבורה]({GOV_FORM_URL})\n\n"
            f"הודעה עם מספר הפנייה נשלחה אל:\n"
            f"• תיבת המייל שלך (`{context.user_data.get('email')}`)\n"
            f"• משרד התחבורה (`{MOT_EMAIL}`)\n"
            f"• מחזיק תיק התחבורה בעיריית ירושלים (`{JERUSALEM_TRANSPORT_EMAIL}`)",
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text("הפעולה בוטלה.")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("התהליך בוטל.")
    return ConversationHandler.END

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CONFIRM_SAVED_USER: [CallbackQueryHandler(confirm_saved_user_callback, pattern="^user_")],
            FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_full_name)],
            ID_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_id_number)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
            LINE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_line_number)],
            STOP_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_stop_code)],
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
    print("הבוט פועל ומאזין...")
    app.run_polling()

if __name__ == "__main__":
    main()
