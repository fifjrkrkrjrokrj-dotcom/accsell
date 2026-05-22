import asyncio
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import time

import database
import config
from helpers import main_menu_kb, generate_upi_qr, status_emoji
from modules.gmail_checker import check_gmail_for_payment
from modules.oxapay import oxapay_create_invoice
from handlers.wallet import poll_crypto_deposit, ACTIVE_CRYPTO_TASKS

logger = logging.getLogger(__name__)

async def text_handler(update, context):
    user = update.effective_user
    text = update.message.text.strip()

    # ── AMOUNT INPUT FOR DEPOSIT ──
    if context.user_data.get("awaiting_dep_amount"):
        try:
            amount = float(text)
        except ValueError:
            await update.message.reply_text("❌ Invalid number. Try again:")
            return
            
        method = context.user_data.pop("dep_method", "upi")
        context.user_data.pop("awaiting_dep_amount", None)

        if method == "upi":
            if amount < 20:
                await update.message.reply_text("❌ Minimum ₹20. Enter again:")
                context.user_data["awaiting_dep_amount"] = True
                context.user_data["dep_method"] = "upi"
                return
                
            context.user_data["dep_inr"] = amount
            # New flow: ask for UTR first
            context.user_data["awaiting_dep_utr"] = True
            
            qr_buf = generate_upi_qr(amount, f"Deposit")
            await update.message.reply_photo(
                photo=qr_buf,
                caption=f"💳 UPI Deposit\nAmount: Rs{amount:.0f}\nUPI ID: `{config.UPI_ID}`\n\nPay EXACT amount.\nAfter paying, please enter your UTR/Transaction ID below:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="wallet", style="danger")]])
            )
        else:
            # Crypto Deposit
            if amount < 0.1:
                await update.message.reply_text("❌ Minimum $0.1. Enter again:")
                context.user_data["awaiting_dep_amount"] = True
                context.user_data["dep_method"] = "crypto"
                return
                
            rate = await database.get_usdt_rate()
            inr_est = round(amount * rate, 2)
            
            msg = await update.message.reply_text("⏳ Generating crypto invoice...")
            
            invoice = await oxapay_create_invoice(amount, f"Deposit", f"dep_{user.id}_{int(time.time())}")
            if not invoice:
                await msg.edit_text("❌ Failed to create invoice.", reply_markup=main_menu_kb())
                return
                
            dep_id = await database.get_next_sequence_value("deposits")
            await database.db.deposits.insert_one({
                "_id": dep_id,
                "user_id": user.id,
                "amount_inr": inr_est,
                "amount_usd": amount,
                "payment_method": "crypto",
                "crypto_track_id": invoice["trackId"],
                "status": "pending",
                "created_at": database.datetime.now(config.IST).isoformat()
            })
            
            text_resp = (
                f"🪙 *Crypto Deposit*\n"
                f"Amount: ${amount:.2f} USDT (~₹{inr_est:.0f})\n"
                f"Rate: 1 USDT = ₹{rate:.0f}\n"
                f"Expires: 30 minutes | Auto-credited ✅"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 Pay Now (OxaPay)", url=invoice["payLink"], style="success")],
                [InlineKeyboardButton("🔄 Check Status", callback_data=f"chk_dep_{dep_id}", style="primary")],
                [InlineKeyboardButton("❌ Cancel", callback_data="wallet", style="danger")]
            ])
            await msg.edit_text(text_resp, parse_mode="Markdown", reply_markup=kb)
            
            # Start polling and track task
            task = asyncio.create_task(poll_crypto_deposit(context, invoice["trackId"], user.id, dep_id))
            ACTIVE_CRYPTO_TASKS[user.id] = task
        return

    # ── UTR/TXN INPUT FOR DEPOSIT ──
    if context.user_data.get("awaiting_dep_utr"):
        context.user_data.pop("awaiting_dep_utr")
        user_input = text
        amount_inr = context.user_data.get("dep_inr")
        
        if not user_input or not amount_inr:
            await update.message.reply_text("❌ Invalid input.", reply_markup=main_menu_kb())
            return
        
        await update.message.reply_text("⏳ Checking your deposit...")
        
        if await database.is_payment_used(utr=user_input, transaction_id=user_input):
            await update.message.reply_text("❌ This UTR/Transaction ID has already been used!", reply_markup=main_menu_kb())
            return
            
        match_found, extracted_utr, extracted_txn = await asyncio.to_thread(
            check_gmail_for_payment, amount_inr, user_input, 60
        )
        
        dep_id = await database.get_next_sequence_value("deposits")
        
        if match_found:
            final_utr = extracted_utr or (user_input if user_input.isdigit() else None)
            final_txn = extracted_txn or (user_input if not user_input.isdigit() else None)
            
            await database.mark_payment_used(final_utr, final_txn, user.id)
            now = database.datetime.now(config.IST).isoformat()
            
            await database.db.deposits.insert_one({
                "_id": dep_id,
                "user_id": user.id,
                "amount_inr": amount_inr,
                "payment_method": "upi",
                "utr_number": final_utr,
                "transaction_id": final_txn,
                "status": "approved",
                "created_at": now,
                "reviewed_by": 0,
                "reviewed_at": now
            })
            
            await database.db.users.update_one({"_id": user.id}, {"$inc": {"wallet_balance": amount_inr}})
            
            await update.message.reply_text(
                f"✅ *Auto-Approved!* ₹{amount_inr:.0f} credited to your wallet!",
                parse_mode="Markdown",
                reply_markup=main_menu_kb()
            )
            
            ref_id, commission = await database.credit_referral_commission(user.id, amount_inr)
            if ref_id and commission > 0:
                try:
                    await context.bot.send_message(chat_id=ref_id, text=f"💰 You earned ₹{commission:.2f} referral commission!")
                except:
                    pass
        else:
            # Auto approval failed -> store initial deposit and ask for screenshot
            final_utr = user_input if user_input.isdigit() else None
            final_txn = user_input if not user_input.isdigit() else None
            
            await database.db.deposits.insert_one({
                "_id": dep_id,
                "user_id": user.id,
                "amount_inr": amount_inr,
                "payment_method": "upi",
                "utr_number": final_utr,
                "transaction_id": final_txn,
                "status": "pending", # wait for screenshot
                "created_at": database.datetime.now(config.IST).isoformat()
            })
            
            context.user_data["awaiting_deposit_screenshot_utr_failed"] = True
            context.user_data["failed_dep_id"] = dep_id
            
            await update.message.reply_text(
                "⏳ Could not auto-verify. Please provide your payment screenshot for manual review.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="wallet", style="danger")]])
            )
        return

async def screenshot_handler(update, context):
    user = update.effective_user
    photo = update.message.photo[-1]
    
    if context.user_data.get("awaiting_deposit_screenshot_utr_failed"):
        context.user_data.pop("awaiting_deposit_screenshot_utr_failed", None)
        dep_id = context.user_data.pop("failed_dep_id", None)
        
        if not dep_id:
            await update.message.reply_text("❌ Session expired.", reply_markup=main_menu_kb())
            return
            
        file_id = photo.file_id
        
        # update the deposit with screenshot
        await database.db.deposits.update_one(
            {"_id": dep_id},
            {"$set": {"screenshot": file_id}}
        )
        
        dep = await database.db.deposits.find_one({"_id": dep_id})
        
        await update.message.reply_text("✅ Screenshot received! Sent to admin for manual review.", reply_markup=main_menu_kb())
        
        # Send to admin group
        try:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Approve", callback_data=f"approve_deposit_{dep_id}", style="success"),
                 InlineKeyboardButton("❌ Reject",  callback_data=f"reject_deposit_{dep_id}", style="danger")]
            ])
            text = (
                f"💳 *Manual Deposit Review*\n"
                f"Deposit #{dep_id}\n"
                f"👤 User: {user.first_name} (@{user.username})\n"
                f"🆔 User ID: `{user.id}`\n"
                f"💵 Amount: ₹{dep['amount_inr']:.0f}\n"
                f"🔢 UTR: `{dep.get('utr_number') or 'None'}`\n"
                f"🆔 TXN: `{dep.get('transaction_id') or 'None'}`"
            )
            await context.bot.send_photo(
                chat_id=config.ADMIN_GROUP_ID,
                photo=file_id,
                caption=text,
                parse_mode="Markdown",
                reply_markup=kb
            )
        except Exception as e:
            logger.error(f"Failed to send to admin group: {e}")
            
    # Other screenshot logic (like order screenshot) can go here if needed...
