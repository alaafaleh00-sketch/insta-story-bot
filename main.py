import os
import re
import html
import logging
import requests
from telebot import TeleBot, types

# 1. إعداد الـ Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 2. قراءة متغيرات البيئة من Railway
BOT_TOKEN = os.environ.get("BOT_TOKEN")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "de17445a54msh4c64319ee7db803p13eaBejsn2e402b20a043").strip()
CHANNEL_1 = os.environ.get("CHANNEL_1", "").strip()
CHANNEL_2 = os.environ.get("CHANNEL_2", "").strip()

RAPIDAPI_HOST = "instagram-public-bulk-scraper.p.rapidapi.com"

if not BOT_TOKEN or not RAPIDAPI_KEY:
    logger.critical("❌ خطأ: لم يتم العثور على BOT_TOKEN أو RAPIDAPI_KEY في متغيرات البيئة!")
    exit(1)

bot = TeleBot(BOT_TOKEN)

# 3. دالة تنظيف واستخراج اسم المستخدم
def extract_clean_username(text: str) -> str:
    if not text:
        return ""
    clean_text = text.split('?')[0].strip()
    match = re.search(r'instagram\.com/([a-zA-Z0-9_\.]+)', clean_text)
    raw_user = match.group(1) if match else clean_text
    return re.sub(r'[^a-zA-Z0-9_\.]', '', raw_user).strip('.')

# 4. دالة فحص الاشتراك بالقنوات
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

# 5. لوحة أزرار الاشتراك الإجباري
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

# 6. معالج أمر /start
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

# 7. معالج زر التحقق
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

# 8. معالج طلب الستوريات الرئيسي عبر RapidAPI
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
    status_msg = bot.reply_to(message, f"⚡ <b>جاري جلب ستوريات @{safe_username}...</b>", parse_mode="HTML")

    url = f"https://{RAPIDAPI_HOST}/v1/download_story"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }
    params = {"username": username}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
        res_data = response.json()

        stories = []
        if isinstance(res_data, list):
            stories = res_data
        elif isinstance(res_data, dict):
            stories = res_data.get("data") or res_data.get("stories") or res_data.get("items") or [res_data]

        if not stories or (isinstance(stories, list) and len(stories) == 0):
            bot.edit_message_text(
                f"ℹ️ <b>لا توجد ستوريات نشطة حالياً للحساب @{safe_username}.</b>",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                parse_mode="HTML"
            )
            return

        media_group = []
        for item in stories:
            if isinstance(item, dict):
                video_url = item.get("video_url") or item.get("download_url") or (item.get("video_versions", [{}])[0].get("url") if item.get("video_versions") else None)
                image_url = item.get("image_url") or item.get("display_url") or item.get("thumbnail_url")

                if video_url and ("mp4" in str(video_url).lower() or item.get("is_video")):
                    media_group.append(types.InputMediaVideo(video_url))
                elif image_url:
                    media_group.append(types.InputMediaPhoto(image_url))

        if not media_group:
            bot.edit_message_text(
                f"ℹ️ <b>تعذر استخراج روابط الستوري للحساب @{safe_username}.</b>",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                parse_mode="HTML"
            )
            return

        chunk_size = 10
        for i in range(0, len(media_group), chunk_size):
            chunk = media_group[i:i + chunk_size]
            bot.send_media_group(message.chat.id, chunk)

        bot.delete_message(message.chat.id, status_msg.message_id)

    except Exception as e:
        logger.error(f"RapidAPI Error for {username}: {e}")
        bot.edit_message_text(
            f"❌ <b>تعذر جلب الستوريات للحساب @{safe_username}.</b>\n\nتأكد أن الحساب <b>عام (Public)</b> وليس خاصاً.",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            parse_mode="HTML"
        )

if __name__ == "__main__":
    logger.info("🚀 البوت يعمل الآن بنجاح مع RapidAPI...")
    bot.infinity_polling(skip_pending=True)
    
