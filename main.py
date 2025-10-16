import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode 
import datetime
import logging
import os
import sys
import psycopg2

# ----------------- LOGGING -----------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# ----------------- ENV VARIABLES (সংশোধিত) -----------------
# Render/Railway-তে সেট করা ভেরিয়েবলগুলো এখান থেকে নেওয়া হবে।
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if TELEGRAM_BOT_TOKEN:
    TELEGRAM_BOT_TOKEN = TELEGRAM_BOT_TOKEN.strip()

# ডেটাবেস সংযোগের সমস্যার জন্য এখন আলাদা ভেরিয়েবল ব্যবহার করা হবে।
DB_NAME = os.environ.get("DB_NAME")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT") # পোর্ট সাধারণত 5432
DB_SSLMODE = os.environ.get("DB_SSLMODE") # মান হবে 'require'

try:
    admin_id_str = os.environ.get("ADMIN_USER_ID")
    if admin_id_str:
        ADMIN_USER_ID = int(admin_id_str.strip())
    else:
        # ফলব্যাক ID
        ADMIN_USER_ID = 12345678
except (TypeError, ValueError):
    # ফলব্যাক ID
    ADMIN_USER_ID = 12345678 

# ----------------- SETTINGS -----------------
ADSTERRA_DIRECT_LINK = "https://roughlydispleasureslayer.com/ykawxa7tnr?key=bacb6ca047e4fabf73e54c2eaf85b2a5"
TASK_LANDING_PAGE = "https://newspaper.42web.io"

CHANNEL_USERNAME = "@EarnQuickOfficial"
CHANNEL_INVITE_LINK = "https://t.me/EarnQuickOfficial"

DAILY_REWARD_POINTS = 10
REFERRAL_JOIN_BONUS = 50
REFERRAL_DAILY_COMMISSION = 2
MIN_WITHDRAW_POINTS = 1000

# ----------------- DATABASE FUNCTIONS (সংশোধিত) -----------------
def get_db_connection():
    # নতুন ভেরিয়েবল চেক করা হচ্ছে
    if not DB_NAME or not DB_USER:
        return None
    try:
        # আলাদা ভেরিয়েবল ব্যবহার করে সংযোগ
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
            sslmode=DB_SSLMODE
        )
        return conn
    except Exception as e:
        logger.error(f"DB connection failed: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            # users টেবিল তৈরি করা
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username VARCHAR(255),
                    points INTEGER DEFAULT 0,
                    last_claim_date DATE,
                    referrer_id BIGINT,
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
            logger.info("✅ PostgreSQL table ready")
    except Exception as e:
        logger.error(f"DB table creation error: {e}")
    finally:
        if conn: conn.close()

def get_user_data(user_id):
    conn = get_db_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id, username, points, last_claim_date, referrer_id FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            if row:
                return {
                    'user_id': row[0],
                    'username': row[1],
                    'points': row[2],
                    'last_claim_date': row[3],
                    'referrer_id': row[4]
                }
            return None
    except Exception as e:
        logger.error(f"Error fetching user data: {e}")
        return None
    finally:
        if conn: conn.close()

def add_new_user(user_id, username, referrer_id=None):
    conn = get_db_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (user_id, username, referrer_id) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO NOTHING",
                (user_id, username, referrer_id)
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Error adding new user: {e}")
    finally:
        if conn: conn.close()

def update_user_points(user_id, points_change, last_claim_date=None):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            if last_claim_date:
                cur.execute(
                    "UPDATE users SET points = points + %s, last_claim_date = %s WHERE user_id = %s",
                    (points_change, last_claim_date, user_id)
                )
            else:
                cur.execute(
                    "UPDATE users SET points = points + %s WHERE user_id = %s",
                    (points_change, user_id)
                )
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Error updating points: {e}")
        return False
    finally:
        if conn: conn.close()

def get_bot_stats():
    conn = get_db_connection()
    if not conn:
        return {'total_users': 0, 'total_points': 0}
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(user_id), COALESCE(SUM(points),0) FROM users;")
            row = cur.fetchone()
            return {'total_users': int(row[0]), 'total_points': int(row[1])} if row else {'total_users':0,'total_points':0}
    except Exception as e:
        logger.error(f"Error fetching bot stats: {e}")
        return {'total_users':0,'total_points':0}
    finally:
        if conn: conn.close()

def get_user_id_list():
    conn = get_db_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM users")
            rows = cur.fetchall()
            return [row[0] for row in rows]
    except Exception as e:
        logger.error(f"Error fetching user ids: {e}")
        return []
    finally:
        if conn: conn.close()

# ----------------- CHANNEL CHECK -----------------
async def check_channel_member(context: ContextTypes.DEFAULT_TYPE, user_id):
    try:
        member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ['member','administrator','creator']
    except:
        return False

async def show_join_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    join_message = (
        f"⛔ **কাজ শুরু করতে চ্যানেলে জয়েন করুন!**\n"
        f"{CHANNEL_INVITE_LINK}"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ জয়েন করেছি", callback_data='check_join')]
    ])
    if update.callback_query:
        await update.callback_query.edit_message_text(join_message, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(join_message, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

# ----------------- KEYBOARD -----------------
def get_main_keyboard(user_data):
    current_points = user_data.get('points',0) if user_data else 0
    keyboard = [
        [InlineKeyboardButton("💰 দৈনিক বোনাস", callback_data='daily_reward')],
        [InlineKeyboardButton("📰 ট্র্যাক ১", url=ADSTERRA_DIRECT_LINK)],
        [InlineKeyboardButton("🔗 ট্র্যাক ২", url=TASK_LANDING_PAGE)],
        [InlineKeyboardButton("🧠 ট্র্যাক ৩", url=TASK_LANDING_PAGE)],
        [InlineKeyboardButton(f"📊 ব্যালেন্স: {current_points}", callback_data='my_account')],
        [InlineKeyboardButton("💸 উইথড্রয়াল", callback_data='withdraw_request')],
        [InlineKeyboardButton("🏠 মূল মেনু", callback_data='start_menu_btn')]
    ]
    return InlineKeyboardMarkup(keyboard)

# ----------------- START -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.first_name or "New User"

    is_member = await check_channel_member(context, user_id)
    if not is_member:
        await show_join_prompt(update, context)
        return

    user_data = get_user_data(user_id)
    referrer_id = None
    if context.args and context.args[0].startswith('ref'):
        try:
            rid = int(context.args[0][3:])
            if rid != user_id and get_user_data(rid):
                referrer_id = rid
        except:
            pass

    if not user_data:
        add_new_user(user_id, username, referrer_id)
        user_data = get_user_data(user_id)
        if referrer_id:
            update_user_points(referrer_id, REFERRAL_JOIN_BONUS)
    reply_markup = get_main_keyboard(user_data)
    welcome_msg = f"🎉 স্বাগতম, {username}!\n✅ কাজ শুরু করতে মেনু ব্যবহার করুন।"
    if update.callback_query:
        await update.callback_query.edit_message_text(welcome_msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(welcome_msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

# ----------------- BUTTON CALLBACK -----------------
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    is_member = await check_channel_member(context, user_id)
    if not is_member and query.data not in ['check_join','start_menu_btn']:
        await show_join_prompt(query, context)
        return

    user_data = get_user_data(user_id)
    if not user_data:
        await query.edit_message_text("⛔ ডেটা পাওয়া যায়নি। /start করুন।")
        return

    if query.data == 'check_join':
        if await check_channel_member(context,user_id):
            await start(query,context)
        else:
            await show_join_prompt(query,context)
        return
    elif query.data == 'daily_reward':
        today = datetime.date.today()
        last_claim = user_data.get('last_claim_date')
        if last_claim == today:
            msg = "❌ আজকের রিওয়ার্ড ক্লেম করা হয়েছে।"
        else:
            if update_user_points(user_id, DAILY_REWARD_POINTS, today):
                referrer_id = user_data.get('referrer_id')
                if referrer_id:
                    update_user_points(referrer_id, REFERRAL_DAILY_COMMISSION)
                updated_user = get_user_data(user_id)
                msg = f"✅ {DAILY_REWARD_POINTS} পয়েন্ট যোগ হয়েছে। বর্তমান ব্যালেন্স: {updated_user['points']}"
            else:
                msg = "❌ পয়েন্ট আপডেটে সমস্যা।"
        await query.edit_message_text(msg, reply_markup=get_main_keyboard(get_user_data(user_id)), parse_mode=ParseMode.MARKDOWN)
    elif query.data == 'my_account':
        bot_username = context.bot.username
        referral_link = f"https://t.me/{bot_username}?start=ref{user_id}"
        acc_msg = f"📊 আপনার পয়েন্ট: {user_data['points']}\n🔗 রেফারেল লিঙ্ক: `{referral_link}`"
        await query.edit_message_text(acc_msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 মূল মেনু", callback_data='start_menu_btn')]]), parse_mode=ParseMode.MARKDOWN)
    elif query.data == 'withdraw_request':
        points = user_data['points']
        if points >= MIN_WITHDRAW_POINTS:
            msg = "💸 আপনার উইথড্রয়াল রিকোয়েস্ট লিখুন (বিকাশ/নগদ/রকেট/নম্বর)।"
        else:
            msg = f"❌ কমপক্ষে {MIN_WITHDRAW_POINTS} পয়েন্ট প্রয়োজন। আপনার পয়েন্ট: {points}"
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 মূল মেনু", callback_data='start_menu_btn')]]), parse_mode=ParseMode.MARKDOWN)
    elif query.data == 'start_menu_btn':
        await start(query, context)

# ----------------- ADMIN -----------------
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ শুধুমাত্র অ্যাডমিন।")
        return
    stats = get_bot_stats()
    await update.message.reply_text(f"📊 ইউজার: {stats['total_users']}\nপয়েন্ট: {stats['total_points']}")

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ শুধুমাত্র অ্যাডমিন।")
        return
    if not context.args:
        await update.message.reply_text("/broadcast <মেসেজ>")
        return
    msg = update.message.text.replace("/broadcast","",1).strip()
    user_ids = get_user_id_list()
    for uid in user_ids:
        try:
            await context.bot.send_message(uid,msg,parse_mode=ParseMode.MARKDOWN)
        except:
            continue
    await update.message.reply_text(f"✅ {len(user_ids)} ইউজারকে পাঠানো হয়েছে।")

# ----------------- MESSAGE HANDLER -----------------
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    user_data = get_user_data(user_id)
    if not user_data:
        await update.message.reply_text("⛔ /start করুন।")
        return
    # Forward withdraw requests to admin
    await context.bot.send_message(
        ADMIN_USER_ID,
        f"💸 উইথড্রয়াল রিকোয়েস্ট\nUser: {user_id}\nPoints: {user_data['points']}\nMessage: {text}"
    )
    await update.message.reply_text("আপনার মেসেজ অ্যাডমিনকে পাঠানো হয়েছে।", reply_markup=get_main_keyboard(user_data))

# ----------------- MAIN (সংশোধিত) -----------------
def main():
    # এখন DB_NAME চেক করা হবে
    if not TELEGRAM_BOT_TOKEN or not DB_NAME:
        logger.error("❌ ENV variables missing")
        sys.exit(1)
    init_db()
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(CommandHandler("stats", admin_stats))
    application.add_handler(CommandHandler("broadcast", admin_broadcast))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))
    print("✅ Smart Earn Bot Running...")
    application.run_polling(poll_interval=3)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        sys.exit(1)
