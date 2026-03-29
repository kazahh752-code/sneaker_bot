import asyncio
import logging
import threading
from telegram import Bot
from telegram.error import TelegramError

from database import Database
from search import run_search, format_item
from config import CHECK_INTERVAL_HOURS, BRANDS

logger = logging.getLogger(__name__)


async def check_and_notify(bot: Bot, db: Database):
    subscribers = db.get_all_subscribers()
    if not subscribers:
        return

    logger.info(f"Scheduled check for {len(subscribers)} subscribers...")
    db.cleanup_old(days=14)

    for user in subscribers:
        user_id = user["id"]
        max_price = user["max_price"]
        custom = user.get("custom_query") or ""

        query_list = [custom] if custom else BRANDS

        try:
            items = await run_search(
                query_list=query_list,
                sizes=["44.5", "45", "45.5"],
                max_price=max_price,
                use_wb=True,
                use_ym=True,
            )

            new_items = [i for i in items if not db.is_seen(user_id, i["id"])]
            if not new_items:
                continue

            await bot.send_message(
                chat_id=user_id,
                text=f"🆕 <b>Найдено {len(new_items)} новых предложений!</b>",
                parse_mode="HTML"
            )

            for item in new_items[:15]:
                db.mark_seen(user_id, item["id"])
                await bot.send_message(
                    chat_id=user_id,
                    text=format_item(item),
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
                await asyncio.sleep(0.4)

            if len(new_items) > 15:
                await bot.send_message(
                    chat_id=user_id,
                    text=f"...и ещё <b>{len(new_items) - 15}</b>. Нажми «Поиск везде» для полного списка.",
                    parse_mode="HTML"
                )

        except TelegramError as e:
            logger.error(f"Send error to {user_id}: {e}")
        except Exception as e:
            logger.error(f"Check error for {user_id}: {e}")

        await asyncio.sleep(2)


def start_scheduler(bot: Bot, db: Database, loop: asyncio.AbstractEventLoop):
    async def _loop():
        while True:
            await check_and_notify(bot, db)
            await asyncio.sleep(CHECK_INTERVAL_HOURS * 3600)

    def _run():
        asyncio.run_coroutine_threadsafe(_loop(), loop)

    threading.Thread(target=_run, daemon=True).start()
    logger.info(f"Scheduler started. Interval: {CHECK_INTERVAL_HOURS}h")
