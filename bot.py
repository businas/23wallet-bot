import os
import datetime
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ParseMode
from pymongo import MongoClient

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("8305203190:AAEICcb-AcRpUO3JhxDuvvJ7jnX635oXt88")
ADMIN_ID = int(os.getenv("7579033502"))
SUPPORT = os.getenv("@qwallethelperbot")

MONGO_URL = os.getenv("mongodb+srv://hdnfaer:6rcwEsRoRUyY5URP@qwallet1.regstjp.mongodb.net/Qwallet1")
client = MongoClient(MONGO_URL)
db = client["wallet"]
users = db["users"]
txs = db["transactions"]
withdraws = db["withdraws"]

# ================== BOT INIT (FIXED) ==================
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.MARKDOWN)
dp = Dispatcher(bot)

# ================== HELPERS ==================
def get_user(uid):
    user = users.find_one({"_id": uid})
    if not user:
        user = {
            "_id": uid,
            "balance": 0.0,
            "frozen": False,
            "last_bonus": None
        }
        users.insert_one(user)
    return user

def main_menu(is_admin=False):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("💰 Balance", callback_data="balance"),
        InlineKeyboardButton("🎁 Daily Bonus", callback_data="bonus"),
        InlineKeyboardButton("💸 Withdraw", callback_data="withdraw"),
        InlineKeyboardButton("🎯 Tip User", callback_data="tip"),
        InlineKeyboardButton("📊 History", callback_data="history"),
        InlineKeyboardButton("👤 Profile", callback_data="profile"),
        InlineKeyboardButton("🆘 Support", callback_data="support"),
    )
    if is_admin:
        kb.add(InlineKeyboardButton("🔒 Admin Panel", callback_data="admin"))
    return kb

# ================== START ==================
@dp.message_handler(commands=["start"])
async def start(msg: types.Message):
    user = get_user(msg.from_user.id)
    if user["frozen"]:
        return await msg.answer("❌ Your account is *frozen* by admin.")

    text = (
        "👋 *Welcome to Q Wallet*\n\n"
        "💱 Rate: `1 Q = 1 USDT`\n"
        "⚡ Fast • Secure • Simple\n\n"
        "👇 Use buttons below"
    )
    await msg.answer(text, reply_markup=main_menu(msg.from_user.id == ADMIN_ID))

# ================== BALANCE ==================
@dp.callback_query_handler(lambda c: c.data == "balance")
async def balance(c: types.CallbackQuery):
    user = get_user(c.from_user.id)
    await c.message.edit_text(
        f"💰 *Your Balance*\n\n`{user['balance']} Q`",
        reply_markup=main_menu(c.from_user.id == ADMIN_ID)
    )

# ================== DAILY BONUS ==================
@dp.callback_query_handler(lambda c: c.data == "bonus")
async def bonus(c: types.CallbackQuery):
    user = get_user(c.from_user.id)
    today = datetime.date.today()

    if user["last_bonus"] == str(today):
        return await c.answer("⏳ Already claimed today", show_alert=True)

    users.update_one(
        {"_id": c.from_user.id},
        {"$set": {"last_bonus": str(today)}, "$inc": {"balance": 0.05}}
    )
    txs.insert_one({
        "user": c.from_user.id,
        "type": "Daily Bonus",
        "amount": 0.05,
        "date": datetime.datetime.utcnow()
    })
    await c.message.edit_text(
        "🎁 *Daily Bonus Claimed!*\n\n+ `0.05 Q` added",
        reply_markup=main_menu(c.from_user.id == ADMIN_ID)
    )

# ================== TIP ==================
@dp.callback_query_handler(lambda c: c.data == "tip")
async def tip_info(c: types.CallbackQuery):
    await c.message.edit_text(
        "🎯 *Send Tip*\n\n"
        "Send like:\n"
        "`/tip user_id amount`\n\n"
        "Minimum: `1 Q`",
        reply_markup=main_menu(c.from_user.id == ADMIN_ID)
    )

@dp.message_handler(commands=["tip"])
async def tip(msg: types.Message):
    args = msg.text.split()
    if len(args) != 3:
        return await msg.reply("Usage: `/tip user_id amount`")

    to_id = int(args[1])
    amount = float(args[2])

    sender = get_user(msg.from_user.id)
    receiver = get_user(to_id)

    if sender["balance"] < amount or amount < 1:
        return await msg.reply("❌ Invalid amount")

    users.update_one({"_id": msg.from_user.id}, {"$inc": {"balance": -amount}})
    users.update_one({"_id": to_id}, {"$inc": {"balance": amount}})

    txs.insert_many([
        {"user": msg.from_user.id, "type": "Tip Sent", "amount": -amount, "date": datetime.datetime.utcnow()},
        {"user": to_id, "type": "Tip Received", "amount": amount, "date": datetime.datetime.utcnow()}
    ])

    await bot.send_message(
        to_id,
        f"🎉 *You received a tip!*\n\n+ `{amount} Q` from `{msg.from_user.id}`"
    )
    await msg.reply("✅ Tip sent successfully")

# ================== WITHDRAW ==================
@dp.callback_query_handler(lambda c: c.data == "withdraw")
async def withdraw_menu(c: types.CallbackQuery):
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("TRC20", callback_data="wd_TRC20"),
        InlineKeyboardButton("BEP20", callback_data="wd_BEP20")
    )
    await c.message.edit_text("🌐 *Select Network*", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("wd_"))
async def withdraw_net(c: types.CallbackQuery):
    network = c.data.split("_")[1]
    await c.message.edit_text(
        f"💸 *Withdraw ({network})*\n\n"
        "Send:\n"
        "`/withdraw amount address`\n\n"
        "Minimum: `100 Q`"
    )

@dp.message_handler(commands=["withdraw"])
async def withdraw(msg: types.Message):
    args = msg.text.split()
    if len(args) != 3:
        return await msg.reply("Usage: `/withdraw amount address`")

    amount = float(args[1])
    address = args[2]
    user = get_user(msg.from_user.id)

    if amount < 100 or user["balance"] < amount:
        return await msg.reply("❌ Invalid withdraw")

    users.update_one({"_id": msg.from_user.id}, {"$inc": {"balance": -amount}})
    withdraws.insert_one({
        "user": msg.from_user.id,
        "amount": amount,
        "address": address,
        "status": "pending"
    })

    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_{msg.from_user.id}_{amount}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject_{msg.from_user.id}_{amount}")
    )
    await bot.send_message(ADMIN_ID, f"💸 Withdraw Request\nUser: `{msg.from_user.id}`\nAmount: `{amount}`", reply_markup=kb)
    await msg.reply("⏳ Withdraw request submitted")

# ================== ADMIN ==================
@dp.callback_query_handler(lambda c: c.data == "admin")
async def admin_panel(c: types.CallbackQuery):
    if c.from_user.id != ADMIN_ID:
        return
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("🔒 Freeze User", callback_data="freeze"),
        InlineKeyboardButton("🔓 Unfreeze User", callback_data="unfreeze")
    )
    await c.message.edit_text("🛠 *Admin Panel*", reply_markup=kb)

# ================== HISTORY ==================
@dp.callback_query_handler(lambda c: c.data == "history")
async def history(c: types.CallbackQuery):
    data = txs.find({"user": c.from_user.id}).sort("date", -1).limit(10)
    text = "📊 *Transaction History*\n\n"
    for t in data:
        text += f"{t['type']} : `{t['amount']} Q`\n"
    await c.message.edit_text(text, reply_markup=main_menu(c.from_user.id == ADMIN_ID))

# ================== PROFILE ==================
@dp.callback_query_handler(lambda c: c.data == "profile")
async def profile(c: types.CallbackQuery):
    u = get_user(c.from_user.id)
    await c.message.edit_text(
        f"👤 *Profile*\n\n"
        f"ID: `{c.from_user.id}`\n"
        f"Balance: `{u['balance']} Q`\n"
        f"Status: `{'Frozen' if u['frozen'] else 'Active'}`",
        reply_markup=main_menu(c.from_user.id == ADMIN_ID)
    )

# ================== SUPPORT ==================
@dp.callback_query_handler(lambda c: c.data == "support")
async def support(c: types.CallbackQuery):
    await c.message.edit_text(
        f"🆘 *Support*\n\n"
        f"Please send your issue clearly.\n"
        f"Our team will reply ASAP.\n\n"
        f"Contact: {SUPPORT}",
        reply_markup=main_menu(c.from_user.id == ADMIN_ID)
    )

# ================== RUN ==================
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
