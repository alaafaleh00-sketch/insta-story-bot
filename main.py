import os
import re
import json
import html
import logging
from telebot import TeleBot, types
from instagrapi import Client

# 1. إعداد الـ Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 2. جلب متغيرات البيئة
BOT_TOKEN = os.environ.get("BOT_TOKEN")
INSTA_SESSION = os.environ.get("INSTA_SESSION")
CHANNEL_1 = os.environ.get("CHANNEL_1", "").strip()
CHANNEL_2 = os.environ.get("CHANNEL_2", "").strip()

if not BOT_TOKEN or not INSTA_SESSION:
    logger.critical("❌ خطأ: لم يتم العثور على BOT_TOKEN أو INSTA_SESSION!")
    exit(1)

bot = TeleBot(BOT_TOKEN)
cl = Client()
cl.request_timeout = 20

# 3. إعداد الجلسة والكوكيز بدون أخطاء
def setup_instagram_session():
    try:
        session_dict = json.loads(INSTA_SESSION)
        cookies = session_dict.get("cookies", {})
        session_id = cookies.get("sessionid", "")

        if session_id:
            user_id_match = re.match(r'^(\d+)', session_id)
            ds_user_id = user_id_match.group(1) if user_id_match else ""
            session_dict["cookies"] = {
                "sessionid": session_id,
                "ds_user_id": ds_user_id,
                "csrftoken": "missing"
            }
            
        cl.set_settings(session_dict)
        logger.info("✅ تم إعداد جلسة إنستغرام بنجاح.")
    except Exception as e:
        logger.error(f"❌ خطأ في إعداد الجلسة: {e}")

setup_instagram_session()

# 4. دالة استخراج وتنظيف اسم المستخدم
def extract_clean_username(text: str) -> str:
    if not text:
        return ""
    clean_text = text.split('?')[0].strip()
    url_pattern = r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/([a-zA-Z0-9_\.]+)'
    match = re.search(url_pattern, clean_text)
    raw_user = match.group(1) if match else clean_text
    cleaned = re.sub(r'[^a-zA-Z0-9_\.]', '', raw_user)
    return cleaned.strip('.')

# 5. فحص اشتراك القنوات
def check_channel_subscription(user_id: int) -> bool:
    channels = [c for c in [CHANNEL_1, CHANNEL_2] if c]
    if not channels:
        return True

    for ch in channels:
        try:
            ch_name = ch if ch.startswith("@") or ch.startswith("-100") else f"@{ch}"
            member = bot.get_chat_member(ch_name, user_id)
            if member.status in ['left', 'kicked']:
                return False
        except Exception as e:
            logger.warning(f"تعذر فحص القناة {ch}: {e}")
            continue
    return True

# 6. لوحة أزرار القنوات
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

# 7. معالج أمر /start
@bot.message_handler(commands=['start', 'help'])
def start_handler(message):
    user_id = message.from_user.id
    if not check_channel_subscription(user_id):
        bot.reply_to(
            message,
            "⚠️ <b>يجب عليك الاشتراك في قنوات البوت أولاً لاستخدامه.</b>",
            parse_mode="HTML",
            reply_markup=build_sub_keyboard()
        )
        return

    bot.reply_to(
        message,
        "✨ <b>أهلاً بك في بوت كاشف الستوريات الاحترافي!</b>\n\n"
        "أرسل لي <b>رابط الحساب</b> أو <b>اسم المستخدم (Username)</b> "
        "وسأجلب لك كافة الستوريات النشطة فوراً ⚡",
        parse_mode="HTML"
    )

# 8. معالج زر التحقق
@bot.callback_query_handler(func=lambda call: call.data == "verify_sub")
def verify_sub_callback(call):
    if check_channel_subscription(call.from_user.id):
        bot.answer_callback_query(call.id, "✅ تم التحقق بنجاح!", show_alert=True)
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
        bot.reply_to(message, "❌ <b>يرجى إرسال اسم مستخدم أو رابط صحيح.</b>", parse_mode="HTML")
        return

    safe_username = html.escape(username)
    status_msg = bot.reply_to(message, f"⚡ <b>جاري البحث عن ستوريات @{safe_username}...</b>", parse_mode="HTML")

    try:
        # جلب ID الحساب ثم الستوريات
        target_id = cl.user_id_from_username(username)
        stories = cl.user_stories(target_id)

        if not stories:
            bot.edit_message_text(
                f"ℹ️ <b>لا توجد ستوريات نشطة حالياً للحساب @{safe_username}.</b>",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                parse_mode="HTML"
            )
            return

        media_group = []
        for story in stories:
            if story.media_type == 1:
                media_group.append(types.InputMediaPhoto(str(story.thumbnail_url)))
            elif story.media_type == 2:
                media_group.append(types.InputMediaVideo(str(story.video_url)))

        chunk_size = 10
        for i in range(0, len(media_group), chunk_size):
            chunk = media_group[i:i + chunk_size]
            bot.send_media_group(message.chat.id, chunk)

        bot.delete_message(message.chat.id, status_msg.message_id)

    except Exception as e:
        logger.error(f"Error handling {username}: {e}")
        err_str = str(e).lower()
        if "login" in err_str or "403" in err_str or "429" in err_str:
            msg = "⚠️ <b>السيرفر يواجه تقييداً مؤقتاً من إنستغرام، يرجى إعادة المحاولة بعد قليل.</b>"
        else:
            msg = f"❌ <b>تعذر جلب الستوريات للحساب @{safe_username}.</b>\n\nتأكد أن الحساب <b>عام (Public)</b> وليس خاصاً."

        bot.edit_message_text(
            msg,
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            parse_mode="HTML"
        )

if __name__ == "__main__":
    logger.info("🚀 البوت يعمل الآن بنجاح واستقرار تام...")
    bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=30)
    
