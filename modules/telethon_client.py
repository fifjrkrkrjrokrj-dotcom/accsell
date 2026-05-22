import re
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
import config

logger = logging.getLogger(__name__)

async def fetch_otp(session_string):
    """
    Connects to Telegram using the provided session string,
    fetches the latest OTP, and returns it.
    Returns (otp_code, error_message).
    """
    client = TelegramClient(StringSession(session_string), config.API_ID, config.API_HASH)
    otp_code = None
    error_msg = None
    
    try:
        await client.connect()
        pat = re.compile(r'\b\d{4,6}\b')
        for sender in ["+42777", 777000]:
            try:
                for msg in await client.get_messages(sender, limit=5):
                    if msg.text:
                        m = pat.search(msg.text)
                        if m:
                            otp_code = m.group()
                            break
                if otp_code:
                    break
            except Exception:
                continue
    except Exception as e:
        error_msg = ("❌ Session expired." if "session" in str(e).lower() or "auth" in str(e).lower()
                     else "⚠️ Could not fetch OTP.")
        logger.error(f"OTP fetch: {e}")
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
            
    return otp_code, error_msg

async def logout_session(session_string):
    """Logs out the session."""
    client = TelegramClient(StringSession(session_string), config.API_ID, config.API_HASH)
    try:
        await client.connect()
        await client.log_out()
        return True
    except Exception as e:
        logger.error(f"Logout error: {e}")
        return False
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
