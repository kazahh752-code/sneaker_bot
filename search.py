import asyncio
import logging
from config import BRANDS, SIZES

logger = logging.getLogger(__name__)


def format_item(item: dict) -> str:
    emoji = {"wb": "🟣", "yandex": "🟡"}.get(item["source"], "🛒")
    price_line = f"💰 <b>{item['price']:,} ₽</b>".replace(",", " ")
    if item.get("old_price") and item["old_price"] > item["price"]:
        price_line += f"  <s>{item['old_price']:,} ₽</s>".replace(",", " ")
    if item.get("discount"):
        price_line += f"  🔥 -{item['discount']}%"
    lines = [
        f"{emoji} <b>{item['brand']} {item['name']}</b>",
        f"📐 Размер: {item['size']}",
        price_line,
    ]
    if item.get("rating"):
        lines.append(f"⭐️ {item['rating']}")
    lines.append(f"🔗 <a href=\"{item['url']}\">Открыть</a>")
    return "\n".join(lines)


async def run_search(
    query_list: list[str],
    sizes: list[str],
    max_price: int,
    use_wb: bool = True,
    use_ym: bool = True,
) -> list[dict]:
    """
    query_list — список запросов (бренды или конкретные модели)
    Возвращает дедуплицированный отсортированный список товаров.
    """
    from parsers.wildberries import fetch_wb
    from parsers.yandex_market import fetch_yandex_market

    all_items = []

    for query in query_list:
        for size in sizes:
            if use_wb:
                try:
                    items = await fetch_wb(query, size, max_price)
                    all_items.extend(items)
                    logger.info(f"WB {query} {size}: {len(items)} items")
                except Exception as e:
                    logger.error(f"WB error {query} {size}: {e}")

            if use_ym:
                try:
                    items = await fetch_yandex_market(query, size, max_price)
                    all_items.extend(items)
                    logger.info(f"YM {query} {size}: {len(items)} items")
                except Exception as e:
                    logger.error(f"YM error {query} {size}: {e}")

            # Пауза между серией запросов
            await asyncio.sleep(1)

    # Дедупликация по ID
    seen = set()
    unique = []
    for item in all_items:
        if item["id"] not in seen:
            seen.add(item["id"])
            unique.append(item)

    unique.sort(key=lambda x: x["price"])
    return unique
