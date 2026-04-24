import time
import requests


class DiscordWebhookClient:
    def __init__(self, webhook_url: str, max_retries: int = 3):
        self.webhook_url = webhook_url
        self.max_retries = max(0, int(max_retries))

    def post_item(self, embed: dict, buy_url: str, chrome_url: str = None) -> None:
        payload = {
            "embeds": [embed],
            "components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 2,
                            "style": 5,
                            "label": "🛒 Compra Ora",
                            "url": buy_url
                        },
                        {
                            "type": 2,
                            "style": 5,
                            "label": "🌐 Vedi su Chrome",
                            "url": chrome_url or buy_url
                        }
                    ]
                }
            ]
        }

        attempts = self.max_retries + 1
        for attempt in range(attempts):
            r = requests.post(self.webhook_url, json=payload, timeout=30)

            if r.status_code in (200, 204):
                return

            if r.status_code == 429 and attempt < attempts - 1:
                retry_after = 1.0
                try:
                    js = r.json()
                    retry_after = float(js.get("retry_after", 1.0))
                except Exception:
                    pass
                time.sleep(max(retry_after, 0.1))
                continue

            raise Exception(f"Discord error {r.status_code}: {r.text}")
