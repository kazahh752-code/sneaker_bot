import logging
import httpx
from config import YANDEX_MARKET_TOKEN, YANDEX_CAMPAIGN_ID

logger = logging.getLogger(__name__)

# Яндекс.Маркет — поиск через партнёрский API
# Документация: https://yandex.ru/dev/market/partner-dsbs/doc/ru/
YM_SEARCH_URL = "https://api.partner.market.yandex.ru/v2/models"
YM_SEARCH_URL_V1 = "https://api.partner.market.yandex.ru/models"

# Fallback: публичный поиск через мобильное API Яндекса (без токена)
YM_PUBLIC_URL = "https://market-search.yandex.ru/search"


async def fetch_yandex_market(query: str, size: str, max_price: int) -> list[dict]:
    """
    Пробуем сначала через партнёрский API (если есть токен),
    затем через публичный поиск.
    """
    if YANDEX_MARKET_TOKEN and YANDEX_CAMPAIGN_ID:
        results = await _fetch_partner_api(query, size, max_price)
        if results:
            return results

    # Публичный fallback
    return await _fetch_public(query, size, max_price)


async def _fetch_partner_api(query: str, size: str, max_price: int) -> list[dict]:
    headers = {
        "Authorization": f"Bearer {YANDEX_MARKET_TOKEN}",
        "Content-Type": "application/json",
    }
    params = {
        "query": f"{query} кроссовки беговые размер {size}",
        "maxPrice": max_price,
        "count": 30,
        "sort": "PRICE",
    }
    try:
        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            resp = await client.get(YM_SEARCH_URL_V1, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"YM partner API error: {e}")
        return []

    results = []
    for item in data.get("models", []) or data.get("items", []):
        try:
            price_info = item.get("prices") or {}
            price = int(price_info.get("min") or price_info.get("avg") or 0)
            if price == 0 or price > max_price:
                continue

            item_id = str(item.get("id", ""))
            results.append({
                "id": f"ym_{item_id}_{size}",
                "source": "yandex",
                "brand": item.get("vendorName", ""),
                "name": item.get("name", ""),
                "size": size,
                "price": price,
                "old_price": None,
                "discount": None,
                "rating": str(item.get("rating", "")),
                "url": f"https://market.yandex.ru/product/{item_id}",
            })
        except Exception:
            continue
    return results


async def _fetch_public(query: str, size: str, max_price: int) -> list[dict]:
    """
    Публичный поиск по Яндекс.Маркету через мобильный API.
    Работает без токена, но менее стабильный.
    """
    params = {
        "text": f"{query} кроссовки беговые размер {size}",
        "priceTo": max_price,
        "hid": 7812201,  # категория «Кроссовки»
        "how": "aprice",  # сортировка по цене
        "glfilter": f"26417735:{size}",  # фильтр размера (EU)
        "numdoc": 24,
        "page": 1,
        "rearr-factors": "market_new_cpm_iterator=4",
    }
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/112.0.0.0 Mobile Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*",
        "Referer": "https://market.yandex.ru/",
    }

    try:
        async with httpx.AsyncClient(
            timeout=15, headers=headers, follow_redirects=True
        ) as client:
            resp = await client.get(
                "https://market.yandex.ru/api/search", params=params
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"YM public fetch error {query} {size}: {e}")
        return []

    results = []
    items = (
        data.get("results", []) or
        data.get("items", []) or
        data.get("searchResult", {}).get("items", [])
    )

    for item in items[:20]:
        try:
            # Nested price
            prices = item.get("prices") or item.get("price") or {}
            if isinstance(prices, dict):
                price = int(prices.get("value") or prices.get("min") or prices.get("avg") or 0)
                old_price = int(prices.get("base") or 0) or None
            else:
                price = int(str(prices).replace(" ", "") or 0)
                old_price = None

            if price == 0 or price > max_price:
                continue

            discount = None
            if old_price and old_price > price:
                discount = round((1 - price / old_price) * 100)

            item_id = str(item.get("id") or item.get("modelId") or "")
            name = item.get("name") or item.get("title") or ""
            brand = item.get("brand") or item.get("vendor") or ""
            rating = item.get("rating") or item.get("score")
            reviews = item.get("reviewCount") or item.get("opinions")

            url = item.get("url") or f"https://market.yandex.ru/product/{item_id}"
            if url.startswith("/"):
                url = "https://market.yandex.ru" + url

            results.append({
                "id": f"ym_{item_id}_{size}",
                "source": "yandex",
                "brand": brand,
                "name": name,
                "size": size,
                "price": price,
                "old_price": old_price,
                "discount": discount,
                "rating": f"{rating} ({reviews} отз.)" if rating and reviews else str(rating) if rating else None,
                "url": url,
            })
        except Exception as e:
            logger.debug(f"YM item parse: {e}")
            continue

    return results
  
