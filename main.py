import telebot
from telebot import types
import json
import datetime
import google.generativeai as genai
import time
from keep_alive import keep_alive  # اضافه شده برای Render

# ---------- تنظیمات ----------
TELEGRAM_TOKEN = "7747661039:AAGYPRPF_DX0JvszIQKZAjgAvSzS_Gqm0fg"
GEMINI_API_KEY = "AIzaSyDbTQIO0QgTOpnfVQHuFn9Xd_ZPsaK34Pg"
USERS_FILE = "users.json"

# ---------- تنظیمات Rate Limit ----------
MAX_MESSAGES_PER_MINUTE = 15
RATE_LIMIT_WINDOW = 60
global_message_count = 0
rate_limit_start_time = None

# ---------- اتصال ----------
bot = telebot.TeleBot(TELEGRAM_TOKEN)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("models/gemini-2.0-flash")

# ---------- متغیرهای حافظه ----------
user_contexts = {}         # حافظه مکالمات کاربران
chat_id_to_code = {}       # نگاشت chat_id به کد اشتراک
pending_starts = {}        # درخواست‌های start در حال انتظار
active_sessions = {}       # نشست‌های فعال {code: chat_id}
session_timestamps = {}    # زمان آخرین فعالیت هر کاربر

# ---------- تابع بررسی Rate Limit ----------
def check_rate_limit():
    global global_message_count, rate_limit_start_time
    
    now = time.time()
    
    if rate_limit_start_time is None or (now - rate_limit_start_time) > RATE_LIMIT_WINDOW:
        global_message_count = 1
        rate_limit_start_time = now
        return True
    
    if global_message_count >= MAX_MESSAGES_PER_MINUTE:
        return False
    
    global_message_count += 1
    return True

# ---------- تابع بررسی نشست کاربر ----------
def check_user_session(code, chat_id):
    """بررسی می‌کند آیا کاربر از دستگاه دیگری وارد شده است"""
    if code in active_sessions:
        if active_sessions[code] != chat_id:
            # بررسی زمان آخرین فعالیت
            last_active = session_timestamps.get(code, 0)
            if time.time() - last_active > 300:  # 5 دقیقه عدم فعالیت
                # حذف نشست قدیمی
                old_chat_id = active_sessions[code]
                if old_chat_id in chat_id_to_code:
                    chat_id_to_code.pop(old_chat_id)
                if old_chat_id in user_contexts:
                    user_contexts.pop(old_chat_id)
                active_sessions.pop(code)
                session_timestamps.pop(code, None)
                return True
            return False
    return True

# ---------- ابزارها ----------
def load_users():
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_users(users):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=2)

def is_active(user):
    today = datetime.date.today()
    expire = datetime.datetime.strptime(user['expire'], '%Y-%m-%d').date()
    return today <= expire

# ---------- لیست کاربران آنلاین ----------
def list_online_users(chat_id):
    users = load_users()
    online_users = []
    
    for code, user_data in users.items():
        if code in active_sessions:
            user_info = (
                f"👤 {user_data.get('name', 'نامشخص')}\n"
                f"📅 انقضا: {user_data['expire']}\n"
                "──────────────────"
            )
            online_users.append(user_info)
    
    if online_users:
        message_text = (
            "🟢 کاربران آنلاین:\n\n" +
            "\n".join(online_users) + 
            f"\n\nتعداد کل: {len(online_users)} کاربر"
        )
    else:
        message_text = "⚠️ هیچ کاربر آنلاینی وجود ندارد."
    
    bot.send_message(chat_id, message_text)
    show_admin_menu(chat_id)

# ---------- هندلرهای مسدود کردن مدیا ----------
@bot.message_handler(content_types=['photo', 'video', 'voice', 'audio', 'document', 'sticker'])
def handle_blocked_media(message):
    chat_id = message.chat.id
    bot.reply_to(message, "⚠️ این ربات فقط از پیام‌های متنی پشتیبانی می‌کند.")
    if chat_id in user_contexts:
        ask_user_topic(chat_id, load_users().get(chat_id_to_code.get(chat_id)))

# ---------- شروع ----------
def welcome(message):
    chat_id = message.chat.id
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("ورود با کد اشتراک")
    bot.send_message(
        chat_id,
        "🤖 به ربات هوشمند تیوان خوش آمدید!\n"
        "لطفاً برای ادامه، کد اشتراک خود را وارد کنید:",
        reply_markup=markup
    )
    bot.register_next_step_handler_by_chat_id(chat_id, check_code)

@bot.message_handler(commands=['start'])
def handle_start(message):
    chat_id = message.chat.id
    pending_starts[chat_id] = message
    bot.clear_step_handler_by_chat_id(chat_id)
    time.sleep(0.5)
    
    if pending_starts.get(chat_id) == message:
        welcome(message)
        pending_starts.pop(chat_id, None)

# ---------- بررسی کد اشتراک ----------
def check_code(message):
    chat_id = message.chat.id
    bot.clear_step_handler_by_chat_id(chat_id)
    
    if message.content_type != 'text':
        handle_blocked_media(message)
        return welcome(message)
        
    code = message.text.strip()
    users = load_users()
    user = users.get(code)

    if not user:
        bot.send_message(chat_id, "❌ کد اشتراک نامعتبر است.")
        return welcome(message)

    if not is_active(user):
        bot.send_message(chat_id, "❌ اشتراک شما منقضی شده است.")
        return welcome(message)

    # بررسی ورود همزمان
    if not check_user_session(code, chat_id):
        bot.send_message(
            chat_id,
            "⚠️ این حساب کاربری در حال حاضر از دستگاه دیگری استفاده می‌شود.\n\n"
            "اگر شما از دستگاه دیگری وارد شده‌اید، لطفاً:\n"
            "1. ابتدا از آن دستگاه خارج شوید (/خروج)\n"
            "2. یا 5 دقیقه صبر کنید تا اتصال قبلی به صورت خودکار قطع شود"
        )
        return welcome(message)

    # ثبت نشست کاربر
    active_sessions[code] = chat_id
    session_timestamps[code] = time.time()
    chat_id_to_code[chat_id] = code

    if user['role'] == 'admin':
        show_admin_menu(chat_id)
    else:
        info = (
            f"👤 مشخصات شما:\n"
            f"نام: {user.get('name', 'نامشخص')}\n"
            f"کد ملی: {user.get('national_id', 'نامشخص')}\n"
            f"شماره تماس: {user.get('phone', 'نامشخص')}\n"
            f"تاریخ انقضا: {user['expire']}\n"
        )
        bot.send_message(chat_id, info)
        ask_user_topic(chat_id, user)

# ---------- پرسیدن موضوع مکاتبه ----------
def ask_user_topic(chat_id, user):
    # به روزرسانی زمان آخرین فعالیت
    code = chat_id_to_code.get(chat_id)
    if code:
        session_timestamps[code] = time.time()
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("پایان مکالمه", "خروج از حساب کاربری")
    bot.send_message(chat_id, "📝 لطفاً موضوع مکاتبه خود را وارد کنید:", reply_markup=markup)
    bot.register_next_step_handler_by_chat_id(chat_id, handle_user_topic)

def handle_user_topic(message):
    chat_id = message.chat.id
    code = chat_id_to_code.get(chat_id)
    
    # بررسی زمان آخرین فعالیت
    if code and code in session_timestamps:
        session_timestamps[code] = time.time()
    
    if message.content_type != 'text':
        handle_blocked_media(message)
        return ask_user_topic(chat_id, load_users().get(code))
        
    text = message.text.strip()

    if text in ["پایان مکالمه", "خروج از حساب کاربری"]:
        if text == "پایان مکالمه":
            user_contexts.pop(chat_id, None)
            users = load_users()
            user = users.get(code)
            if user:
                info = (
                    f"👤 مشخصات شما:\n"
                    f"نام: {user.get('name', 'نامشخص')}\n"
                    f"کد ملی: {user.get('national_id', 'نامشخص')}\n"
                    f"شماره تماس: {user.get('phone', 'نامشخص')}\n"
                    f"تاریخ انقضا: {user['expire']}\n"
                )
                bot.send_message(chat_id, info)
                ask_user_topic(chat_id, user)
            else:
                welcome(message)
        else:  # خروج از حساب
            if code in active_sessions:
                active_sessions.pop(code)
            if code in session_timestamps:
                session_timestamps.pop(code)
            chat_id_to_code.pop(chat_id, None)
            user_contexts.pop(chat_id, None)
            bot.send_message(chat_id, "✅ از حساب کاربری خود خارج شدید.")
            welcome(message)
        return

    if chat_id not in user_contexts:
        user_contexts[chat_id] = []

    user_contexts[chat_id].append({"role": "user", "content": f"موضوع مکاتبه: {text}"})
    send_gemini_continued(message)

# ---------- پاسخ پیوسته از Gemini ----------
def send_gemini_continued(message):
    chat_id = message.chat.id
    code = chat_id_to_code.get(chat_id)
    
    # بررسی زمان آخرین فعالیت
    if code and code in session_timestamps:
        session_timestamps[code] = time.time()
    
    if message.content_type != 'text':
        handle_blocked_media(message)
        return
    
    # بررسی Rate Limit
    if not check_rate_limit():
        remaining_time = int(RATE_LIMIT_WINDOW - (time.time() - rate_limit_start_time))
        bot.send_message(
            chat_id,
            f"⏳ **محدودیت ارسال پیام برای همه کاربران**!\n"
            f"به دلیل ترافیک بالا، می‌توانید بعد از {remaining_time} ثانیه دیگر پیام ارسال کنید.\n"
            f"محدودیت سیستم: {MAX_MESSAGES_PER_MINUTE} پیام در دقیقه برای همه کاربران"
        )
        return
    
    prompt = message.text.strip()

    # بررسی سوالات ممنوعه درباره هوش مصنوعی
    forbidden_keywords = [
        "تو کی هستی", "هویت تو", "چه کسی تو را ساخته",
        "مدل تو چیست", "نسخه تو", "مشخصات فنی","قدرت می گیری",
        "چه کسی تو را توسعه داده", "شرکت سازنده",
        "api key", "توکن", "gemini", "گوگل", "google"
    ]
    
    if any(keyword in prompt.lower() for keyword in forbidden_keywords):
        bot.send_message(
            chat_id,
            "من یک مدل هوش مصنوعی آموزش‌دیده توسط تیوان هستم که برای مکاتبات اداری و رسمی طراحی شده‌ام. "
            "لطفاً سوالات خود را در این زمینه مطرح کنید."
        )
        return ask_user_topic(chat_id, load_users().get(code))

    if chat_id not in user_contexts:
        user_contexts[chat_id] = []

    user_contexts[chat_id].append({"role": "user", "content": prompt})

    # دریافت سبک نوشتاری کاربر از پروفایل
    users = load_users()
    user = users.get(code, {})
    writing_style = user.get("writing_style")

    # ساخت prompt با دستورالعمل مخفی
    system_prompt = ( 
    "لازم به توضیحات نیست و فقط اصل مکاتبه نمایش داده شود"
        f"ویژگی‌های سبک نوشتاری مورد نظر: {writing_style}\n\n"
    )

    full_prompt = system_prompt + "\n\n"
    for entry in user_contexts[chat_id]:
        role = entry["role"]
        content = entry["content"]
        if role == "user":
            full_prompt += f"سوال کاربر: {content}\n"
        else:
            full_prompt += f"پاسخ قبلی: {content}\n"

    try:
        response = model.generate_content(full_prompt)
        answer = response.text.strip()
        user_contexts[chat_id].append({"role": "assistant", "content": answer})
        bot.send_message(chat_id, answer)
    except Exception as e:
        bot.send_message(chat_id, f"❌ خطا: {e}")

    ask_user_topic(chat_id, user)

# ---------- منوی ادمین ----------
def show_admin_menu(chat_id):
    bot.clear_step_handler_by_chat_id(chat_id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("افزودن مشترک", "وضعیت مشترکین")
    markup.add("غیرفعال‌سازی مشترک", "وضعیت توکن")
    markup.add("لیست کاربران آنلاین")
    markup.add("خروج از حساب کاربری")
    bot.send_message(chat_id, "🔧 لطفاً یک گزینه را انتخاب کنید:", reply_markup=markup)
    bot.register_next_step_handler_by_chat_id(chat_id, handle_admin_choice)

def handle_admin_choice(message):
    chat_id = message.chat.id
    code = chat_id_to_code.get(chat_id)
    
    # بررسی زمان آخرین فعالیت
    if code and code in session_timestamps:
        session_timestamps[code] = time.time()
    
    bot.clear_step_handler_by_chat_id(chat_id)
    
    if message.content_type != 'text':
        handle_blocked_media(message)
        return show_admin_menu(chat_id)

    if message.text == "افزودن مشترک":
        bot.send_message(chat_id, "لطفاً اطلاعات کاربر را با فرمت زیر وارد کنید:\n"
                          "کد, نقش(user/admin), تاریخ انقضا(YYYY-MM-DD), نام کامل, کد ملی, شماره تماس, سبک نوشتاری\n\n"
                          "مثال:\n"
                          "12345,user,2024-12-31,محمد احمدی,0012345678,0912345678,سبک رسمی و مختصر با لحن محترمانه")
        bot.register_next_step_handler(message, add_user)
    elif message.text == "وضعیت مشترکین":
        users = load_users()
        text = "\n".join([
            f"{u} - {v['name']} ({v['role']}) - {'فعال' if is_active(v) else 'منقضی'} تا {v['expire']}"
            f" - {'آنلاین' if u in active_sessions else 'آفلاین'}"
            for u, v in users.items()
        ]) or "⚠️ هیچ کاربری ثبت نشده است."
        bot.send_message(chat_id, text)
        show_admin_menu(chat_id)
    elif message.text == "غیرفعال‌سازی مشترک":
        bot.send_message(chat_id, "کد کاربر:")
        bot.register_next_step_handler(message, deactivate_user)
    elif message.text == "وضعیت توکن":
        bot.send_message(chat_id, f"✅ توکن فعال است.\n📅 تاریخ امروز: {datetime.date.today()}")
        show_admin_menu(chat_id)
    elif message.text == "لیست کاربران آنلاین":
        list_online_users(chat_id)
    elif message.text == "خروج از حساب کاربری":
        if code in active_sessions:
            active_sessions.pop(code)
        if code in session_timestamps:
            session_timestamps.pop(code)
        chat_id_to_code.pop(chat_id, None)
        user_contexts.pop(chat_id, None)
        bot.send_message(chat_id, "✅ از حساب کاربری خود خارج شدید.")
        welcome(message)
    else:
        bot.send_message(chat_id, "❌ گزینه معتبر نیست.")
        show_admin_menu(chat_id)

# ---------- افزودن مشترک ----------
def add_user(message):
    chat_id = message.chat.id
    bot.clear_step_handler_by_chat_id(chat_id)
    
    if message.content_type != 'text':
        handle_blocked_media(message)
        return show_admin_menu(chat_id)
        
    try:
        code, role, expire, name, national_id, phone, writing_style = [x.strip() for x in message.text.split(',')]
        users = load_users()
        users[code] = {
            "role": role,
            "expire": expire,
            "name": name,
            "national_id": national_id,
            "phone": phone,
            "writing_style": writing_style
        }
        save_users(users)
        bot.send_message(chat_id, "✅ کاربر با موفقیت اضافه شد.")
    except Exception as e:
        bot.send_message(chat_id, f"❌ خطا در فرمت: {e}")
    show_admin_menu(chat_id)

# ---------- غیرفعال‌سازی مشترک ----------
def deactivate_user(message):
    chat_id = message.chat.id
    bot.clear_step_handler_by_chat_id(chat_id)
    
    if message.content_type != 'text':
        handle_blocked_media(message)
        return show_admin_menu(chat_id)
        
    code = message.text.strip()
    users = load_users()
    if code in users:
        users[code]['expire'] = '2000-01-01'
        save_users(users)
        # اگر کاربر آنلاین است، او را خارج کن
        if code in active_sessions:
            old_chat_id = active_sessions[code]
            if old_chat_id in chat_id_to_code:
                chat_id_to_code.pop(old_chat_id)
            if old_chat_id in user_contexts:
                user_contexts.pop(old_chat_id)
            active_sessions.pop(code)
            session_timestamps.pop(code, None)
            bot.send_message(old_chat_id, "❌ اشتراک شما توسط ادمین غیرفعال شده است.")
        bot.send_message(chat_id, "✅ کاربر غیرفعال شد.")
    else:
        bot.send_message(chat_id, "❌ کاربر یافت نشد.")
    show_admin_menu(chat_id)

# ---------- اجرای ربات ----------
if __name__ == '__main__':
    keep_alive()  # فقط این خط اضافه شده
    print("🤖 ربات در حال اجراست...")
    bot.infinity_polling()
