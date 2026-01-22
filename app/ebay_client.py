import time
import logging
import requests
from typing import Any, Dict, List, Optional

log = logging.getLogger("ebay")

class EbayClient:
    def __init__(
        self,
        base_url: str,
        marketplace_id: str,
        client_id: str,
        client_secret: str,
        scope: str
    ):
        self.base_url = base_url.rstrip("/")
        self.marketplace_id = marketplace_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self._token: Optional[str] = None
        self._token_exp: int = 0

    # ---- OAuth Token ----
    def _get_token(self) -> str:
        now = int(time.time())
        if self._token and now < self._token_exp - 60:
            return self._token

        url = f"{self.base_url}/identity/v1/oauth2/token"
        data = {"grant_type": "client_credentials", "scope": self.scope}

        log.info("Requesting OAuth token from eBay...")
        r = requests.post(url, data=data, auth=(self.client_id, self.client_secret), timeout=30)

        if not r.ok:
            log.error("Token request failed: %s %s", r.status_code, r.text)
            r.raise_for_status()

        js = r.json()
        self._token = js["access_token"]
        self._token_exp = now + int(js.get("expires_in", 7200))

        log.info("OAuth token obtained (expires in %ss)", js.get("expires_in", 7200))
        return self._token

    # ---- Search Items ----
    def search_items(
        self,
        keywords: str,
        category_id: Optional[str] = None,
        condition_ids: Optional[List[int]] = None,
        price_min: Optional[float] = None,
        price_max: Optional[float] = None,
        currency: str = "EUR",
        location_country: Optional[str] = None,   # itemLocationCountry (se vuoi limitarlo)
        delivery_country: Optional[str] = None,   # deliveryCountry (spedizione verso)
        sort: Optional[str] = None,               # price / newlyListed
        limit: int = 25,
    ) -> List[Dict[str, Any]]:

        token = self._get_token()

        url = f"{self.base_url}/buy/browse/v1/item_summary/search"

        params: Dict[str, Any] = {
            "q": keywords,
            "limit": min(max(limit, 1), 200),
        }

        # ---- ORDINAMENTO LATO EBAY ----
        if sort:
            params["sort"] = sort
            log.info("Sorting via eBay: %s", sort)

        # ---- FILTRI ----
        filters = []

        if category_id:
            filters.append(f"categoryIds:{{{category_id}}}")

        if condition_ids:
            filters.append("conditionIds:{" + "|".join(str(x) for x in condition_ids) + "}")

        if price_min is not None or price_max is not None:
            lo = "" if price_min is None else price_min
            hi = "" if price_max is None else price_max
            filters.append(f"price:[{lo}..{hi}],priceCurrency:{currency}")

        # venditori localizzati in un paese specifico (opzionale)
        if location_country:
            filters.append(f"itemLocationCountry:{location_country}")

        # spedizione verso paese (worldwide seller ok)
        if delivery_country:
            filters.append(f"deliveryCountry:{delivery_country}")

        if filters:
            params["filter"] = ",".join(filters)

        headers = {
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": self.marketplace_id,
        }

        log.info("Calling eBay search API")
        log.debug("Params: %s", params)

        r = requests.get(url, params=params, headers=headers, timeout=30)

        if not r.ok:
            log.error("Search failed: %s %s", r.status_code, r.text)
            r.raise_for_status()

        js = r.json()
        items = js.get("itemSummaries", [])

        log.info("eBay returned %d items", len(items))
        return items
