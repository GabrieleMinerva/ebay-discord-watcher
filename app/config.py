from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import yaml

@dataclass
class DiscordCfg:
    webhook_url: str

@dataclass
class QueryCfg:
    name: str
    enabled: bool
    interval_seconds: int
    keywords: str
    category_id: Optional[str] = None
    condition_ids: Optional[List[int]] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    currency: str = "EUR"
    location_country: Optional[str] = None
    discord: DiscordCfg = None
    delivery_country: Optional[str] = None
    sort: Optional[str] = None
    title_must_contain_any: Optional[List[str]] = None
    title_must_not_contain_any: Optional[List[str]] = None

@dataclass
class AppCfg:
    ebay: Dict[str, Any]
    storage: Dict[str, Any]
    queries: List[QueryCfg]

def load_config(path: str) -> AppCfg:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    queries = []
    for q in raw["queries"]:
        queries.append(QueryCfg(
            name=q["name"],
            enabled=q.get("enabled", True),
            interval_seconds=q["interval_seconds"],
            keywords=q["keywords"],
            category_id=q.get("category_id"),
            condition_ids=q.get("condition_ids"),
            price_min=q.get("price_min"),
            price_max=q.get("price_max"),
            currency=q.get("currency", "EUR"),
            location_country=q.get("location_country"),
            discord=DiscordCfg(webhook_url=q["discord"]["webhook_url"]),
            sort = q.get("sort"),
            delivery_country = q.get("delivery_country"),
            title_must_contain_any=q.get("title_must_contain_any"),
            title_must_not_contain_any=q.get("title_must_not_contain_any")
        ))

    return AppCfg(
        ebay=raw["ebay"],
        storage=raw["storage"],
        queries=queries
    )
