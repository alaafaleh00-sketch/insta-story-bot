import os
import re
import json
import time
import logging
from telebot import TeleBot, types
from instagrapi import Client
from instagrapi.exceptions import RateLimitError, ClientError

# 1. إعداد الـ Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 2. جلب متغيرات البيئة من Railway
BOT_TOKEN = os.environ.get("BOT_TOKEN")
INSTA_SESSION = os.environ.get("INSTA_SESSION")
CHANNEL_1 = os.environ.get("CHANNEL_1")  # مثال: @MyChannel1
CHANNEL_2 = os.environ.get("CHANNEL_2")  # مثال: @MyChannel2

if not BOT_TOKEN or not INSTA_SESSION:
    logger.error("❌ خطأ: يرجى التأكد من ضبط BOT_TOKEN و INSTA_SESSION في Railway!")

bot = TeleBot(BOT_TOKEN)
cl = Client()
cl.request_timeout = 12  # زيادة المهلة لتفادي حظر الشبكة

# 3. تحميل الـ Session بأمان
def load_instagram_session():
    try:
        session_dict = json.loads(INSTA_SESSION)
        cl.set_settings(session_dict)
        logger.info("✅ تم تحميل جلسة إنستغرام بنجاح.")
    except Exception as e:
        logger.error(f"❌ فشل تحميل الـ Session: {e}")

load_instagram_session()

# 4. دالة تنظيف اليوزر بدقة عالية (تحذف الأقواس، الرموز، والروابط)
def clean_username(text: str) -> str:
    if not text:
        return ""
    # استخراج اليوزر إذا كان رابطاً
    url_match = re.search(r'instagram\.com/([a-zA-Z0-9_\.]+)', text)
    if url_match:
        raw_user = url_match.group(1)
    else:
        raw_user = text
    
    # حذف أي رموز أو أقواس زائدة والإبقاء فقط على الحروف والأرقام والنقاط
    cleaned = re.sub(r'[^a-zA-Z0-9_\.]', '', raw_user)
    return cleaned.strip('.')

# 5. التحقق من اشتراك المستخدم في القنوات
def is_user_subscribed(user_id: int) -> bool:
    channels = [CHANNEL_1, CHANNEL_2]
    for ch in channels:
        if not ch:
            continue
        try:
            ch_clean = ch.strip()
            if not ch_clean.startswith("@") and not ch_clean.startswith("-100"):
                ch_clean = f"@{ch_clean}"
            
            member = bot.get_chat_member(ch_clean, user_id)
            if member.status in ['left', 'kicked']:
                return False
        except Exception as e:
            logger.warning(f"تعذر التحقق من القناة {ch}: {e}")
            # إذا لم يكن البوت مدمناً بالقناة يتجاوز الفحص لكي لا يتوقف البوت
            continue
    return True

# 6. لوحة أزرار الاشتراك الإجباري
def get_subscription_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    if CHANNEL_1:
        ch1_link = f"https://t.me/{CHANNEL_1.replace('@', '')}"
        markup.add(types.InlineKeyboardButton("📢 القناة الأولى", url=ch1_link))
    if CHANNEL_2:
        ch2_link = f"https://t.me/{CHANNEL_2.replace('@', '')}"
        markup.add(types.InlineKeyboardButton("📢 القناة الثانية", url=ch2_link))
    
    markup.add(types.InlineKeyboardButton("🔄 تحقق من الاشتراك", callback_data="check_sub"))
    return markup

# 7. معالج أمر /start
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    user_id = message.from_user.id
    
    if not is_user_subscribed(user_id):
        sub_text = (
            "⚠️ **عذراً عزيزي! يجب عليك الاشتراك في قنوات البوت أولاً لاستخدامه.**\n\n"
            "اشترك في القنوات أدناه ثم اضغط على زر **(تحقق من الاشتراك)** 👇"
        )
        bot.reply_to(message, sub_text, parse_mode="Markdown", reply_markup=get_subscription_keyboard())
        return

    welcome_text = (
        "✨ **أهلاً بك في بوت كاشف الستوريات الاحترافي!**\n\n"
        "🔍 **كيفية الاستخدام:**\n"
        "فقط أرسل لي **رابط الحساب** أو **اسم المستخدم (Username)** "
        "وسأقوم بجلب كافة الستوريات النشطة بخفاء تام وبأعلى جودة ⚡"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

# 8. معالج زر التحقق من الاشتراك
@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def callback_check_sub(call):
    if is_user_subscribed(call.from_user.id):
        bot.answer_callback_query(call.id, "✅ تم التحقق بنجاح! يمكنك استخدام البوت الآن.", show_alert=True)
        bot.edit_message_text(
            "✨ **تم التحقق من اشتراكك بنجاح!**\n\nأرسل الآن رابط الحساب أو اسم المستخدم لجلب الستوريات.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="Markdown"
        )
    else:
        bot.answer_callback_query(call.id, "❌ لم تشترك في جميع القنوات بعد!", show_alert=True)

# 9. معالج جلب الستوريات الرئيسي
@bot.message_handler(func=lambda message: True)
def handle_story_request(message):
    user_id = message.from_user.id

    # فحص الاشتراك قبل معالجة الطلب
    if not is_user_subscribed(user_id):
        bot.reply_to(
            message,
            "⚠️ **يجب عليك الاشتراك في القنوات لاستخدام البوت:**",
            parse_mode="Markdown",
            reply_markup=get_subscription_keyboard()
        )
        return

    username = clean_username(message.text)
    
    if not username:
        bot.reply_to(message, "❌ **يرجى إرسال اسم مستخدم أو رابط صحيح.**", parse_mode="Markdown")
        return

    status_msg = bot.reply_to(message, f"⚡ **جاري البحث عن ستوريات @{username}...**", parse_mode="Markdown")

    try:
        # جلب ID الحساب بطرق بديلة لتفادي حظر 429
        try:
            target_user_id = cl.user_id_from_username(username)
        except Exception:
            # طريقة احتياطية إذا فشلت الأولى
            user_info = cl.user_info_by_username_v1(username)
            target_user_id = user_info.pk

        # جلب الستوريات النشطة
        stories = cl.user_stories(target_user_id)

        if not stories:
            bot.edit_message_text(
                f"ℹ️ **لا توجد ستوريات نشطة حالياً للحساب @{username}.**",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                parse_mode="Markdown"
            )
            return

        # تجميع ألبوم الوسائط
        media_group = []
        for story in stories:
            if story.media_type == 1:  # صورة
                media_group.append(types.InputMediaPhoto(str(story.thumbnail_url)))
            elif story.media_type == 2:  # فيديو
                media_group.append(types.InputMediaVideo(str(story.video_url)))

        # تقسيم الإرسال لألبومات (حد أقصى 10 وسائط في الرسالة)
        chunk_size = 10
        for i in range(0, len(media_group), chunk_size):
            chunk = media_group[i:i + chunk_size]
            bot.send_media_group(message.chat.id, chunk)

        # حذف رسالة الانتظار عند النجاح
        bot.delete_message(message.chat.id, status_msg.message_id)

    except RateLimitError:
        logger.error(f"Rate limit error for {username}")
        bot.edit_message_text(
            "🔥 **السيرفر يواجه ضغطاً مؤقتاً من إنستغرام.**\nيرجى المحاولة بعد دقيقة واحدة.",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error fetching stories for {username}: {e}")
        bot.edit_message_text(
            f"❌ **تعذر جلب الستوريات للحساب @{username}**\n\n"
            "تأكد من:\n"
            "1. كتابة اليوزر بشكل صحيح بدون أخطاء.\n"
            "2. أن الحساب **عام (Public)** وليس خاصاً (Private).",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            parse_mode="Markdown"
        )

if __name__ == "__main__":
    logger.info("🚀 البوت يعمل الآن بنجاح مع نظام الاشتراك الإجباري...")
    bot.infinity_polling(skip_pending=True)
    
