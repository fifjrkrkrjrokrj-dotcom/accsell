import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import database
from helpers import main_menu_kb
import config

logger = logging.getLogger(__name__)

async def get_force_channels():
    cursor = database.db.force_channels.find()
    return await cursor.to_list(length=None)

async def check_force_sub(bot, user_id):
    not_joined = []
    channels = await get_force_channels()
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch["channel_id"], user_id=user_id)
            if member.status in ("left", "kicked", "banned"):
                not_joined.append(ch)
        except Exception:
            not_joined.append(ch)
    return not_joined

async def send_force_sub_msg(update, not_joined):
    buttons = []
    for i, ch in enumerate(not_joined, 1):
        label = ch.get("channel_name") or f"Channel {i}"
        buttons.append([InlineKeyboardButton(f"➕ Join {label}", url=ch["channel_link"], style="primary")])
    buttons.append([InlineKeyboardButton("✅ I've Joined — Verify", callback_data="verify_sub", style="success")])
    
    lines = ["⚠️ *Access Restricted*\n━━━━━━━━━━━━━━━━━━━━\nJoin these channels to use the bot:\n"]
    for ch in not_joined:
        lines.append(f"• {ch.get('channel_name') or ch.get('channel_id')}")
    lines.append("\n━━━━━━━━━━━━━━━━━━━━\n_Tap Verify after joining._")
    
    msg = update.message or (update.callback_query.message if update.callback_query else None)
    if msg:
        try:
            await msg.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        except Exception:
            pass

async def guard(update, context):
    user = update.effective_user
    if not user:
        return True
    await database.register_user(user)
    
    if await database.is_banned(user.id):
        txt = "🚫 You are banned from using this bot."
        if update.callback_query:
            await update.callback_query.answer(txt, show_alert=True)
        else:
            await update.effective_message.reply_text(txt)
        return True
        
    if await database.is_maintenance() and not database.is_admin(user.id):
        txt = "🔧 Bot is under maintenance. Please try again later."
        if update.callback_query:
            await update.callback_query.answer(txt, show_alert=True)
        else:
            await update.effective_message.reply_text(txt)
        return True
        
    if not database.is_admin(user.id):
        not_joined = await check_force_sub(context.bot, user.id)
        if not_joined:
            await send_force_sub_msg(update, not_joined)
            return True
            
    return False

async def verify_sub(update, context):
    query = update.callback_query
    await query.answer()
    not_joined = await check_force_sub(context.bot, query.from_user.id)
    if not_joined:
        buttons = []
        for i, ch in enumerate(not_joined, 1):
            buttons.append([InlineKeyboardButton(f"➕ Join {ch.get('channel_name') or f'Channel {i}'}", url=ch["channel_link"], style="primary")])
        buttons.append([InlineKeyboardButton("✅ Verify Again", callback_data="verify_sub", style="success")])
        lines = ["❌ Still not joined all channels!\n"]
        for ch in not_joined:
            lines.append(f"• {ch.get('channel_name') or ch.get('channel_id')}")
        await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))
    else:
        msg = await database.get_setting("welcome_message", "🏪 Welcome to NumberStore!")
        await query.edit_message_text(msg, reply_markup=main_menu_kb())

async def start(update, context):
    if await guard(update, context):
        return
    msg_text = await database.get_setting("welcome_message", "🏪 Welcome to NumberStore!")
    user = update.effective_user
    
    # Handle referral
    if context.args and context.args[0].startswith("ref_"):
        try:
            referrer_id = int(context.args[0].split("_")[1])
            if referrer_id != user.id:
                existing = await database.db.users.find_one({"_id": user.id})
                if existing and not existing.get("referred_by"):
                    await database.db.users.update_one({"_id": user.id}, {"$set": {"referred_by": referrer_id}})
                    try:
                        await context.bot.send_message(
                            chat_id=referrer_id,
                            text=f"🎉 New user joined via your referral link!\nYou'll earn {config.REFERRAL_COMMISSION*100:.0f}% commission on their deposits forever."
                        )
                    except:
                        pass
        except (ValueError, IndexError):
            pass
            
    await update.message.reply_text(msg_text, reply_markup=main_menu_kb())

async def addchannel_cmd(update, context):
    if not database.is_admin(update.effective_user.id):
        return
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /addchannel <channel_id> <invite_link> [Name]")
        return
    ch_id, ch_link = args[0], args[1]
    ch_name = " ".join(args[2:]) if len(args) > 2 else ch_id
    
    await database.db.force_channels.update_one(
        {"channel_id": ch_id},
        {"$set": {"channel_link": ch_link, "channel_name": ch_name}},
        upsert=True
    )
    await update.message.reply_text(f"✅ Channel added: {ch_name}")

async def removechannel_cmd(update, context):
    if not database.is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: /removechannel <channel_id>")
        return
    await database.db.force_channels.delete_one({"channel_id": context.args[0]})
    await update.message.reply_text("✅ Channel removed.")
