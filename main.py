import os
import re
import json
import logging
from telebot import TeleBot, types
from instagrapi import Client

# إعداد الـ Logging لمتابعة الأخطاء في Railway Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# جلب المتغيرات من البيئة
BOT_TOKEN = os.environ.get("BOT_TOKEN")
INSTA_SESSION = os.environ.get("INSTA_SESSION")

if not BOT_TOKEN or not INSTA_SESSION:
    raise ValueError("برجاء ضبط BOT_TOKEN و INSTA_SESSION في متغيرات البيئة!")

bot = TeleBot(BOT_TOKEN)
cl = Client()

def init_instagram():
    """تحميل الجلسة من متغيرات البيئة بدون الحاجة لتسجيل دخول جديد"""
    try:
        session_dict = json.loads(INSTA_SESSION)
        cl.set_settings(session_dict)
        logger.info("تم تحميل جلسة انستغرام بنجاح من Environment Variables.")
    except Exception as e:
        logger.error(f"فشل تحميل الـ Session: {e}")

# تهيئة الجلسة عند بدء التشغيل
init_instagram()

def extract_username(text: str) -> str:
    """استخراج اسم المستخدم من رابط انستغرام أو النص"""
    pattern = r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/([a-zA-Z0-9_\.]+)'
    match = re.search(pattern, text)
    if match:
        return match.group(1).split('/')[0]
    return text.replace("@", "").strip()

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "👋 أهلاً بك في بوت مشاهدة الستوريات بخفاء!\n\n"
        "أرسل لي **رابط حساب انستغرام** أو **اسم المستخدم (Username)** "
        "وسأقوم بجلب الستوريات النشطة فوراً."
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def handle_story_request(message):
    username = extract_username(message.text)
    status_msg = bot.reply_to(message, f"🔍 جاري البحث عن ستوريات @{username}...")

    try:
        # جلب ID المستخدم ثم الستوريات
        user_id = cl.user_id_from_username(username)
        stories = cl.user_stories(user_id)

        if not stories:
            bot.edit_message_text("❌ لا توجد ستوريات نشطة حالياً لهذا الحساب.", 
                                  chat_id=message.chat.id, 
                                  message_id=status_msg.message_id)
            return

        # تجميع الوسائط
        media_group = []
        for story in stories:
            if story.media_type == 1:  # صورة
                media_group.append(types.InputMediaPhoto(story.thumbnail_url))
            elif story.media_type == 2:  # فيديو
                media_group.append(types.InputMediaVideo(story.video_url))

        # تليجرام يقبل 10 وسائط كحد أقصى في الألبوم الواحد
        chunk_size = 10
        for i in range(0, len(media_group), chunk_size):
            chunk = media_group[i:i + chunk_size]
            bot.send_media_group(message.chat.id, chunk)

        # مسح رسالة الانتظار بعد النجاح
        bot.delete_message(message.chat.id, status_msg.message_id)

    except Exception as e:
        logger.error(f"Error fetching stories for {username}: {e}")
        bot.edit_message_text(
            "⚠️ تعذر جلب الستوريات.\n"
            "تأكد أن:\n"
            "1. اليوزر مكتوب بشكل صحيح.\n"
            "2. الحساب عام (Public) وليس خاصاً (Private).",
            chat_id=message.chat.id,
            message_id=status_msg.message_id
        )

if __name__ == "__main__":
    logger.info("البوت يعمل الآن...")
    bot.infinity_polling(skip_pending=True)
  
