import os
import time
import logging
from dotenv import load_dotenv

from app.config import load_config, QueryCfg
from app.state_store import StateStore
from app.ebay_client import EbayClient
from app.discord_client import DiscordWebhookClient
from app.scheduler import QueryScheduler

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

log = logging.getLogger("main")

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

    # Shipping
    shipping_str = "0.00"
    ship_val = 0.0
    ship_cur = price_cur

    shipping_opts = item.get("shippingOptions") or []
    if shipping_opts:
        ship_cost = (shipping_opts[0] or {}).get("shippingCost") or {}
        ship_val = _to_float(ship_cost.get("value"))
        ship_cur = ship_cost.get("currency", ship_cur)
        shipping_str = f"{ship_cost.get('value','0.00')} {ship_cur}".strip()

    # Totale
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

    # ✅ Data/ora pubblicazione eBay (mostrata tramite timestamp embed)
    # eBay Browse API spesso fornisce itemCreationDate
    created = item.get("itemCreationDate")
    if created:
        embed["timestamp"] = created  # ISO 8601

    # ✅ Immagine grande in testa
    img = (item.get("image") or {}).get("imageUrl")
    if img:
        embed["image"] = {"url": img}

    return embed

def make_runner(cfg_query: QueryCfg, ebay: EbayClient, store: StateStore):
    discord = DiscordWebhookClient(cfg_query.discord.webhook_url)
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
                limit=100,
            )
            items = sorted(items, key=total_cost, reverse=True)

            qlog.info("eBay returned %d items", len(items))

            now = int(time.time())
            posted_count = 0
            skipped_dup = 0

            for it in items:
                item_id = it.get("itemId")

                # Scarta inserzioni "a varianti" (dropdown)
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
                    qlog.debug("Filtered out by title rules: %r", title)
                    continue

                if not item_id:
                    qlog.debug("Skipping item without itemId: %s", it)
                    continue

                if store.was_posted(cfg_query.name, item_id):
                    skipped_dup += 1
                    qlog.debug("Duplicate (already posted) itemId=%s", item_id)
                    continue

                buy_url = it.get("itemWebUrl")
                if not buy_url:
                    qlog.debug("Skipping item without itemWebUrl itemId=%s", item_id)
                    continue

                embed = build_embed(it, cfg_query.name)
                title = it.get("title", "")
                qlog.info("Posting itemId=%s title=%r", item_id, title)

                discord.post_item(embed=embed, buy_url=buy_url, chrome_url=buy_url)
                store.mark_posted(cfg_query.name, item_id, now)
                posted_count += 1

            qlog.info("RUN end (posted=%d, duplicates=%d)", posted_count, skipped_dup)

        except Exception:
            qlog.exception("RUN failed")

    return run


def main():
    log.info("Starting ebay-discord-watcher (LOG_LEVEL=%s)", LOG_LEVEL)

    # carica .env dalla working directory corrente
    loaded = load_dotenv()
    log.info("load_dotenv() -> %s", loaded)

    # log “presenza” env (non stampiamo i segreti)
    log.info("ENV EBAY_CLIENT_ID present? %s", "EBAY_CLIENT_ID" in os.environ)
    log.info("ENV EBAY_CLIENT_SECRET present? %s", "EBAY_CLIENT_SECRET" in os.environ)
    log.info("ENV EBAY_SCOPE present? %s", "EBAY_SCOPE" in os.environ)

    cfg = load_config("config.yaml")
    log.info("Loaded config: %d queries", len(cfg.queries))

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
        log.info("Config query: name=%r enabled=%s interval=%ss webhook=%s",
                 q.name, q.enabled, q.interval_seconds,
                 ("SET" if (q.discord and q.discord.webhook_url) else "MISSING"))
        if not q.enabled:
            continue
        job_id = f"query::{q.name}"
        sched.add_job(make_runner(q, ebay, store), seconds=q.interval_seconds, job_id=job_id)
        log.info("Scheduled job_id=%s every %ss", job_id, q.interval_seconds)

    sched.start()
    log.info("Scheduler started. Ctrl+C to stop.")
    sched.block_forever()

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

if __name__ == "__main__":
    main()
