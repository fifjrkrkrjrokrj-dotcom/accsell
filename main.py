import logging
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters

import config
import database

# Handlers
from handlers.start import start, addchannel_cmd, removechannel_cmd, verify_sub
from handlers.shop import browse_numbers, category_detail, wallet_buy, pay_upi
from handlers.wallet import wallet, deposit_upi_cb, deposit_crypto_cb, check_dep_cb, redeem_prompt, dep_hist, my_orders, order_detail, cancel_utr_cb
from handlers.otp import reveal_number, get_otp, getotp_back, logout_prompt, logout_confirm
from handlers.admin import admin_menu, admin_users, admin_search_user, admin_edit_wallet, admin_orders, admin_close, admin_settings, set_usdt_rate_cb, approve_deposit, reject_deposit
from handlers.inputs import text_handler, screenshot_handler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # ApplicationBuilder will run asyncio event loop internally
    app = ApplicationBuilder().token(config.BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addchannel", addchannel_cmd))
    app.add_handler(CommandHandler("removechannel", removechannel_cmd))
    app.add_handler(CommandHandler("admin", admin_menu))

    # General Callbacks
    app.add_handler(CallbackQueryHandler(verify_sub, pattern="^verify_sub$"))
    app.add_handler(CallbackQueryHandler(browse_numbers, pattern=r"^browse_\d+$"))
    app.add_handler(CallbackQueryHandler(category_detail, pattern=r"^cat_\d+$"))
    app.add_handler(CallbackQueryHandler(wallet_buy, pattern=r"^wallet_buy_\d+$"))
    app.add_handler(CallbackQueryHandler(pay_upi, pattern=r"^pay_upi_\d+$"))
    app.add_handler(CallbackQueryHandler(wallet, pattern="^wallet$"))
    app.add_handler(CallbackQueryHandler(deposit_upi_cb, pattern="^deposit_upi$"))
    app.add_handler(CallbackQueryHandler(deposit_crypto_cb, pattern="^deposit_crypto$"))
    app.add_handler(CallbackQueryHandler(check_dep_cb, pattern=r"^chk_dep_\d+$"))
    app.add_handler(CallbackQueryHandler(redeem_prompt, pattern="^redeem_prompt$"))
    app.add_handler(CallbackQueryHandler(dep_hist, pattern=r"^dep_hist_\d+$"))
    app.add_handler(CallbackQueryHandler(my_orders, pattern=r"^my_orders_\d+$"))
    app.add_handler(CallbackQueryHandler(order_detail, pattern=r"^order_detail_\d+$"))
    app.add_handler(CallbackQueryHandler(cancel_utr_cb, pattern=r"^cancel_utr_\d+$"))
    
    # OTP Callbacks
    app.add_handler(CallbackQueryHandler(reveal_number, pattern=r"^reveal_\d+$"))
    app.add_handler(CallbackQueryHandler(get_otp, pattern=r"^getotp_\d+$"))
    app.add_handler(CallbackQueryHandler(getotp_back, pattern=r"^getotp_back_\d+$"))
    app.add_handler(CallbackQueryHandler(logout_prompt, pattern=r"^logout_prompt_\d+$"))
    app.add_handler(CallbackQueryHandler(logout_confirm, pattern=r"^logout_confirm_\d+$"))

    # Admin Callbacks
    app.add_handler(CallbackQueryHandler(admin_menu, pattern="^admin_menu$"))
    app.add_handler(CallbackQueryHandler(admin_close, pattern="^admin_close$"))
    app.add_handler(CallbackQueryHandler(admin_users, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(admin_search_user, pattern="^admin_search_user$"))
    app.add_handler(CallbackQueryHandler(admin_edit_wallet, pattern="^admin_edit_wallet$"))
    app.add_handler(CallbackQueryHandler(admin_orders, pattern=r"^admin_orders_[a-z_]+_\d+$"))
    app.add_handler(CallbackQueryHandler(admin_settings, pattern="^admin_settings$"))
    app.add_handler(CallbackQueryHandler(set_usdt_rate_cb, pattern="^set_usdt_rate$"))
    app.add_handler(CallbackQueryHandler(approve_deposit, pattern=r"^approve_deposit_\d+$"))
    app.add_handler(CallbackQueryHandler(reject_deposit, pattern=r"^reject_deposit_\d+$"))
    
    # Inputs (Text & Media)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.PHOTO, screenshot_handler))

    logger.info("✅ Modular Bot Starting Up with MongoDB...")

    # Run MongoDB init within the application loop
    import asyncio

    async def init():
    await database.init_db()

    asyncio.run(init())

    app.run_polling(drop_pending_updates=True)
