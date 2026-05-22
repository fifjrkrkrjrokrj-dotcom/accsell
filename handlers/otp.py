import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import database
from helpers import mesc, now_ist
from modules.telethon_client import fetch_otp, logout_session

logger = logging.getLogger(__name__)

async def reveal_number(update, context):
    query = update.callback_query
    await query.answer()
    
    order_id = int(query.data.split("_")[1])
    user_id = query.from_user.id
    
    order = await database.db.orders.find_one({"_id": order_id, "user_id": user_id})
    if not order or order.get("status") != "approved":
        await query.edit_message_text("❌ Order not found or not approved.")
        return
        
    acc = await database.db.accounts.find_one({"_id": order["account_id"]})
    if not acc:
        await query.edit_message_text("❌ Account data not found.")
        return
        
    text = (
        f"📱 *Your Number Details*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📂 Category: {mesc(order['category_name'])}\n"
        f"📞 Number: `+{acc['phone_number']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📨 Get Latest OTP",     callback_data=f"getotp_{acc['_id']}", style="primary")],
        [InlineKeyboardButton("🔒 Logout Bot Session", callback_data=f"logout_prompt_{acc['_id']}", style="danger")],
        [InlineKeyboardButton("📦 My Orders",          callback_data="my_orders_0", style="primary")],
    ])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)

async def _get_order_for_acc(acc_id):
    row = await database.db.orders.find_one({"account_id": acc_id, "status": "approved"})
    return row["_id"] if row else 0

async def get_otp(update, context):
    query = update.callback_query
    await query.answer("⏳ Fetching OTP...")
    acc_id = int(query.data.split("_")[1])
    
    acc = await database.db.accounts.find_one({"_id": acc_id})
    if not acc:
        await query.edit_message_text("❌ Account not found.")
        return
        
    order_id = await _get_order_for_acc(acc_id)
    back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"reveal_{order_id}", style="primary")]])
    
    if not acc.get("session_string"):
        await query.edit_message_text("ℹ️ Bot session already logged out.", reply_markup=back_kb)
        return
        
    await query.edit_message_text("⏳ Connecting to fetch OTP...")
    
    otp_code, error_msg = await fetch_otp(acc["session_string"])
    
    if error_msg:
        await query.edit_message_text(error_msg, reply_markup=back_kb)
        return
        
    text = (
        f"🔑 *Latest OTP:* `{otp_code or 'Not found'}`\n"
        f"📞 `+{acc['phone_number']}`\n"
        f"⏱ {now_ist().strftime('%H:%M:%S IST')}\n\n"
        f"**✨ Thanks For Purchasing From Us ✔**"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh OTP",        callback_data=f"getotp_{acc_id}", style="primary")],
        [InlineKeyboardButton("🔒 Logout Bot Session", callback_data=f"logout_prompt_{acc_id}", style="danger")],
        [InlineKeyboardButton("🔙 Back",               callback_data=f"getotp_back_{acc_id}", style="primary")],
    ])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)

async def getotp_back(update, context):
    query = update.callback_query
    await query.answer()
    acc_id = int(query.data.split("_")[2])
    
    order_id = await _get_order_for_acc(acc_id)
    order = await database.db.orders.find_one({"_id": order_id})
    acc = await database.db.accounts.find_one({"_id": acc_id})
    
    if not order or not acc:
        await query.edit_message_text("❌ Order not found.")
        return
        
    text = (
        f"📱 *Your Number Details*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📂 Category: {mesc(order['category_name'])}\n"
        f"📞 Number: `+{acc['phone_number']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📨 Get Latest OTP",     callback_data=f"getotp_{acc['_id']}", style="primary")],
        [InlineKeyboardButton("🔒 Logout Bot Session", callback_data=f"logout_prompt_{acc['_id']}", style="danger")],
        [InlineKeyboardButton("📦 My Orders",          callback_data="my_orders_0", style="primary")],
    ])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)

async def logout_prompt(update, context):
    query = update.callback_query
    await query.answer()
    acc_id = int(query.data.split("_")[2])
    order_id = await _get_order_for_acc(acc_id)
    
    text = (
        "🔒 *Logout Bot Session*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚠️ This will remove the bot's authorized device from your Telegram account\\.\n\n"
        "✅ *Only proceed if you have already successfully logged into this account on your own device\\.*\n\n"
        "After logout, the bot will no longer be able to fetch OTPs for this number\\.\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔒 Yes, Logout Bot Now", callback_data=f"logout_confirm_{acc_id}", style="danger")],
        [InlineKeyboardButton("❌ Cancel", callback_data=f"reveal_{order_id}", style="primary")],
    ])
    await query.edit_message_text(text, parse_mode="MarkdownV2", reply_markup=kb)

async def logout_confirm(update, context):
    query = update.callback_query
    await query.answer("⏳ Logging out...")
    acc_id = int(query.data.split("_")[2])
    
    acc = await database.db.accounts.find_one({"_id": acc_id})
    if not acc:
        await query.edit_message_text("❌ Account not found.")
        return
        
    orders_kb = InlineKeyboardMarkup([[InlineKeyboardButton("📦 My Orders", callback_data="my_orders_0", style="primary")]])
    
    if not acc.get("session_string"):
        await query.edit_message_text("ℹ️ Bot session already logged out.", reply_markup=orders_kb)
        return
        
    await query.edit_message_text("⏳ Connecting to logout...")
    success = await logout_session(acc["session_string"])
    
    if success:
        await database.db.accounts.update_one({"_id": acc_id}, {"$set": {"session_string": ""}})
        await query.edit_message_text(
            "✅ *Bot session logged out successfully\\!*\n\n"
            "The bot's authorized device has been removed from your account\\.\n"
            "Your account is now fully under your control only\\. 🔐",
            parse_mode="MarkdownV2",
            reply_markup=orders_kb
        )
    else:
        order_id = await _get_order_for_acc(acc_id)
        await query.edit_message_text(
            "⚠️ Could not logout. Session may have already expired.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"reveal_{order_id}", style="primary")]])
        )
