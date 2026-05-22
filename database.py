import logging
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import config

logger = logging.getLogger(__name__)

# Global database client and db instance
client = None
db = None

async def init_db():
    global client, db
    client = AsyncIOMotorClient(config.MONGO_URI)
    db = client[config.DB_NAME]
    
    # Initialize default settings if not exist
    settings_coll = db.settings
    defaults = {
        "maintenance": "0",
        "upi_enabled": "1",
        "crypto_enabled": "1",
        "usdt_rate": "83",
        "welcome_message": "🏪 Welcome to NumberStore!\nBuy verified phone numbers instantly.\nFast • Secure • 24/7"
    }
    for k, v in defaults.items():
        existing = await settings_coll.find_one({"key": k})
        if not existing:
            await settings_coll.insert_one({"key": k, "value": v})
    
    logger.info("✅ MongoDB initialization complete")

async def get_setting(key, default=""):
    row = await db.settings.find_one({"key": key})
    return row["value"] if row else default

async def set_setting(key, value):
    await db.settings.update_one(
        {"key": key},
        {"$set": {"value": str(value)}},
        upsert=True
    )

async def get_usdt_rate():
    try:
        val = await get_setting("usdt_rate", "83")
        return float(val)
    except Exception:
        return 83.0

def inr_to_usd(inr, rate):
    return round(inr / rate, 2) if rate > 0 else 0.0

async def register_user(user, referrer_id=None):
    existing = await db.users.find_one({"_id": user.id})
    if not existing:
        await db.users.insert_one({
            "_id": user.id,
            "username": user.username or "",
            "first_name": user.first_name or "",
            "is_banned": 0,
            "total_purchases": 0,
            "wallet_balance": 0.0,
            "joined_at": datetime.now(config.IST),
            "referred_by": referrer_id
        })
    else:
        await db.users.update_one(
            {"_id": user.id},
            {"$set": {
                "username": user.username or "",
                "first_name": user.first_name or ""
            }}
        )

async def is_banned(user_id):
    row = await db.users.find_one({"_id": user_id})
    return row and row.get("is_banned") == 1

async def is_maintenance():
    return await get_setting("maintenance", "0") == "1"

def is_admin(user_id):
    return user_id in config.ADMIN_IDS

async def is_payment_used(utr=None, transaction_id=None):
    if not utr and not transaction_id:
        return False
    query = {"$or": []}
    if utr:
        query["$or"].append({"utr_number": utr})
    if transaction_id:
        query["$or"].append({"transaction_id": transaction_id})
    
    if not query["$or"]:
        return False
        
    row = await db.used_utrs.find_one(query)
    return bool(row)

async def mark_payment_used(utr, transaction_id, user_id):
    if not utr and not transaction_id:
        return
    try:
        await db.used_utrs.insert_one({
            "utr_number": utr,
            "transaction_id": transaction_id,
            "used_by": user_id,
            "used_at": datetime.now(config.IST)
        })
    except Exception as e:
        logger.error(f"mark_payment_used error: {e}")

async def get_stock_count(cat_id):
    return await db.accounts.count_documents({"category_id": cat_id, "is_sold": 0})

async def get_cat(cat_id):
    return await db.stock_categories.find_one({"_id": cat_id})

async def credit_referral_commission(user_id, deposit_amount):
    user = await db.users.find_one({"_id": user_id})
    if user and user.get("referred_by"):
        referrer_id = user["referred_by"]
        commission = round(deposit_amount * config.REFERRAL_COMMISSION, 2)
        if commission > 0:
            await db.users.update_one(
                {"_id": referrer_id},
                {"$inc": {"wallet_balance": commission}}
            )
            return referrer_id, commission
    return None, 0

async def get_next_sequence_value(sequence_name):
    # Custom auto-increment for orders, deposits, accounts, categories
    sequence_document = await db.counters.find_one_and_update(
        {"_id": sequence_name},
        {"$inc": {"sequence_value": 1}},
        upsert=True,
        return_document=True
    )
    return sequence_document["sequence_value"]
