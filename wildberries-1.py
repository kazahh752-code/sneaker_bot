import asyncio
import logging
import httpx
from config import HEADERS_WB, WB_REQUEST_DELAY

logger = logging.getLogger(__name__)

WB_SEARCH_URL = "https://search.wb.ru/exactmatch/ru/common/v5/search"


async def fetch_wb(query: str, size: str, max_price: int) -> list[dict]:
    """
    query — может быть брендом ("Nike") или конкретной моделью ("Nike Pegasus 40")
    """
    params = {
        "query": f"{query} кроссовки беговые",
        "resultset": "catalog",
        "limit": 50,
        "sort": "priceup",
        "page": 1,
        "priceU": f"100;{max_price * 100}",
        "spp": 30,
        "suppressSpellcheck": "false",
    }

    try:
        # Задержка перед каждым запросом — избегаем 429
        await asyncio.sleep(WB_REQUEST_DELAY)

        async with httpx.AsyncClient(timeout=20, headers=HEADERS_WB) as client:
            resp = await client.get(WB_SEARCH_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        logger.warning(f"WB {query} {size}: HTTP {e.response.status_code}")
        return []
    except Exception as e:
        logger.error(f"WB fetch error {query} {size}: {e}")
        return []

    products = data.get("data", {}).get("products", [])
    results = []

    for p in products:
        try:
            price_raw = p.get("salePriceU") or p.get("priceU", 0)
            price = price_raw // 100
            if price == 0 or price > max_price:
                continue

            # Проверяем наличие нужного размера
            sizes_data = p.get("sizes", [])
            size_ok = False
            for s in sizes_data:
                orig = str(s.get("origName", "") or s.get("name", ""))
                if size.replace(".", ",") in orig or size in orig:
                    # Проверяем что размер в наличии
                    stocks = s.get("stocks", [])
                    if stocks:
                        size_ok = True
                        break
            if sizes_data and not size_ok:
                continue

            old_raw = p.get("priceU", 0)
            old_price = old_raw // 100 if old_raw and old_raw > price_raw else None
            discount = p.get("sale") or p.get("discount")

            item_id = str(p.get("id", ""))
            brand = p.get("brand", "")
            name = p.get("name", "")
            rating = p.get("rating")
            feedbacks = p.get("feedbacks", 0)

            results.append({
                "id": f"wb_{item_id}_{size}",
                "source": "wb",
                "brand": brand,
                "name": name,
                "size": size,
                "price": price,
                "old_price": old_price,
                "discount": discount,
                "rating": f"{rating} ({feedbacks} отз.)" if rating else None,
                "url": f"https://www.wildberries.ru/catalog/{item_id}/detail.aspx",
            })

        except Exception as e:
            logger.debug(f"WB item parse: {e}")
            continue

    return results
