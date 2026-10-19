import requests

from Cred._base import kite_credentials

TELEGRAM_TIMEOUT_SECONDS = 2  # Timeout for Telegram requests

class TelegramNotifier:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send_message(self, message):
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        params = {
            "chat_id": self.chat_id,
            "text": message
        }
        try:
            requests.get(url, params=params, timeout=TELEGRAM_TIMEOUT_SECONDS)
            print("📩 Telegram alert sent")
        except Exception as e:
            print(f"❌ Telegram error: {e}")

send_telegram = TelegramNotifier(kite_credentials.bot_token, kite_credentials.chat_id).send_message
