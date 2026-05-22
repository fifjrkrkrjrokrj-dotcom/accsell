import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta
import re
import logging
import config

logger = logging.getLogger(__name__)

def check_gmail_for_payment(amount_inr, search_value, minutes=60):
    """
    Checks Gmail inbox for FamApp payment confirmation matching amount and UTR/TXN.
    Returns: (True, extracted_utr, extracted_txn) or (False, None, None)
    """
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(config.GMAIL_USER, config.GMAIL_APP_PASS)
        mail.select("inbox")

        since_time = (datetime.now() - timedelta(minutes=minutes)).strftime("%d-%b-%Y")
        search_criteria = f'(FROM "{config.FAMAPP_EMAILS[0]}" SINCE "{since_time}")'
        status, messages = mail.search(None, search_criteria)

        if status != "OK" or not messages[0]:
            mail.logout()
            return False, None, None

        email_ids = messages[0].split()
        if not search_value:
            mail.logout()
            return False, None, None

        for eid in reversed(email_ids[-20:]):
            status, msg_data = mail.fetch(eid, "(RFC822)")
            if status != "OK":
                continue

            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject = decode_header(msg["Subject"])[0][0]
                    if isinstance(subject, bytes):
                        subject = subject.decode()

                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            if content_type in ("text/plain", "text/html"):
                                try:
                                    payload = part.get_payload(decode=True)
                                    charset = part.get_content_charset() or 'utf-8'
                                    body += payload.decode(charset, errors='ignore')
                                except:
                                    pass
                    else:
                        try:
                            payload = msg.get_payload(decode=True)
                            charset = msg.get_content_charset() or 'utf-8'
                            body = payload.decode(charset, errors='ignore')
                        except:
                            pass

                    body_clean = re.sub(r'<[^>]+>', ' ', body)
                    full_text = f"{subject} {body_clean}"

                    # Check amount
                    amount_str = str(int(amount_inr))
                    amount_patterns = [
                        f"₹{amount_str}", f"rs.{amount_str}", f"rs {amount_str}",
                        f"inr {amount_str}", f"amount: {amount_str}", f"amount {amount_str}",
                        f"{amount_str}.00", f"{amount_str}.0",
                    ]

                    if not any(pat.lower() in full_text.lower() for pat in amount_patterns):
                        continue

                    # Check if search_value matches (UTR or Transaction ID)
                    if search_value.lower() not in full_text.lower():
                        continue

                    # Extract UTR and TXN
                    extracted_utr = None
                    extracted_txn = None

                    utr_patterns = [
                        r'UTR\s*:?\s*(\d{10,16})',
                        r'UTR\s*Number\s*:?\s*(\d{10,16})',
                        r'Reference\s*ID\s*:?\s*(\d{10,16})',
                        r'UTR\s*:?\s*(\d[\d\s]{8,18})'
                    ]
                    for pat in utr_patterns:
                        match = re.search(pat, full_text, re.IGNORECASE)
                        if match:
                            extracted_utr = re.sub(r'\s+', '', match.group(1))
                            break

                    txn_patterns = [
                        r'Transaction\s*ID\s*:?\s*([A-Za-z0-9]{8,30})',
                        r'Transaction\s*Number\s*:?\s*([A-Za-z0-9]{8,30})',
                        r'Transaction\s*:?\s*([A-Za-z0-9]{8,30})',
                        r'TXN\s*:?\s*([A-Za-z0-9]{8,30})',
                        r'(FMPIB\d{8,20})',
                        r'Transaction\s*(?:ID|Number)?\s*:?\s*(\d{8,20})'
                    ]
                    for pat in txn_patterns:
                        match = re.search(pat, full_text, re.IGNORECASE)
                        if match:
                            extracted_txn = re.sub(r'\s+', '', match.group(1)).upper()
                            break

                    mail.logout()
                    logger.info(f"✅ Gmail auto-match: Amount=₹{amount_inr}, UTR={extracted_utr}, TXN={extracted_txn}")
                    return True, extracted_utr, extracted_txn

        mail.logout()
        return False, None, None

    except Exception as e:
        logger.error(f"Gmail check error: {e}")
        return False, None, None
