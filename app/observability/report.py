# /app/observability/report.py
from configs.config import TG_BOT_TOKEN, TG_CHAT_ID
import urllib.request, json, logging

logger = logging.getLogger(__name__)


def get_channel_id():
    import ssl
    ssl_context = ssl._create_unverified_context()
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/getUpdates"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, context=ssl_context) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data['result'][0]['channel_post']['sender_chat']['id']
    except urllib.error.URLError as e:
        logger.error(f"report.py: Error {e}")
        return None


def reporter(message: str) -> None:
    try:
        if not TG_CHAT_ID:
            print(get_channel_id())
        message = ""
    except Exception as e:
        print(f"Error: {e}")
