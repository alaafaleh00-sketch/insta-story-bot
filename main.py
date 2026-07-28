import os
import re
import json
import html
import logging
from telebot import TeleBot, types
from instagrapi import Client
from instagrapi.exceptions import RateLimitError

# 1. إعداد الـ Logging لمتابعة تشغيل البوت في Railway
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 2. جلب متغيرات البيئة
BOT_TOKEN = os.environ.get("BOT_TOKEN")
INSTA_SESSION = os.environ.get("INSTA_SESSION")
CHANNEL_1 = os.environ.get("CHANNEL_1")
CHANNEL_2 = os.environ.get("CHANNEL_2")

if not BOT_TOKEN or not INSTA_SESSION:
    logger.error("❌ خطأ: لم يتم العثور على BOT_TOKEN أو INSTA_SESSION في متغيرات البيئة!")

bot = TeleBot(BOT_TOKEN)
cl = Client()
cl.request_timeout = 15

# 3. تحميل الـ Session بأمان
def load_instagram_session():
    try:
        session_dict = json.loads(INSTA_SESSION)
        cl.set_settings(session_dict)
        logger.info("✅ تم تحميل جلسة إنستغرام بنجاح.")
    except Exception as e:
        logger.error(f"❌ فشل تحميل الـ Session: {e}")

load_instagram_session()

# 4. دالة تنظيف اليوزر بدقة وتفادي الروابط والمعرفات المعطوبة
def clean_username(text: str) -> str:
    if not text:
        return ""
    # إزالة بارامترات الرابط بعد علامة ?
    clean_text = text.split('?')[0]
    
    # استخراج اليوزر إذا كان رابطاً
    url_match = re.search(r'instagram\.com/([a-zA-Z0-9_\.]+)', clean_text)
    if url_match:
        raw_user = url_match.group(1)
    else:
        raw_user = clean_text
    
    # حذف الرموز والأقواس الزائدة
    cleaned = re.sub(r'[^a-zA-Z0-9_\.]', '', raw_user)
    return cleaned.strip('.')

# 5. الفحص عن الاشتراك بالقنوات
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
            "⚠️ <b>عذراً عزيزي! يجب عليك الاشتراك في قنوات البوت أولاً لاستخدامه.</b>\n\n"
            "اشترك في القنوات أدناه ثم اضغط على زر <b>(تحقق من الاشتراك)</b> 👇"
        )
        bot.reply_to(message, sub_text, parse_mode="HTML", reply_markup=get_subscription_keyboard())
        return

    welcome_text = (
        "✨ <b>أهلاً بك في بوت كاشف الستوريات الاحترافي!</b>\n\n"
        "🔍 <b>كيفية الاستخدام:</b>\n"
        "أرسل لي <b>رابط الحساب</b> أو <b>اسم المستخدم (Username)</b> "
        "وسأقوم بجلب كافة الستوريات النشطة بخفاء تام وبأعلى جودة ⚡"
    )
    bot.reply_to(message, welcome_text, parse_mode="HTML")

# 8. معالج زر التحقق من الاشتراك
@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def callback_check_sub(call):
    if is_user_subscribed(call.from_user.id):
        bot.answer_callback_query(call.id, "✅ تم التحقق بنجاح! يمكنك استخدام البوت الآن.", show_alert=True)
        bot.edit_message_text(
            "✨ <b>تم التحقق من اشتراكك بنجاح!</b>\n\nأرسل الآن رابط الحساب أو اسم المستخدم لجلب الستوريات.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="HTML"
        )
    else:
        bot.answer_callback_query(call.id, "❌ لم تشترك في جميع القنوات بعد!", show_alert=True)

# 9. معالج جلب الستوريات الرئيسي
@bot.message_handler(func=lambda message: True)
def handle_story_request(message):
    user_id = message.from_user.id

    if not is_user_subscribed(user_id):
        bot.reply_to(
            message,
            "⚠️ <b>يجب عليك الاشتراك في القنوات لاستخدام البوت:</b>",
            parse_mode="HTML",
            reply_markup=get_subscription_keyboard()
        )
        return

    username = clean_username(message.text)
    
    if not username:
        bot.reply_to(message, "❌ <b>يرجى إرسال اسم مستخدم أو رابط صحيح.</b>", parse_mode="HTML")
        return

    # التشفير الآمن لليوزر لتفادي خطأ الـ Entities
    safe_username = html.escape(username)
    status_msg = bot.reply_to(message, f"⚡ <b>جاري البحث عن ستوريات @{safe_username}...</b>", parse_mode="HTML")

    try:
        # جلب ID الحساب
        try:
            target_user_id = cl.user_id_from_username(username)
        except Exception:
            user_info = cl.user_info_by_username_v1(username)
            target_user_id = user_info.pk

        # جلب الستوريات النشطة
        stories = cl.user_stories(target_user_id)

        if not stories:
            bot.edit_message_text(
                f"ℹ️ <b>لا توجد ستوريات نشطة حالياً للحساب @{safe_username}.</b>",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                parse_mode="HTML"
            )
            return

        # تجميع ألبوم الوسائط
        media_group = []
        for story in stories:
            if story.media_type == 1:
                media_group.append(types.InputMediaPhoto(str(story.thumbnail_url)))
            elif story.media_type == 2:
                media_group.append(types.InputMediaVideo(str(story.video_url)))

        # إرسال الألبومات (10 وسائط في الرسالة كحد أقصى)
        chunk_size = 10
        for i in range(0, len(media_group), chunk_size):
            chunk = media_group[i:i + chunk_size]
            bot.send_media_group(message.chat.id, chunk)

        # حذف رسالة الانتظار بعد إكمال الإرسال
        bot.delete_message(message.chat.id, status_msg.message_id)

    except RateLimitError:
        logger.error(f"Rate limit error for {username}")
        bot.edit_message_text(
            "🔥 <b>السيرفر يواجه ضغطاً مؤقتاً من إنستغرام.</b>\nيرجى المحاولة بعد دقيقة واحدة.",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Error fetching stories for {username}: {e}")
        bot.edit_message_text(
            f"❌ <b>تعذر جلب الستوريات للحساب @{safe_username}</b>\n\n"
            "تأكد من:\n"
            "1. كتابة اليوزر بشكل صحيح بدون أخطاء.\n"
            "2. أن الحساب <b>عام (Public)</b> وليس خاصاً (Private).",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            parse_mode="HTML"
        )

if __name__ == "__main__":
    logger.info("🚀 البوت يعمل الآن بنظام HTML الآمن...")
    bot.infinity_polling(skip_pending=True)
    
