import os
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from app.config import load_config
from app.main import RouteRuntime, route_passes_filters


class RoutingTests(unittest.TestCase):
    def test_load_config_supports_routes_without_legacy_discord(self):
        raw = textwrap.dedent(
            """
            ebay:
              marketplace_id: EBAY_IT
              base_url: https://api.ebay.com
            storage:
              sqlite_path: ./tmp.sqlite
            queries:
              - name: q1
                enabled: true
                interval_seconds: 30
                keywords: game boy
                routes:
                  - name: general
                    webhook_url: ${DISCORD_WEBHOOK_URL}
                  - name: deals
                    webhook_url: ${DISCORD_WEBHOOK_URL_DEALS}
                    price_max: 50
            """
        )

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(raw)
            path = f.name

        with patch.dict(os.environ, {
            "DISCORD_WEBHOOK_URL": "https://discord.com/api/webhooks/a/b",
            "DISCORD_WEBHOOK_URL_DEALS": "https://discord.com/api/webhooks/c/d",
        }, clear=True):
            cfg = load_config(path)

        self.assertEqual(len(cfg.queries), 1)
        self.assertEqual(len(cfg.queries[0].routes), 2)
        self.assertEqual(cfg.queries[0].routes[1].price_max, 50)

    def test_route_filters_apply_on_title_and_price(self):
        route = RouteRuntime(
            route_key="q::deals",
            route_name="deals",
            webhook_url="https://discord.com/api/webhooks/a/b",
            title_must_not_contain_any=["difetti"],
            price_max=80,
        )

        ok_item = {
            "title": "Nintendo Game Boy Color",
            "price": {"value": "70"},
            "shippingOptions": [{"shippingCost": {"value": "5", "currency": "EUR"}}],
        }
        bad_title_item = {
            "title": "Game Boy con difetti",
            "price": {"value": "30"},
            "shippingOptions": [{"shippingCost": {"value": "5", "currency": "EUR"}}],
        }
        bad_price_item = {
            "title": "Game Boy perfetto",
            "price": {"value": "90"},
            "shippingOptions": [{"shippingCost": {"value": "2", "currency": "EUR"}}],
        }

        self.assertTrue(route_passes_filters(ok_item, route))
        self.assertFalse(route_passes_filters(bad_title_item, route))
        self.assertFalse(route_passes_filters(bad_price_item, route))


if __name__ == "__main__":
    unittest.main()
