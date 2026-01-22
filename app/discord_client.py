import requests


class DiscordWebhookClient:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

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

        r = requests.post(self.webhook_url, json=payload, timeout=30)

        if r.status_code in (200, 204):
            return

        raise Exception(f"Discord error {r.status_code}: {r.text}")
