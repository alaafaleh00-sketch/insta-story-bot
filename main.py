import os
import re
import json
import html
import logging
from telebot import TeleBot, types
from instagrapi import Client
from instagrapi.exceptions import RateLimitError, ClientError

# 1. إعداد نظام Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 2. قراءة متغيرات البيئة من Railway
BOT_TOKEN = os.environ.get("BOT_TOKEN")
INSTA_SESSION = os.environ.get("INSTA_SESSION")
CHANNEL_1 = os.environ.get("CHANNEL_1", "").strip()
CHANNEL_2 = os.environ.get("CHANNEL_2", "").strip()

if not BOT_TOKEN or not INSTA_SESSION:
    logger.critical("❌ خطأ قاتل: لم يتم العثور على BOT_TOKEN أو INSTA_SESSION في Railway!")
    exit(1)

bot = TeleBot(BOT_TOKEN)
cl = Client()
cl.request_timeout = 20

# 3. تحميل الـ Session بأمان
def load_session():
    try:
        session_dict = json.loads(INSTA_SESSION)
        cl.set_settings(session_dict)
        logger.info("✅ تم تحميل جلسة إنستغرام بنجاح.")
    except Exception as e:
        logger.error(f"❌ فشل قراءة نص الـ Session: {e}")

load_session()

# 4. دالة تنظيف اليوزر المتقدمة (تستخرج اسم الحساب بدقة مهما كان شكل الرابط)
def extract_clean_username(text: str) -> str:
    if not text:
        return ""
    # إزالة بارامترات الرابط مثل ?igsh=...
    clean_text = text.split('?')[0].strip()
    
    # البحث عن النمط داخل رابط إنستغرام
    url_pattern = r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/([a-zA-Z0-9_\.]+)'
    match = re.search(url_pattern, clean_text)
    if match:
        raw_user = match.group(1)
    else:
        raw_user = clean_text

    # تنظيف النص من أي أقواس أو رموز غير صالحة
    cleaned = re.sub(r'[^a-zA-Z0-9_\.]', '', raw_user)
    return cleaned.strip('.')

# 5. دالة فحص الاشتراك بالقنوات
def check_channel_subscription(user_id: int) -> bool:
    channels = [c for c in [CHANNEL_1, CHANNEL_2] if c]
    if not channels:
        return True  # إذا لم تحدد قنوات في Railway يتجاوز الفحص

    for ch in channels:
        try:
            ch_name = ch if ch.startswith("@") or ch.startswith("-100") else f"@{ch}"
            member = bot.get_chat_member(ch_name, user_id)
            if member.status in ['left', 'kicked']:
                return False
        except Exception as e:
            logger.warning(f"تعذر التحقق من الاشتراك بالقناة {ch}: {e}")
            continue
    return True

# 6. أزرار القنوات والتحقق
def build_sub_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    if CHANNEL_1:
        c1 = CHANNEL_1.replace('@', '')
        markup.add(types.InlineKeyboardButton("📢 القناة الأولى", url=f"https://t.me/{c1}"))
    if CHANNEL_2:
        c2 = CHANNEL_2.replace('@', '')
        markup.add(types.InlineKeyboardButton("📢 القناة الثانية", url=f"https://t.me/{c2}"))
    
    markup.add(types.InlineKeyboardButton("🔄 تحقق من الاشتراك", callback_data="verify_sub"))
    return markup

# 7. معالج أمر البدء /start
@bot.message_handler(commands=['start', 'help'])
def start_handler(message):
    user_id = message.from_user.id
    
    if not check_channel_subscription(user_id):
        bot.reply_to(
            message,
            "⚠️ <b>عذراً عزيزي! يجب عليك الاشتراك في قنوات البوت لاستخدامه.</b>\n\nاشترك ثم اضغط زر التحقق أدناه 👇",
            parse_mode="HTML",
            reply_markup=build_sub_keyboard()
        )
        return

    bot.reply_to(
        message,
        "✨ <b>أهلاً بك في بوت كاشف الستوريات الاحترافي!</b>\n\n"
        "أرسل لي <b>رابط الحساب</b> أو <b>اسم المستخدم (Username)</b> "
        "وسأجلب لك كافة الستوريات النشطة فورا وبأعلى جودة ⚡",
        parse_mode="HTML"
    )

# 8. معالج زر التحقق
@bot.callback_query_handler(func=lambda call: call.data == "verify_sub")
def verify_sub_callback(call):
    if check_channel_subscription(call.from_user.id):
        bot.answer_callback_query(call.id, "✅ تم التحقق، يمكنك استخدام البوت الآن!", show_alert=True)
        bot.edit_message_text(
            "✨ <b>تم التحقق بنجاح!</b>\n\nأرسل الآن رابط الحساب أو اسم المستخدم.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="HTML"
        )
    else:
        bot.answer_callback_query(call.id, "❌ لم تشترك بجميع القنوات بعد!", show_alert=True)

# 9. معالج الطلبات الرئيسي
@bot.message_handler(func=lambda message: True)
def process_story_request(message):
    user_id = message.from_user.id

    if not check_channel_subscription(user_id):
        bot.reply_to(
            message,
            "⚠️ <b>يجب الاشتراك بالقنوات أولاً لاستخدام البوت:</b>",
            parse_mode="HTML",
            reply_markup=build_sub_keyboard()
        )
        return

    username = extract_clean_username(message.text)
    if not username:
        bot.reply_to(message, "❌ <b>يرجى إرسال اسم مستخدم أو رابط إنستغرام صحيح.</b>", parse_mode="HTML")
        return

    safe_username = html.escape(username)
    status_msg = bot.reply_to(message, f"⚡ <b>جاري البحث عن ستوريات @{safe_username}...</b>", parse_mode="HTML")

    try:
        # جلب ID الحساب
        try:
            target_id = cl.user_id_from_username(username)
        except Exception:
            user_info = cl.user_info_by_username_v1(username)
            target_id = user_info.pk

        # جلب الستوريات
        stories = cl.user_stories(target_id)

        if not stories:
            bot.edit_message_text(
                f"ℹ️ <b>لا توجد ستوريات نشطة حالياً للحساب @{safe_username}.</b>",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                parse_mode="HTML"
            )
            return

        # إعداد الألبوم
        media_group = []
        for story in stories:
            if story.media_type == 1:
                media_group.append(types.InputMediaPhoto(str(story.thumbnail_url)))
            elif story.media_type == 2:
                media_group.append(types.InputMediaVideo(str(story.video_url)))

        # إرسال الوسائط على دفعات
        chunk_size = 10
        for i in range(0, len(media_group), chunk_size):
            chunk = media_group[i:i + chunk_size]
            bot.send_media_group(message.chat.id, chunk)

        # حذف رسالة الانتظار عند الانتهاء
        bot.delete_message(message.chat.id, status_msg.message_id)

    except RateLimitError:
        logger.error(f"Rate limit hit for {username}")
        bot.edit_message_text(
            "🔥 <b>السيرفر يواجه ضغطاً مؤقتاً من إنستغرام.</b>\nيرجى إعادة المحاولة بعد دقيقة.",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error handling {username}: {e}")
        bot.edit_message_text(
            f"❌ <b>تعذر جلب الستوريات للحساب @{safe_username}.</b>\n\n"
            "تأكد أن الحساب <b>عام (Public)</b> وليس خاصاً.",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            parse_mode="HTML"
        )

if __name__ == "__main__":
    logger.info("🚀 البوت يعـمل الآن بنجاح...")
    bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=30)
    
