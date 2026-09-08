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
from transit_api import get_line_info, find_license_plates
from notifier import send_complaint_emails, fill_online_form_playwright

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

(
    FULL_NAME,
    ID_NUMBER,
    PHONE,
    EMAIL,
    LINE_NUMBER,
    SELECT_PLATE,
    LOCATION,
    DATE_TIME,
    CATEGORY,
    DETAILS,
    CONFIRMATION
) = range(11)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 שלום! אני הבוט לדיווח תלונות על אוטובוסים בירושלים.\n"
        "התלונה תועבר ישירות למשרד התחבורה ולמחזיק תיק התחבורה בעיריית ירושלים.\n\n"
        "נתחיל: מה שמך המלא?"
    )
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
    await update.message.reply_text("מה כתובת האימייל שלך? (לקבלת העתק תלונה)")
    return EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['email'] = update.message.text.strip()
    await update.message.reply_text("מה מספר קו האוטובוס?")
    return LINE_NUMBER

async def get_line_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    line_number = update.message.text.strip()
    context.user_data['line_number'] = line_number

    # זיהוי אוטומטי של המפעיל
    line_info = await get_line_info(line_number)
    context.user_data['operator'] = line_info['operator']

    # איתור לוחיות רישוי בזמן אמת ממאגרי SIRI
    plates = await find_license_plates(line_number, datetime.now())

    if plates:
        keyboard = [
            [InlineKeyboardButton(f"🚌 לוחית: {p}", callback_data=f"plate_{p}")]
            for p in plates
        ]
        keyboard.append([InlineKeyboardButton("לא מופיע כאן / לא ידוע", callback_data="plate_unknown")])
        
        await update.message.reply_text(
            f"✅ קו {line_number} שייך לחברת: **{line_info['operator']}**\n"
            f"ממערכות הניטור של משרד התחבורה, אותרו האוטובוסים הבאים שפעלו בקו. בחר מספר רישוי:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return SELECT_PLATE
    else:
        context.user_data['license_plate'] = "לא ידוע"
        await update.message.reply_text(
            f"✅ קו {line_number} שייך לחברת: **{line_info['operator']}**\n"
            "היכן התרחש המקרה בירושלים? (שם רחוב / צומת / תחנה):"
        )
        return LOCATION

async def select_plate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plate = query.data.replace("plate_", "")
    context.user_data['license_plate'] = "לא ידוע" if plate == "unknown" else plate

    await query.edit_message_text(f"מספר רישוי שנבחר: {context.user_data['license_plate']}")
    await query.message.reply_text("היכן התרחש המקרה בירושלים? (שם רחוב / תחנה):")
    return LOCATION

async def get_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['location'] = update.message.text.strip()
    await update.message.reply_text("מתי התרחש המקרה? (לדוגמה: היום ב-08:30):")
    return DATE_TIME

async def get_date_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['date_time'] = update.message.text.strip()

    categories = [
        [InlineKeyboardButton("אי-עצירה בתחנה", callback_data="cat_אי-עצירה בתחנה")],
        [InlineKeyboardButton("איחור משמעותי / אי-הגעה", callback_data="cat_איחור או אי-הגעה")],
        [InlineKeyboardButton("התנהגות נהג / שירות", callback_data="cat_התנהגות נהג")],
        [InlineKeyboardButton("דילוג על מסלול / נהיגה מסוכנת", callback_data="cat_נהיגה מסוכנת")],
    ]
    await update.message.reply_text(
        "בחר את סוג התלונה העיקרי:",
        reply_markup=InlineKeyboardMarkup(categories)
    )
    return CATEGORY

async def select_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("cat_", "")
    context.user_data['category'] = category

    await query.edit_message_text(f"סוג התלונה: {category}")
    await query.message.reply_text("אנא פרט בקצרה מה התרחש באירוע:")
    return DETAILS

async def get_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['details'] = update.message.text.strip()
    data = context.user_data

    summary = (
        "📋 **סיכום התלונה לפני שיגור:**\n\n"
        f"• **שם:** {data.get('full_name')} (ת\"ז: {data.get('id_number')})\n"
        f"• **טלפון:** {data.get('phone')} | **דוא\"ל:** {data.get('email')}\n"
        f"• **קו:** {data.get('line_number')} ({data.get('operator')})\n"
        f"• **מספר רישוי:** {data.get('license_plate')}\n"
        f"• **מועד:** {data.get('date_time')}\n"
        f"• **מיקום:** {data.get('location')}\n"
        f"• **נושא:** {data.get('category')}\n"
        f"• **פירוט:** {data.get('details')}\n\n"
        f"הפנייה תועבר בדוא\"ל רשמי אל:\n"
        f"1. משרד התחבורה (`{MOT_EMAIL}`)\n"
        f"2. מחזיק תיק התחבורה בעיריית ירושלים (`{JERUSALEM_TRANSPORT_EMAIL}`)\n"
        f"3. עותק יישלח אליך ל-`{data.get('email')}`"
    )

    confirm_buttons = [
        [InlineKeyboardButton("🚀 אשר ושגר תלונה", callback_data="confirm_send")],
        [InlineKeyboardButton("❌ בטל", callback_data="confirm_cancel")]
    ]
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(confirm_buttons), parse_mode="Markdown")
    return CONFIRMATION

async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_send":
        await query.edit_message_text("מפיץ את התלונה בדוא\"ל ומפעיל מילוי טופס...")
        
        email_sent = send_complaint_emails(context.user_data)
        await fill_online_form_playwright(context.user_data)

        if email_sent:
            await query.message.reply_text(
                "✅ **התלונה שוגרה בהצלחה!**\n\n"
                f"נשלחה פנייה למשרד התחבורה (`{MOT_EMAIL}`) "
                f"ולמחזיק תיק התחבורה בעיריית ירושלים (`{JERUSALEM_TRANSPORT_EMAIL}`).\n"
                "העתק נשלח גם לתיבת הדוא\"ל שלך.",
                parse_mode="Markdown"
            )
        else:
            await query.message.reply_text(
                "הייתה בעיה בשליחת הדוא\"ל. ניתן להעתיק את הנוסח ולשלוח ישירות ל-pniotcrm@mot.gov.il"
            )
    else:
        await query.edit_message_text("התלונה בוטלה ולא נשלחה.")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("הפעולה בוטלה.")
    return ConversationHandler.END

def main():
    if not TELEGRAM_BOT_TOKEN:
        print("שגיאה: TELEGRAM_BOT_TOKEN חסר. אנא הגדר אותו בקובץ .env")
        return

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            FULL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_full_name)],
            ID_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_id_number)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
            LINE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_line_number)],
            SELECT_PLATE: [CallbackQueryHandler(select_plate_callback, pattern="^plate_")],
            LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_location)],
            DATE_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date_time)],
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
