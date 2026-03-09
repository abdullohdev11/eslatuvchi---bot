import logging
import asyncio
import json
import os
from datetime import datetime, timedelta
import pytz

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import google.generativeai as genai

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TIMEZONE = "Asia/Tashkent"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(name)

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

tz = pytz.timezone(TIMEZONE)
REMINDERS_FILE = "reminders.json"


def load_reminders():
    if os.path.exists(REMINDERS_FILE):
        with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_reminders(data):
    with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_user_reminders(user_id):
    data = load_reminders()
    return data.get(str(user_id), [])


def save_user_reminders(user_id, reminders):
    data = load_reminders()
    data[str(user_id)] = reminders
    save_reminders(data)


def parse_reminder_with_gemini(text):
    now = datetime.now(tz)
    prompt = (
        "Sen O'zbek tilidagi eslatma botisan. "
        "Foydalanuvchi yozgan matndan vaqt va eslatma matnini ajrat.\n\n"
        "Foydalanuvchi yozdi: " + text + "\n"
        "Hozirgi vaqt: " + now.strftime("%d.%m.%Y %H:%M") + " (Toshkent vaqti)\n\n"
        "Qoidalar:\n"
        "1. Faqat vaqt yozilgan bolsa (masalan 13:00) - bugun o'sha vaqt. "
        "Agar o'tib ketgan bolsa - ertaga.\n"
        "2. Sana ham yozilgan bolsa (masalan 05.03 14:30) - o'sha sanada.\n"
        "3. 1 yildan ko'p bo'lsa - qabul qilma.\n\n"
        "Faqat sof JSON qaytar, boshqa hech narsa yozma:\n"
        '{"success": true, "datetime": "DD.MM.YYYY HH:MM", '
        '"message": "eslatma matni", "error": ""}'
    )
    try:
        response = model.generate_content(prompt)
        raw = response.text.strip()
        # backtick llarni tozalash
        if "
            parts = raw.split("")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    raw = part
                    break
        raw = raw.strip()
        result = json.loads(raw)
        return result
    except Exception as e:
        logger.error("Gemini xatosi: %s", e)
        return {"success": False, "error": "Vaqtni tushunmadim", "datetime": "", "message": ""}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = (
        "Assalamu alaykum! 👋\n\n"
        "✨ <b>Eslatuvchi Bot</b>ga xush kelibsiz!\n\n"
        "Muhim ishlarni unutib qo'yasizmi? Endi bu muammo yo'q!\n"
        "Men sizning <b>shaxsiy yordamchingiz</b> — "
        "har qanday ishni o'z vaqtida eslataman! ⏰\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🚀 <b>Ishlatish juda oson:</b>\n\n"
        "<b>Faqat vaqt:</b>\n"
        "<code>13:00 suv ichaman</code>\n"
        "<code>08:00 dori ichish</code>\n\n"
        "<b>Sana + vaqt:</b>\n"
        "<code>05.03 14:30 shifokorga borish</code>\n"
        "<code>25.12 10:00 bayram tabrigi</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📋 <b>Buyruqlar:</b>\n"
        "/list — Eslatmalarim\n"
        "/help — Yordam\n\n"
        "💡 <i>Birinchi eslatmangizni hoziroq qo'shing!</i>"
    )
    await update.message.reply_text(welcome, parse_mode="HTML")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 <b>Foydalanish qo'llanmasi:</b>\n\n"
        "<b>Eslatma qo'shish:</b>\n"
        "• <code>13:00 suv ichaman</code>\n"
        "• <code>09:30 nonushta</code>\n"
        "• <code>05.03 14:30 shifokor</code>\n"
        "• <code>25.12 10:00 bayram tabrigi</code>\n\n"
        "<b>Qoidalar:</b>\n"
        "✅ Vaqt o'tib ketgan bo'lsa — ertaga eslatadi\n"
        "✅ Sana yozilgan bo'lsa — o'sha kuni eslatadi\n"
        "❌ 1 yildan ko'p — qabul qilinmaydi\n\n"
        "<b>Buyruqlar:</b>\n"
        "/list — Eslatmalar ro'yxati\n"
        "/start — Bosh menyu\n"
        "/help — Ushbu yordam"
    )
    await update.message.reply_text(help_text, parse_mode="HTML")


async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    reminders = get_user_reminders(user_id)
    now = datetime.now(tz)
    active = []
    for r in reminders:
        try:
            dt = tz.localize(datetime.strptime(r["datetime"], "%d.%m.%Y %H:%M"))
            if dt > now:
                active.append(r)
        except Exception:
            pass
    save_user_reminders(user_id, active)
    if not active:
        await update.message.reply_text(
            "📭 Sizda hozircha eslatma yo'q.\n\nQo'shish uchun xabar yozing!"
        )
        return
    active.sort(key=lambda x: datetime.strptime(x["datetime"], "%d.%m.%Y %H:%M"))
    text = "📋 <b>Sizning eslatmalaringiz:</b>\n\n"
    keyboard = []
    for i, r in enumerate(active, 1):
        text += f"{i}. ⏰ <b>{r['datetime']}</b>\n   📝 {r['message']}\n\n"
        keyboard.append(
            [InlineKeyboardButton(
                f"🗑 {i}-eslatmani o'chirish",
                callback_data="delete_" + r["id"]
            )]
        )
    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    await update.message.reply_text("⏳ Qayta ishlanmoqda...")
    result = parse_reminder_with_gemini(text)
    if not result.get("success"):
        await update.message.reply_text(
            "❌ Tushunmadim!\n\n"
            "Namuna:\n"
            "• <code>13:00 suv ichaman</code>\n"
            "• <code>05.03 14:30 shifokor</code>",
            parse_mode="HTML",
        )
        return
    reminder_dt_str = result.get("datetime", "")
    reminder_message = result.get("message", text)
    try:
        reminder_dt = tz.localize(
            datetime.strptime(reminder_dt_str, "%d.%m.%Y %H:%M")
        )
    except Exception:
        await update.message.reply_text(
            "❌ Vaqt formatida xato. Qaytadan urinib ko'ring."
        )
        return
    now = datetime.now(tz)
    if reminder_dt > now + timedelta(days=365):
        await update.message.reply_text(
            "❌ 1 yildan ko'p vaqt uchun eslatma qo'shib bo'lmaydi!"
        )
        return
    reminder_id = str(int(now.timestamp() * 1000))
    reminders = get_user_reminders(user_id)
    reminders.append(
        {
            "id": reminder_id,
            "datetime": reminder_dt_str,
            "message": reminder_message,
            "user_id": user_id,
        }
    )
    save_user_reminders(user_id, reminders)
    delay = (reminder_dt - now).total_seconds()
    context.application.job_queue.run_once(
        send_reminder,
        when=delay,
        data={
            "user_id": user_id,
            "message": reminder_message,
            "reminder_id": reminder_id,
        },
        name=reminder_id,
    )
    await update.message.reply_text(
        "✅ <b>Eslatma qo'shildi!</b>\n\n"
        "⏰ Vaqt: <b>" + reminder_dt_str + "</b>\n"
        "📝 Eslatma: " + reminder_message,
        parse_mode="HTML",
    )
    async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    await context.bot.send_message(
        chat_id=data["user_id"],
        text="🔔 <b>ESLATMA!</b>\n\n📝 " + data["message"],
        parse_mode="HTML",
    )
    reminders = get_user_reminders(data["user_id"])
    save_user_reminders(
        data["user_id"],
        [r for r in reminders if r["id"] != data["reminder_id"]],
    )


async def handle_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    reminder_id = query.data.replace("delete_", "")
    reminders = get_user_reminders(user_id)
    new_reminders = [r for r in reminders if r["id"] != reminder_id]
    if len(new_reminders) < len(reminders):
        save_user_reminders(user_id, new_reminders)
        for job in context.application.job_queue.get_jobs_by_name(reminder_id):
            job.schedule_removal()
        await query.edit_message_text("✅ Eslatma o'chirildi!")
    else:
        await query.edit_message_text("❌ Eslatma topilmadi.")


async def restore_reminders(application):
    now = datetime.now(tz)
    for user_id, reminders in load_reminders().items():
        for r in reminders:
            try:
                dt = tz.localize(
                    datetime.strptime(r["datetime"], "%d.%m.%Y %H:%M")
                )
                if dt > now:
                    application.job_queue.run_once(
                        send_reminder,
                        when=(dt - now).total_seconds(),
                        data={
                            "user_id": int(user_id),
                            "message": r["message"],
                            "reminder_id": r["id"],
                        },
                        name=r["id"],
                    )
            except Exception as e:
                logger.error("Qayta yuklash xatosi: %s", e)


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("list", list_reminders))
    app.add_handler(CallbackQueryHandler(handle_delete, pattern="^delete_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.job_queue.run_once(
        lambda ctx: asyncio.create_task(restore_reminders(app)),
        when=1,
    )
    logger.info("Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)


if name == "main":
    main() 
