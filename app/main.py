import os
import time
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from dataclasses import dataclass
from typing import List
from urllib.parse import urlparse
from dotenv import load_dotenv

from app.config import load_config, QueryCfg, RouteCfg
from app.state_store import StateStore
from app.ebay_client import EbayClient
from app.discord_client import DiscordWebhookClient
from app.scheduler import QueryScheduler

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
DISCORD_POST_DELAY_SECONDS = float(os.getenv("DISCORD_POST_DELAY_SECONDS", "0.4"))
DISCORD_MAX_POSTS_PER_RUN = int(os.getenv("DISCORD_MAX_POSTS_PER_RUN", "8"))
DISCORD_MAX_RETRIES = int(os.getenv("DISCORD_MAX_RETRIES", "3"))
EBAY_SEARCH_LIMIT = int(os.getenv("EBAY_SEARCH_LIMIT", "30"))

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

log = logging.getLogger("main")


@dataclass
class RouteRuntime:
    route_key: str
    route_name: str
    webhook_url: str
    title_must_contain_any: List[str] | None = None
    title_must_not_contain_any: List[str] | None = None
    price_min: float | None = None
    price_max: float | None = None


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        return


def start_health_server_if_needed() -> None:
    port_raw = os.getenv("PORT", "").strip()
    if not port_raw:
        return

    try:
        port = int(port_raw)
    except ValueError:
        log.warning("Invalid PORT value: %r", port_raw)
        return

    def _serve():
        server = HTTPServer(("0.0.0.0", port), _HealthHandler)
        log.info("Health server listening on port %s", port)
        server.serve_forever()

    thread = threading.Thread(target=_serve, name="health-server", daemon=True)
    thread.start()


def _is_valid_http_url(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def resolve_discord_webhook(config_webhook: str) -> str:
    """Resolve webhook URL from config with env fallback and strict validation."""
    env_webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    cfg_webhook = (config_webhook or "").strip()

    is_missing_or_placeholder = (
        not cfg_webhook
        or cfg_webhook == "your_hook_url"
        or (cfg_webhook.startswith("${") and cfg_webhook.endswith("}"))
    )

    resolved = env_webhook if is_missing_or_placeholder and env_webhook else cfg_webhook

    if not _is_valid_http_url(resolved):
        raise ValueError(
            "Discord webhook non valido. Imposta un URL https:// valido in "
            "queries[].discord.webhook_url oppure nella env DISCORD_WEBHOOK_URL."
        )

    return resolved


def _to_float(value) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def get_shipping_cost(item: dict) -> float:
    opts = item.get("shippingOptions") or []
    if not opts:
        return 0.0
    ship_cost = (opts[0] or {}).get("shippingCost") or {}
    return _to_float(ship_cost.get("value"))


def get_item_price(item: dict) -> float:
    price = item.get("price") or {}
    return _to_float(price.get("value"))


def total_cost(item: dict) -> float:
    return get_item_price(item) + get_shipping_cost(item)


def build_embed(item: dict, query_name: str) -> dict:
    title = (item.get("title") or "Senza titolo")[:256]

    price = item.get("price") or {}
    price_val = price.get("value", "?")
    price_cur = price.get("currency", "")
    price_str = f"{price_val} {price_cur}".strip()

    shipping_str = "0.00"
    ship_val = 0.0
    ship_cur = price_cur

    shipping_opts = item.get("shippingOptions") or []
    if shipping_opts:
        ship_cost = (shipping_opts[0] or {}).get("shippingCost") or {}
        ship_val = _to_float(ship_cost.get("value"))
        ship_cur = ship_cost.get("currency", ship_cur)
        shipping_str = f"{ship_cost.get('value','0.00')} {ship_cur}".strip()

    item_val = _to_float(price.get("value"))
    tot_val = item_val + ship_val
    total_str = f"{tot_val:.2f} {ship_cur}".strip()

    url = item.get("itemWebUrl")

    embed = {
        "title": title,
        "url": url,
        "description": (
            f"🔎 **Query:** {query_name}\n"
            f"💰 **Prezzo:** {price_str}\n"
            f"📦 **Spedizione:** {shipping_str}\n"
            f"🧾 **Totale:** **{total_str}**"
        )[:4096],
    }

    created = item.get("itemCreationDate")
    if created:
        embed["timestamp"] = created

    img = (item.get("image") or {}).get("imageUrl")
    if img:
        embed["image"] = {"url": img}

    return embed


def title_passes_filters(title: str, must_any=None, must_not=None) -> bool:
    t = (title or "").lower()

    if must_any:
        must_any_l = [x.lower() for x in must_any]
        if not any(x in t for x in must_any_l):
            return False

    if must_not:
        must_not_l = [x.lower() for x in must_not]
        if any(x in t for x in must_not_l):
            return False

    return True


def route_passes_filters(item: dict, route: RouteRuntime) -> bool:
    title = item.get("title", "")
    if not title_passes_filters(title, route.title_must_contain_any, route.title_must_not_contain_any):
        return False

    amount = total_cost(item)
    if route.price_min is not None and amount < route.price_min:
        return False
    if route.price_max is not None and amount > route.price_max:
        return False

    return True


def _build_runtime_routes(query: QueryCfg) -> list[RouteRuntime]:
    runtime_routes: list[RouteRuntime] = []

    if query.routes:
        for r in query.routes:
            runtime_routes.append(RouteRuntime(
                route_key=f"{query.name}::{r.name}",
                route_name=r.name,
                webhook_url=resolve_discord_webhook(r.webhook_url),
                title_must_contain_any=r.title_must_contain_any,
                title_must_not_contain_any=r.title_must_not_contain_any,
                price_min=r.price_min,
                price_max=r.price_max,
            ))
        return runtime_routes

    config_webhook = query.discord.webhook_url if query.discord else ""
    runtime_routes.append(RouteRuntime(
        route_key=f"{query.name}::default",
        route_name="default",
        webhook_url=resolve_discord_webhook(config_webhook),
    ))
    return runtime_routes


def make_runner(cfg_query: QueryCfg, ebay: EbayClient, store: StateStore):
    routes = _build_runtime_routes(cfg_query)
    route_clients = {
        r.route_key: DiscordWebhookClient(r.webhook_url, max_retries=DISCORD_MAX_RETRIES)
        for r in routes
    }
    qlog = logging.getLogger(f"job.{cfg_query.name}")

    def run():
        qlog.info("RUN start (keywords=%r, interval=%ss)", cfg_query.keywords, cfg_query.interval_seconds)
        try:
            items = ebay.search_items(
                keywords=cfg_query.keywords,
                price_min=cfg_query.price_min,
                price_max=cfg_query.price_max,
                currency=cfg_query.currency,
                delivery_country=cfg_query.delivery_country,
                sort=cfg_query.sort,
                limit=EBAY_SEARCH_LIMIT,
            )
            items = sorted(items, key=total_cost, reverse=True)

            qlog.info("eBay returned %d items", len(items))

            now = int(time.time())
            posted_count = 0
            skipped_dup = 0

            for it in items:
                item_id = it.get("itemId")

                if it.get("itemGroupType") or it.get("itemGroupId") or it.get("itemGroupHref"):
                    qlog.debug("Skipping variant/group listing: itemId=%s itemGroupType=%s",
                               it.get("itemId"), it.get("itemGroupType"))
                    continue

                title = it.get("title", "")
                if not title_passes_filters(
                    title,
                    must_any=cfg_query.title_must_contain_any,
                    must_not=cfg_query.title_must_not_contain_any,
                ):
                    qlog.debug("Filtered out by query title rules: %r", title)
                    continue

                if not item_id:
                    qlog.debug("Skipping item without itemId: %s", it)
                    continue

                buy_url = it.get("itemWebUrl")
                if not buy_url:
                    qlog.debug("Skipping item without itemWebUrl itemId=%s", item_id)
                    continue

                for route in routes:
                    if not route_passes_filters(it, route):
                        continue

                    if store.was_posted(route.route_key, item_id):
                        skipped_dup += 1
                        qlog.debug("Duplicate for route=%s itemId=%s", route.route_name, item_id)
                        continue

                    embed = build_embed(it, f"{cfg_query.name} / {route.route_name}")
                    qlog.info("Posting route=%s itemId=%s title=%r", route.route_name, item_id, title)

                    try:
                        route_clients[route.route_key].post_item(embed=embed, buy_url=buy_url, chrome_url=buy_url)
                    except Exception:
                        qlog.exception("Failed to post route=%s itemId=%s", route.route_name, item_id)
                        continue

                    store.mark_posted(route.route_key, item_id, now)
                    posted_count += 1

                    if posted_count >= DISCORD_MAX_POSTS_PER_RUN:
                        qlog.info("Reached per-run post cap (%s). Stopping current run.", DISCORD_MAX_POSTS_PER_RUN)
                        qlog.info("RUN end (posted=%d, duplicates=%d)", posted_count, skipped_dup)
                        return

                    if DISCORD_POST_DELAY_SECONDS > 0:
                        time.sleep(DISCORD_POST_DELAY_SECONDS)

            qlog.info("RUN end (posted=%d, duplicates=%d)", posted_count, skipped_dup)

        except Exception:
            qlog.exception("RUN failed")

    return run


def main():
    log.info("Starting ebay-discord-watcher (LOG_LEVEL=%s)", LOG_LEVEL)

    loaded = load_dotenv()
    log.info("load_dotenv() -> %s", loaded)

    log.info("ENV EBAY_CLIENT_ID present? %s", "EBAY_CLIENT_ID" in os.environ)
    log.info("ENV EBAY_CLIENT_SECRET present? %s", "EBAY_CLIENT_SECRET" in os.environ)
    log.info("ENV EBAY_SCOPE present? %s", "EBAY_SCOPE" in os.environ)

    cfg_path = os.getenv("CONFIG_PATH", "config.yaml")
    cfg = load_config(cfg_path)
    log.info("Loaded config from %s: %d queries", cfg_path, len(cfg.queries))

    store_path = cfg.storage.get("sqlite_path", "./posted_items.sqlite")
    log.info("State store sqlite_path=%s", store_path)
    store = StateStore(store_path)

    ebay = EbayClient(
        base_url=cfg.ebay.get("base_url", "https://api.ebay.com"),
        marketplace_id=cfg.ebay.get("marketplace_id", "EBAY_IT"),
        client_id=os.environ["EBAY_CLIENT_ID"],
        client_secret=os.environ["EBAY_CLIENT_SECRET"],
        scope=os.environ.get("EBAY_SCOPE", "https://api.ebay.com/oauth/api_scope"),
    )
    log.info("EbayClient initialized (base_url=%s marketplace=%s)", ebay.base_url, ebay.marketplace_id)

    sched = QueryScheduler()

    for q in cfg.queries:
        route_count = len(q.routes or []) if q.routes else 1
        log.info(
            "Config query: name=%r enabled=%s interval=%ss routes=%d",
            q.name, q.enabled, q.interval_seconds, route_count
        )
        if not q.enabled:
            continue
        job_id = f"query::{q.name}"
        sched.add_job(make_runner(q, ebay, store), seconds=q.interval_seconds, job_id=job_id)
        log.info("Scheduled job_id=%s every %ss", job_id, q.interval_seconds)

    start_health_server_if_needed()

    sched.start()
    log.info("Scheduler started. Ctrl+C to stop.")
    sched.block_forever()


if __name__ == "__main__":
    main()
