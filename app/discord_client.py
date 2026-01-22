import logging
import requests
from typing import Any, Dict, Optional

log = logging.getLogger("discord")

class DiscordWebhookClient:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def post_item(self, embed: Dict[str, Any], buy_url: str, chrome_url: Optional[str] = None) -> None:
        components = [
            {
                "type": 1,
                "components": [
                    {"type": 2, "style": 5, "label": "Compra Ora", "url": buy_url},
                    {"type": 2, "style": 5, "label": "Vedi su Chrome", "url": chrome_url or buy_url},
                ],
            }
        ]

        payload = {"embeds": [embed], "components": components}

        log.info("POST Discord webhook (title=%r)", embed.get("title"))
        r = requests.post(self.webhook_url, json=payload, timeout=30)

        # Rate limit info utile
        if r.status_code == 429:
            log.warning("Discord rate limited: %s", r.text)
            r.raise_for_status()

        if not r.ok:
            log.error("Discord webhook failed: %s %s", r.status_code, r.text)
            r.raise_for_status()

        log.debug("Discord webhook OK (%s)", r.status_code)
