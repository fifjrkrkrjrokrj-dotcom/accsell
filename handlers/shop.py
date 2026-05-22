import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import database
from helpers import mesc, main_menu_kb
import config
from handlers.start import guard

logger = logging.getLogger(__name__)

async def browse_numbers(update, context):
    query = update.callback_query
    await query.answer()
    if await guard(update, context):
        return
        
    page = int(query.data.split("_")[1])
    cursor = database.db.stock_categories.find({"enabled": 1})
    cats = await cursor.to_list(length=None)
    
    per_page = 10
    total = len(cats)
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    chunk = cats[page * per_page:(page + 1) * per_page]
    
    buttons = []
    for c in chunk:
        count = await database.get_stock_count(c["_id"])
        btn_text = f"📱 {c['name']} | ₹{c['price_inr']} | 📦 {count}"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"cat_{c['_id']}", style="primary")])
        
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"browse_{page-1}", style="primary"))
        nav.append(InlineKeyboardButton(f"{page+1}/{pages}", callback_data="noop", style="primary"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"browse_{page+1}", style="primary"))
    if nav:
        buttons.append(nav)
        
    buttons.append([InlineKeyboardButton("🔙 Main Menu", callback_data="main_menu", style="primary")])
    await query.edit_message_text("🛒 *Available Services*\nSelect a service to buy:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def category_detail(update, context):
    query = update.callback_query
    await query.answer()
    if await guard(update, context):
        return
        
    cat_id = int(query.data.split("_")[1])
    c = await database.get_cat(cat_id)
    if not c:
        await query.edit_message_text("❌ Category not found.", reply_markup=main_menu_kb())
        return
        
    count = await database.get_stock_count(cat_id)
    rate = await database.get_usdt_rate()
    usd = database.inr_to_usd(c["price_inr"], rate)
    
    text = (
        f"📱 *Service:* {mesc(c['name'])}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 Price: ₹{c['price_inr']:.0f} INR \\(~${usd:.2f} USD\\)\n"
        f"📦 Stock Available: {count}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"Choose payment method:"
    )
    
    buttons = []
    if count > 0:
        buttons.append([InlineKeyboardButton("💰 Pay via Wallet", callback_data=f"wallet_buy_{cat_id}", style="success")])
        upi_on = await database.get_setting("upi_enabled", "1") == "1"
        crypto_on = await database.get_setting("crypto_enabled", "1") == "1"
        if upi_on:
            buttons.append([InlineKeyboardButton("💳 Pay via UPI", callback_data=f"pay_upi_{cat_id}", style="primary")])
        if crypto_on:
            buttons.append([InlineKeyboardButton("🪙 Pay via Crypto", callback_data=f"pay_crypto_{cat_id}", style="primary")])
    else:
        text += "\n\n❌ _Out of stock! Check back later._"
        
    buttons.append([InlineKeyboardButton("🔙 Back to Shop", callback_data="browse_0", style="primary")])
    await query.edit_message_text(text, parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(buttons))

async def wallet_buy(update, context):
    query = update.callback_query
    await query.answer()
    if await guard(update, context):
        return
        
    cat_id = int(query.data.split("_")[2])
    c = await database.get_cat(cat_id)
    user_id = query.from_user.id
    
    user = await database.db.users.find_one({"_id": user_id})
    bal = user.get("wallet_balance", 0)
    
    if bal < c["price_inr"]:
        await query.answer(f"❌ Insufficient balance! Need ₹{c['price_inr']:.0f}", show_alert=True)
        return
        
    acc = await database.db.accounts.find_one({"category_id": cat_id, "is_sold": 0})
    if not acc:
        await query.answer("❌ Out of stock!", show_alert=True)
        return
        
    now = database.datetime.now(config.IST).isoformat()
    
    await database.db.users.update_one({"_id": user_id}, {"$inc": {"wallet_balance": -c["price_inr"], "total_purchases": 1}})
    await database.db.accounts.update_one({"_id": acc["_id"]}, {"$set": {"is_sold": 1, "sold_to": user_id, "sold_at": now}})
    
    order_id = await database.get_next_sequence_value("orders")
    await database.db.orders.insert_one({
        "_id": order_id,
        "user_id": user_id,
        "username": user.username,
        "account_id": acc["_id"],
        "category_id": cat_id,
        "category_name": c["name"],
        "amount_inr": c["price_inr"],
        "amount_usd": 0,
        "payment_method": "wallet",
        "status": "approved",
        "created_at": now,
        "reviewed_by": 0,
        "reviewed_at": now
    })
    
    await send_purchase_log(context.bot, c["name"], c["price_inr"], acc["phone_number"], user.username, user.id)
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("📱 Reveal Number", callback_data=f"reveal_{order_id}", style="primary")]])
    await query.edit_message_text(f"✅ *Purchase Successful!*\nOrder #{order_id} active.", parse_mode="Markdown", reply_markup=kb)

async def pay_upi(update, context):
    query = update.callback_query
    await query.answer()
    if await guard(update, context):
        return
        
    cat_id = int(query.data.split("_")[2])
    c = await database.get_cat(cat_id)
    
    order_id = await database.get_next_sequence_value("orders")
    await database.db.orders.insert_one({
        "_id": order_id,
        "user_id": query.from_user.id,
        "username": query.from_user.username,
        "account_id": None,
        "category_id": cat_id,
        "category_name": c["name"],
        "amount_inr": c["price_inr"],
        "amount_usd": 0,
        "payment_method": "upi",
        "status": "awaiting_utr",
        "created_at": database.datetime.now(config.IST).isoformat()
    })
    
    context.user_data["awaiting_utr"] = True
    context.user_data["utr_order_id"] = order_id
    
    text = (
        f"💳 *UPI Payment*\n"
        f"Pay EXACTLY: `₹{c['price_inr']:.0f}`\n"
        f"UPI ID: `{config.UPI_ID}`\n\n"
        f"After paying, enter your **UTR** or **Transaction ID** below."
    )
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel Order", callback_data=f"cancel_utr_{order_id}", style="danger")]])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)

async def send_purchase_log(bot, category_name, price_inr, phone_number, username, user_id):
    ph = str(phone_number)
    masked = f"+{ph[:4]}{'•' * max(0, len(ph)-4)}"
    user_tag = f"@{username}" if username else f"ID:{user_id}"
    text = (
        f"✅ New Number Purchase Successful\n"
        f"➖ Category: {category_name} | ₹{price_inr:.0f}\n"
        f"➕ Number: {masked} 📞\n"
        f"➕ Server: ({config.SERVER_NUM}) 🥂\n"
        f"• {user_tag} || {config.STORE_TAG}"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛒 Buy Now", url=config.STORE_LINK, style="primary")]])
    try:
        await bot.send_message(chat_id=config.LOG_CHANNEL_ID, text=text, reply_markup=kb)
    except Exception as e:
        logger.error(f"Log channel error: {e}")
