import aiohttp
import logging
import config

logger = logging.getLogger(__name__)

async def oxapay_create_invoice(amount_usd, desc, order_ref):
    payload = {
        "merchant": config.OXAPAY_MERCHANT_KEY, 
        "amount": round(float(amount_usd), 2),
        "currency": "USDT", 
        "lifeTime": 30, 
        "feePaidByPayer": 1,
        "description": desc, 
        "orderId": order_ref,
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{config.OXAPAY_API_BASE}/merchants/request", json=payload) as r:
                data = await r.json()
                if data.get("result") == 100:
                    return {"payLink": data["payLink"], "trackId": data["trackId"]}
    except Exception as e:
        logger.error(f"OxaPay create invoice error: {e}")
    return None

async def oxapay_check(track_id):
    payload = {
        "merchant": config.OXAPAY_MERCHANT_KEY,
        "trackId": track_id
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{config.OXAPAY_API_BASE}/merchants/inquiry", json=payload) as r:
                data = await r.json()
                if data.get("result") == 100:
                    return data.get("status")
    except Exception as e:
        logger.error(f"OxaPay check error: {e}")
    return None
