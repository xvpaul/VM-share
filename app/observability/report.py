# /app/observability/report.py
from configs.config import TG_BOT_TOKEN, TG_CHAT_ID
import urllib.request, json, logging

logger = logging.getLogger(__name__)


def telegram_reporting(message: str) -> None:
            logger.info('app/observability/report.py: telegram_reporting has been triggered')
            try:
                import ssl
                ssl_context = ssl._create_unverified_context()
                url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
                data = {
                    "chat_id": TG_CHAT_ID,
                    "text": message,
                    "parse_mode": "HTML"
                }
                data_bytes = json.dumps(data).encode('utf-8')
                req = urllib.request.Request(
                    url,
                    data=data_bytes,
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with urllib.request.urlopen(req, context=ssl_context) as response:
                    logger.info('app/observability/report.py: Telegram message sent successfully')
                    return None
            except Exception as e:
                logger.error(
                    f'app/observability/report.py: Error {e}')
