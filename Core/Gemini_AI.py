
import os

import requests
from google.genai import Client

from Core.send_notification import send_telegram


class GeminiAI:
    def __init__(self, client):
        self.client = client
        self.margin_buffer: float = 0.003  # 2% of total capital

    def get_account_info(self):
        url = f"{self.base_url}/account"
        response = requests.get(url, auth=(self.api_key, self.api_secret))
        return response.json()


    def motivate_trader(self):
        if self.client is None:
            print("⚠️ Gemini client not initialized. Skipping motivational message.")
            return

        try:
            response = self.client.models.generate_content(
                model="gemini-3.1-flash-lite-preview",
                contents=[
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": (
                                    "A stop-loss was triggered on a Nifty credit spread. "
                                    f"Risk was limited to {abs(self.margin_buffer * 100):.2f}% of total capital. "
                                    "This is the 2nd consecutive loss. "
                                    "The trader followed all predefined rules.\n\n"
                                    "Generate a short motivational message reinforcing discipline, "
                                    "risk management, and long-term statistical thinking."
                                )
                            }
                        ],
                    }
                ],
                config={
                    "system_instruction": (
                        "You are a calm, professional trading performance coach. "
                        "The trader has just exited due to a stop-loss. "
                        "Reinforce discipline and emotional stability. "
                        "Do NOT mention recovering losses or making money back. "
                        "Do NOT encourage aggressive trading. "
                        "Keep the response under 2 sentences. "
                        "Tone: grounded, calm, professional."
                    )
                },
            )
            #os.system(f'say "{response.text}"')
            print(f"💬 Motivational message: {response.text}")
            send_telegram(f"💬 Motivational message: {response.text}")
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ Error generating motivational message: {e}")


client = None


def motivate_trader():
    """Fallback used when Gemini is not configured."""
    print("⚠️ Gemini client not initialized. Skipping motivational message.")


try:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("OPEN_API_KEY")
    if api_key:
        client = Client(api_key=api_key)
        motivate_trader = GeminiAI(client).motivate_trader
    else:
        print("⚠️ No Gemini API key or OPEN_API_KEY found. Skipping Gemini client initialization.")
except Exception as e:  # noqa: BLE001
    print(f"❌ Error initializing Gemini client: {e}")
