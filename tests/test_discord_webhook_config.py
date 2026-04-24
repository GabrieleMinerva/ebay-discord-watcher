import os
import unittest
from unittest.mock import patch

from app.main import resolve_discord_webhook


class DiscordWebhookConfigTests(unittest.TestCase):
    def test_uses_config_webhook_when_valid(self):
        with patch.dict(os.environ, {}, clear=True):
            url = resolve_discord_webhook("https://discord.com/api/webhooks/abc/xyz")
        self.assertEqual(url, "https://discord.com/api/webhooks/abc/xyz")

    def test_fallback_to_env_when_config_has_placeholder_value(self):
        with patch.dict(os.environ, {"DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/env/value"}, clear=True):
            url = resolve_discord_webhook("your_hook_url")
        self.assertEqual(url, "https://discord.com/api/webhooks/env/value")

    def test_raises_on_invalid_webhook_without_env(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                resolve_discord_webhook("your_hook_url")


if __name__ == "__main__":
    unittest.main()
