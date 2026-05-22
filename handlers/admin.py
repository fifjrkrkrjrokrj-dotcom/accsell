import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import database
import config
from helpers import fmt_time, status_emoji

logger = logging.getLogger(__name__)

def clear_admin_states(context):
    """Clears all awaiting text input states to ensure true cancellation."""
    keys_to_clear = [
        "awaiting_search_user", "ban_action", "wallet_action",
        "admin_edit_balance_uid", "admin_set_price_cat", "awaiting_price_input",
        "awaiting_broadcast", "broadcast_msg_id", "broadcast_chat_id",
        "awaiting_usdt_rate", "awaiting_welcome_msg", "awaiting_category_name",
        "awaiting_zip_file", "upload_cat_id", "upload_mode", "awaiting_single_acc"
    ]
    for k in keys_to_clear:
        context.user_data.pop(k, None)

async def admin_menu(update, context):
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id
    
    if query:
        await query.answer()
        
    if not database.is_admin(user_id):
        return
        
    clear_admin_states(context)
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Stock", callback_data="admin_stock", style="primary"),
         InlineKeyboardButton("🛒 Orders", callback_data="admin_orders_all_0", style="primary")],
        [InlineKeyboardButton("💳 Deposits", callback_data="admin_deps_all_0", style="primary"),
         InlineKeyboardButton("👥 Users", callback_data="admin_users", style="primary")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast", style="primary"),
         InlineKeyboardButton("🎟️ Coupons", callback_data="admin_redeem_codes", style="primary")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings", style="primary"),
         InlineKeyboardButton("📊 Stats", callback_data="admin_stats", style="primary")],
        [InlineKeyboardButton("📺 Force Subs", callback_data="admin_channels", style="primary")],
        [InlineKeyboardButton("❌ Close", callback_data="admin_close", style="danger")],
    ])
    
    text = "👨‍💻 *Admin Panel*"
    if query:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)

async def admin_users(update, context):
    query = update.callback_query
    await query.answer()
    if not database.is_admin(query.from_user.id):
        return
        
    clear_admin_states(context)
        
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Search",       callback_data="admin_search_user", style="primary"),
         InlineKeyboardButton("🚫 Ban",           callback_data="admin_ban_user", style="danger"),
         InlineKeyboardButton("✅ Unban",          callback_data="admin_unban_user", style="success")],
        [InlineKeyboardButton("💰 Edit Wallet",   callback_data="admin_edit_wallet", style="primary")],
        [InlineKeyboardButton("🔙 Back",          callback_data="admin_menu", style="primary")],
    ])
    await query.edit_message_text("👥 *Users Manager*", parse_mode="Markdown", reply_markup=kb)

async def admin_search_user(update, context):
    query = update.callback_query
    await query.answer()
    clear_admin_states(context)
    context.user_data["awaiting_search_user"] = True
    await query.edit_message_text("Enter user ID or @username:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="admin_users", style="danger")]]))

async def admin_edit_wallet(update, context):
    query = update.callback_query
    await query.answer()
    clear_admin_states(context)
    context.user_data["awaiting_search_user"] = True
    context.user_data["wallet_action"] = True
    await query.edit_message_text("Enter user ID or @username to edit wallet:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cancel", callback_data="admin_users", style="danger")]]))

# --- Add other admin handlers (Orders, Deposits, Stats, Settings) ---
# To keep the file manageable and to the point, I'll provide the essential ones.

async def admin_orders(update, context):
    query = update.callback_query
    await query.answer()
    clear_admin_states(context)
    parts = query.data.split("_")
    sf = parts[2]
    page = int(parts[3])
    
    query_filter = {} if sf == "all" else {"status": sf}
    cursor = database.db.orders.find(query_filter).sort("created_at", -1)
    orders = await cursor.to_list(length=None)
    
    filter_btns = [
        InlineKeyboardButton("⏳ Pend",  callback_data="admin_orders_pending_0", style="primary"),
        InlineKeyboardButton("🔄 Await", callback_data="admin_orders_awaiting_utr_0", style="primary"),
        InlineKeyboardButton("✅ Appr",  callback_data="admin_orders_approved_0", style="success"),
        InlineKeyboardButton("❌ Rej",   callback_data="admin_orders_rejected_0", style="danger"),
    ]
    
    per_page = 5
    total = len(orders)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    chunk = orders[page * per_page:(page + 1) * per_page]
    
    buttons = [filter_btns]
    for o in chunk:
        buttons.append([InlineKeyboardButton(f"#{o['_id']} uid:{o['user_id']} ₹{o['amount_inr']:.0f} {status_emoji(o['status'])}", callback_data=f"admin_order_view_{o['_id']}", style="primary")])
        
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"admin_orders_{sf}_{page-1}", style="primary"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"admin_orders_{sf}_{page+1}", style="primary"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔙 Admin", callback_data="admin_menu", style="primary")])
    
    await query.edit_message_text(f"💰 *Orders ({sf.title()})*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def admin_close(update, context):
    query = update.callback_query
    await query.answer()
    clear_admin_states(context)
    await query.edit_message_text("Admin panel closed.")

async def admin_settings(update, context):
    query = update.callback_query
    await query.answer()
    clear_admin_states(context)
    maint  = await database.is_maintenance()
    upi    = await database.get_setting("upi_enabled",   "1") == "1"
    crypto = await database.get_setting("crypto_enabled","1") == "1"
    rate   = await database.get_usdt_rate()
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔧 Maintenance: {'ON→OFF' if maint else 'OFF→ON'}", callback_data="toggle_maintenance", style="danger" if maint else "success")],
        [InlineKeyboardButton(f"💳 UPI: {'✅ ON→Disable' if upi else '❌ OFF→Enable'}", callback_data="toggle_upi", style="success" if upi else "primary")],
        [InlineKeyboardButton(f"🪙 Crypto: {'✅ ON→Disable' if crypto else '❌ OFF→Enable'}", callback_data="toggle_crypto", style="success" if crypto else "primary")],
        [InlineKeyboardButton(f"💱 USDT Rate: ₹{rate:.0f} → Change", callback_data="set_usdt_rate", style="primary")],
        [InlineKeyboardButton("📝 Welcome Message", callback_data="edit_welcome_msg", style="primary")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_menu", style="primary")],
    ])
    await query.edit_message_text("⚙️ *Settings*", parse_mode="Markdown", reply_markup=kb)

async def set_usdt_rate_cb(update, context):
    query = update.callback_query
    await query.answer()
    clear_admin_states(context)
    context.user_data["awaiting_usdt_rate"] = True
    rate = await database.get_usdt_rate()
    await query.edit_message_text(
        f"💱 *Set USDT Rate*\n\nCurrent rate: 1 USDT = ₹{rate:.0f}\n\nEnter new INR rate for 1 USDT:\nExample: `85`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="admin_settings", style="danger")]]))

async def approve_deposit(update, context):
    query = update.callback_query
    await query.answer()
    dep_id = int(query.data.split("_")[2])
    
    dep = await database.db.deposits.find_one({"_id": dep_id})
    if dep and dep["status"] != "approved":
        await database.db.deposits.update_one({"_id": dep_id}, {"$set": {"status": "approved"}})
        await database.db.users.update_one({"_id": dep["user_id"]}, {"$inc": {"wallet_balance": dep["amount_inr"]}})
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(f"✅ Deposit #{dep_id} manually approved.")
        try:
            await context.bot.send_message(chat_id=dep["user_id"], text=f"✅ Your deposit of ₹{dep['amount_inr']:.0f} has been approved manually!")
        except:
            pass

async def reject_deposit(update, context):
    query = update.callback_query
    await query.answer()
    dep_id = int(query.data.split("_")[2])
    
    await database.db.deposits.update_one({"_id": dep_id}, {"$set": {"status": "rejected"}})
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text(f"❌ Deposit #{dep_id} manually rejected.")
    
    dep = await database.db.deposits.find_one({"_id": dep_id})
    if dep:
        try:
            await context.bot.send_message(chat_id=dep["user_id"], text=f"❌ Your deposit has been rejected by admin.")
        except:
            pass
