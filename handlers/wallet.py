import asyncio
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import database
from helpers import status_emoji, main_menu_kb, generate_upi_qr, fmt_time
import config
from modules.oxapay import oxapay_create_invoice, oxapay_check

logger = logging.getLogger(__name__)

# Track active crypto polling tasks: {user_id: task}
ACTIVE_CRYPTO_TASKS = {}

async def wallet(update, context):
    query = update.callback_query
    await query.answer()
    
    # Cancel any active crypto tasks if entering wallet
    user_id = query.from_user.id
    if user_id in ACTIVE_CRYPTO_TASKS:
        task = ACTIVE_CRYPTO_TASKS.pop(user_id)
        if not task.done():
            task.cancel()
            logger.info(f"Cancelled crypto polling task for user {user_id}")

    row = await database.db.users.find_one({"_id": user_id})
    bal = row.get("wallet_balance", 0) if row else 0
    
    upi_on    = await database.get_setting("upi_enabled",   "1") == "1"
    crypto_on = await database.get_setting("crypto_enabled","1") == "1"
    
    buttons = []
    if upi_on:
        buttons.append([InlineKeyboardButton("➕ Deposit via UPI",    callback_data="deposit_upi", style="success")])
    if crypto_on:
        buttons.append([InlineKeyboardButton("🪙 Deposit via Crypto", callback_data="deposit_crypto", style="success")])
    buttons += [
        [InlineKeyboardButton("🎟️ Redeem Coupon",   callback_data="redeem_prompt", style="primary")],
        [InlineKeyboardButton("📋 Deposit History", callback_data="dep_hist_0", style="primary")],
        [InlineKeyboardButton("🔙 Main Menu",        callback_data="main_menu", style="primary")],
    ]
    await query.edit_message_text(
        f"💰 *My Wallet*\n━━━━━━━━━━━━━━━━━━━━\n💵 Balance: ₹{bal:.2f} INR\n━━━━━━━━━━━━━━━━━━━━",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def deposit_upi_cb(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_dep_amount"] = True
    context.user_data["dep_method"]          = "upi"
    await query.edit_message_text(
        "💳 *UPI Deposit*\nEnter amount in INR:\n_\\(Minimum ₹20\\)_",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="wallet", style="danger")]]))

async def deposit_crypto_cb(update, context):
    query = update.callback_query
    await query.answer()
    rate = await database.get_usdt_rate()
    context.user_data["awaiting_dep_amount"] = True
    context.user_data["dep_method"]          = "crypto"
    await query.edit_message_text(
        f"🪙 *Crypto Deposit*\nEnter amount in USD:\n_(Minimum $0.1 | Rate: 1 USDT = ₹{rate:.0f})_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="wallet", style="danger")]]))

async def check_dep_cb(update, context):
    query  = update.callback_query
    dep_id = int(query.data.split("_")[2])
    dep    = await database.db.deposits.find_one({"_id": dep_id})
    
    if not dep:
        await query.answer("Deposit not found.", show_alert=True)
        return
    if dep.get("status") == "approved":
        await query.answer("✅ Already credited!", show_alert=True)
        return
        
    status = await oxapay_check(dep.get("crypto_track_id"))
    label  = {"Waiting":"⏳ Waiting","Paid":"✅ Paid","Expired":"⌛ Expired","Failed":"❌ Failed"}.get(status,"❓")
    await query.answer(f"Status: {label}", show_alert=True)

async def poll_crypto_deposit(context, track_id, user_id, dep_id):
    """Background task to poll OxaPay."""
    for _ in range(60): # Poll for 30 minutes (every 30s)
        await asyncio.sleep(30)
        try:
            status = await oxapay_check(track_id)
            if status == "Paid":
                dep = await database.db.deposits.find_one({"_id": dep_id, "status": "pending"})
                if dep:
                    await database.db.deposits.update_one(
                        {"_id": dep_id},
                        {"$set": {"status": "approved", "reviewed_at": database.datetime.now(config.IST).isoformat()}}
                    )
                    await database.db.users.update_one(
                        {"_id": user_id},
                        {"$inc": {"wallet_balance": dep["amount_inr"]}}
                    )
                    try:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"✅ *Crypto Deposit Approved!*\n₹{dep['amount_inr']:.0f} credited to your wallet.",
                            parse_mode="Markdown",
                            reply_markup=main_menu_kb()
                        )
                        # Check referral
                        await database.credit_referral_commission(user_id, dep["amount_inr"])
                    except:
                        pass
                break
            elif status in ("Expired", "Failed"):
                await database.db.deposits.update_one(
                    {"_id": dep_id},
                    {"$set": {"status": "rejected", "reviewed_at": database.datetime.now(config.IST).isoformat()}}
                )
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="❌ Crypto deposit expired or failed.",
                        reply_markup=main_menu_kb()
                    )
                except:
                    pass
                break
        except asyncio.CancelledError:
            # Task was explicitly cancelled
            logger.info(f"Crypto polling for user {user_id} cancelled.")
            raise
        except Exception as e:
            logger.error(f"Poll error: {e}")

async def redeem_prompt(update, context):
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_redeem_code"] = True
    await query.edit_message_text(
        "🎟️ *Redeem Coupon*\n\nEnter your redeem code:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="wallet", style="danger")]])
    )

async def dep_hist(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    page = int(query.data.split("_")[2])
    
    deps_cursor = database.db.deposits.find({"user_id": user_id}).sort("created_at", -1)
    deps = await deps_cursor.to_list(length=None)
    
    per_page = 5
    total = len(deps)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    chunk = deps[page * per_page:(page + 1) * per_page]
    
    lines = ["📋 *Deposit History*"]
    for d in chunk:
        lines.append(f"• #{d['_id']} | ₹{d['amount_inr']:.0f} | {d['payment_method'].upper()} | {status_emoji(d['status'])}")
    
    if not chunk:
        lines.append("No deposits found.")
        
    buttons = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"dep_hist_{page-1}", style="primary"))
        nav.append(InlineKeyboardButton(f"{page+1}/{pages}", callback_data="noop", style="primary"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"dep_hist_{page+1}", style="primary"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔙 Wallet", callback_data="wallet", style="primary")])
    
    await query.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def my_orders(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    page = int(query.data.split("_")[2])
    
    orders_cursor = database.db.orders.find({"user_id": user_id}).sort("created_at", -1)
    orders = await orders_cursor.to_list(length=None)
    
    per_page = 5
    total = len(orders)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    chunk = orders[page * per_page:(page + 1) * per_page]
    
    buttons = []
    for o in chunk:
        buttons.append([InlineKeyboardButton(f"#{o['_id']} {o['category_name'][:15]} {status_emoji(o['status'])}", callback_data=f"order_detail_{o['_id']}", style="primary")])
        
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"my_orders_{page-1}", style="primary"))
        nav.append(InlineKeyboardButton(f"{page+1}/{pages}", callback_data="noop", style="primary"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"my_orders_{page+1}", style="primary"))
    if nav:
        buttons.append(nav)
        
    buttons.append([InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu", style="primary")])
    
    text = "📦 *My Orders*" if chunk else "📦 You have no orders yet."
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def order_detail(update, context):
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split("_")[2])
    order = await database.db.orders.find_one({"_id": order_id, "user_id": query.from_user.id})
    
    if not order:
        await query.edit_message_text("❌ Order not found.")
        return
        
    text = (
        f"📦 *Order #{order['_id']}*\n"
        f"📂 {order['category_name']}\n"
        f"💰 ₹{order['amount_inr']:.0f} | {order['payment_method'].upper()}\n"
        f"📊 {status_emoji(order['status'])} {order['status'].title()}\n"
        f"📅 {fmt_time(order['created_at'])}"
    )
    
    buttons = []
    if order["status"] == "approved":
        buttons.append([InlineKeyboardButton("📱 Reveal Number", callback_data=f"reveal_{order['_id']}", style="success")])
    elif order["status"] == "awaiting_utr" and order["payment_method"] == "upi":
        context.user_data["awaiting_utr"] = True
        context.user_data["utr_order_id"] = order['_id']
        text += "\n\n⚠️ *Awaiting UTR/Transaction ID*\nPlease send your UTR/Transaction ID below:"
        buttons.append([InlineKeyboardButton("❌ Cancel Order", callback_data=f"cancel_utr_{order['_id']}", style="danger")])
        
    buttons.append([InlineKeyboardButton("🔙 Back to Orders", callback_data="my_orders_0", style="primary")])
    
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def cancel_utr_cb(update, context):
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split("_")[2])
    
    await database.db.orders.update_one(
        {"_id": order_id, "status": "awaiting_utr"},
        {"$set": {"status": "rejected"}}
    )
    context.user_data.pop("utr_order_id", None)
    context.user_data.pop("awaiting_utr", None)
    await query.edit_message_text("❌ Order cancelled.", reply_markup=main_menu_kb())
