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


def build_embed(item: dict, query_name: str) -> dict:
    title = item.get("title", "Senza titolo")
    price = item.get("price", {})
    price_str = f'{price.get("value","?")} {price.get("currency","")}'.strip()
    item_web_url = item.get("itemWebUrl")

    img = None
    if item.get("image") and item["image"].get("imageUrl"):
        img = item["image"]["imageUrl"]

    subtitle = f"Query: {query_name} • Prezzo: {price_str}"

    embed = {
        "title": title,
        "url": item_web_url,
        "description": subtitle,
        "fields": [],
    }
    if img:
        embed["thumbnail"] = {"url": img}
    return embed


def make_runner(cfg_query: QueryCfg, ebay: EbayClient, store: StateStore):
    discord = DiscordWebhookClient(cfg_query.discord.webhook_url)
    qlog = logging.getLogger(f"job.{cfg_query.name}")

    def run():
        qlog.info("RUN start (keywords=%r, interval=%ss)", cfg_query.keywords, cfg_query.interval_seconds)
        try:
            items = ebay.search_items(
                keywords=cfg_query.keywords,
                category_id=cfg_query.category_id,
                condition_ids=cfg_query.condition_ids,
                price_min=cfg_query.price_min,
                price_max=cfg_query.price_max,
                currency=cfg_query.currency,
                location_country=cfg_query.location_country,
                limit=25,
            )
            qlog.info("eBay returned %d items", len(items))

            now = int(time.time())
            posted_count = 0
            skipped_dup = 0

            for it in items:
                item_id = it.get("itemId")
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


if __name__ == "__main__":
    main()
