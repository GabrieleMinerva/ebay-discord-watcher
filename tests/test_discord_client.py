import unittest
from unittest.mock import MagicMock, patch

from app.discord_client import DiscordWebhookClient


class DiscordClientTests(unittest.TestCase):
    @patch("app.discord_client.time.sleep")
    @patch("app.discord_client.requests.post")
    def test_retries_on_rate_limit_then_succeeds(self, mock_post, mock_sleep):
        rate_limited = MagicMock(status_code=429, text='{"message": "You are being rate limited."}')
        rate_limited.json.return_value = {"retry_after": 0.2}
        success = MagicMock(status_code=204, text="")

        mock_post.side_effect = [rate_limited, success]

        client = DiscordWebhookClient("https://discord.com/api/webhooks/test/test", max_retries=3)
        client.post_item(embed={"title": "x"}, buy_url="https://example.com")

        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once_with(0.2)

    @patch("app.discord_client.requests.post")
    def test_raises_after_retry_budget_exhausted(self, mock_post):
        rate_limited = MagicMock(status_code=429, text='{"message": "You are being rate limited."}')
        rate_limited.json.return_value = {"retry_after": 0.1}
        mock_post.return_value = rate_limited

        client = DiscordWebhookClient("https://discord.com/api/webhooks/test/test", max_retries=1)

        with self.assertRaises(Exception):
            client.post_item(embed={"title": "x"}, buy_url="https://example.com")


if __name__ == "__main__":
    unittest.main()
