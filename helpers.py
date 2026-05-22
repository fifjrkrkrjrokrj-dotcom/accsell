import io
import qrcode
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import config

def escape_mdv2(text):
    if not text:
        return ""
    special_chars = r'_*[]()~`>#+-=|{}.!'
    for ch in special_chars:
        text = text.replace(ch, f'\\{ch}')
    return text

def mesc(t):
    return escape_mdv2(str(t))

def now_ist():
    return datetime.now(config.IST)

def fmt_time(ts):
    if not ts:
        return "N/A"
    try:
        if isinstance(ts, str):
            dt = datetime.fromisoformat(ts)
        else:
            dt = ts
        if dt.tzinfo is None:
            # Assuming it was stored as UTC or local time
            from datetime import timezone
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(config.IST).strftime("%d %b %Y %H:%M IST")
    except Exception:
        return str(ts)

def status_emoji(s):
    return {"pending":"⏳","approved":"✅","rejected":"❌","paid":"💚","expired":"⌛","awaiting_utr":"🔄"}.get(s,"❓")

def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 Buy Numbers", callback_data="browse_0", style="primary"),
         InlineKeyboardButton("💰 My Wallet",       callback_data="wallet", style="primary")],
        [InlineKeyboardButton("🎟️ Redeem Coupon",  callback_data="redeem_prompt", style="primary"),
         InlineKeyboardButton("👥 Referrals",       callback_data="referrals", style="primary")],
        [InlineKeyboardButton("📦 My Orders",       callback_data="my_orders_0", style="primary"),
         InlineKeyboardButton("❓ Help",             callback_data="help", style="primary")],
    ])

def generate_upi_qr(amount, note):
    upi_url = f"upi://pay?pa={config.UPI_ID}&pn=NumberStore&am={amount}&cu=INR&tn={note}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(upi_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

def generate_referral_link(user_id):
    return f"https://t.me/{config.STORE_TAG.lstrip('@')}?start=ref_{user_id}"
