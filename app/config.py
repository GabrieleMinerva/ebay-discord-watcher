from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import os
import yaml


@dataclass
class DiscordCfg:
    webhook_url: str


@dataclass
class RouteCfg:
    name: str
    webhook_url: str
    title_must_contain_any: Optional[List[str]] = None
    title_must_not_contain_any: Optional[List[str]] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None


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
    discord: Optional[DiscordCfg] = None
    routes: Optional[List[RouteCfg]] = None
    delivery_country: Optional[str] = None
    sort: Optional[str] = None
    title_must_contain_any: Optional[List[str]] = None
    title_must_not_contain_any: Optional[List[str]] = None


@dataclass
class AppCfg:
    ebay: Dict[str, Any]
    storage: Dict[str, Any]
    queries: List[QueryCfg]


def _expand_env_vars(value: Any) -> Any:
    """Recursively expands ${VAR} placeholders using process environment."""
    if isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env_vars(v) for v in value]
    if isinstance(value, str):
        return os.path.expandvars(value)
    return value


def _parse_routes(raw_query: Dict[str, Any]) -> Optional[List[RouteCfg]]:
    raw_routes = raw_query.get("routes") or []
    if not raw_routes:
        return None

    routes: List[RouteCfg] = []
    for rr in raw_routes:
        routes.append(RouteCfg(
            name=rr["name"],
            webhook_url=rr["webhook_url"],
            title_must_contain_any=rr.get("title_must_contain_any"),
            title_must_not_contain_any=rr.get("title_must_not_contain_any"),
            price_min=rr.get("price_min"),
            price_max=rr.get("price_max"),
        ))
    return routes


def load_config(path: str) -> AppCfg:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    raw = _expand_env_vars(raw)

    queries = []
    for q in raw["queries"]:
        discord_raw = q.get("discord")
        routes = _parse_routes(q)

        discord_cfg = None
        if discord_raw:
            discord_cfg = DiscordCfg(webhook_url=discord_raw["webhook_url"])

        if not discord_cfg and not routes:
            raise ValueError(
                f"Query '{q.get('name', 'unknown')}' must define discord.webhook_url or at least one route"
            )

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
            discord=discord_cfg,
            routes=routes,
            sort=q.get("sort"),
            delivery_country=q.get("delivery_country"),
            title_must_contain_any=q.get("title_must_contain_any"),
            title_must_not_contain_any=q.get("title_must_not_contain_any")
        ))

    return AppCfg(
        ebay=raw["ebay"],
        storage=raw["storage"],
        queries=queries
    )
