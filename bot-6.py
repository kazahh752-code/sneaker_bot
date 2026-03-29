import asyncio
import logging
from pathlib import Path
from threading import Thread

from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, ConversationHandler, filters
)

from config import BOT_TOKEN, PORT, BRANDS, SIZES, DEFAULT_MAX_PRICE
from database import Database
from search import run_search, format_item

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

db = Database()
app_flask = Flask(__name__)

# Conversation states
SET_PRICE, SET_MODEL = range(2)


@app_flask.route("/")
def index():
    return "Sneaker Bot v2 is running!", 200


# ── Главное меню ──────────────────────────────────────────────────────────────

def main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    sub = db.is_subscribed(user_id)
    price = db.get_user_max_price(user_id)
    custom = db.get_custom_query(user_id)

    sub_btn = "🔔 Отписаться" if sub else "🔔 Подписаться на обновления"
    sub_cb = "unsub" if sub else "sub"

    model_label = f"🔎 Модель: {custom}" if custom else "🔎 Искать конкретную модель"

    keyboard = [
        [InlineKeyboardButton("🟣 Поиск на WB", callback_data="search_wb"),
         InlineKeyboardButton("🟡 Поиск на Яндекс", callback_data="search_ym")],
        [InlineKeyboardButton("🔍 Поиск везде", callback_data="search_all")],
        [InlineKeyboardButton(model_label, callback_data="set_model")],
        [InlineKeyboardButton(f"💰 Цена: до {price} ₽", callback_data="set_price")],
        [InlineKeyboardButton(sub_btn, callback_data=sub_cb)],
        [InlineKeyboardButton("📊 Статус", callback_data="status"),
         InlineKeyboardButton("❓ Помощь", callback_data="help")],
    ]
    return InlineKeyboardMarkup(keyboard)


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, edit=False):
    user = update.effective_user
    db.add_user(user.id, user.username or user.first_name)

    text = (
        "👟 <b>Sneaker Bot</b>\n\n"
        "Ищу беговые кроссовки на <b>Wildberries</b> и <b>Яндекс.Маркете</b>.\n\n"
        "Выбери действие:"
    )
    keyboard = main_menu_keyboard(user.id)

    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        msg = update.message or update.callback_query.message
        await msg.reply_text(text, reply_markup=keyboard, parse_mode="HTML")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update, context)


# ── Callback роутер ───────────────────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data in ("search_wb", "search_ym", "search_all"):
        await handle_search(update, context, data)
    elif data == "set_price":
        await query.edit_message_text(
            "💰 Введи максимальную цену в рублях (например: <b>5000</b>):\n\n"
            "Для отмены напиши /cancel",
            parse_mode="HTML"
        )
        return SET_PRICE
    elif data == "set_model":
        custom = db.get_custom_query(query.from_user.id)
        hint = f"\nСейчас задана модель: <b>{custom}</b>" if custom else ""
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑 Сбросить модель (искать все бренды)", callback_data="clear_model")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_menu")],
        ])
        await query.edit_message_text(
            f"🔎 <b>Поиск конкретной модели</b>{hint}\n\n"
            "Введи название модели, например:\n"
            "<code>Nike Pegasus 40</code>\n"
            "<code>ASICS Gel-Nimbus 25</code>\n"
            "<code>New Balance 1080</code>\n\n"
            "Или выбери действие:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return SET_MODEL
    elif data == "clear_model":
        db.set_custom_query(query.from_user.id, "")
        await query.answer("✅ Модель сброшена — буду искать все бренды", show_alert=True)
        await show_main_menu(update, context, edit=True)
    elif data == "sub":
        db.set_subscribed(query.from_user.id, True)
        await query.answer("✅ Подписка активирована!", show_alert=True)
        await show_main_menu(update, context, edit=True)
    elif data == "unsub":
        db.set_subscribed(query.from_user.id, False)
        await query.answer("🔕 Подписка отключена", show_alert=True)
        await show_main_menu(update, context, edit=True)
    elif data == "status":
        await show_status(update, context)
    elif data == "help":
        await show_help(update, context)
    elif data == "back_menu":
        await show_main_menu(update, context, edit=True)

    return ConversationHandler.END


# ── Поиск ─────────────────────────────────────────────────────────────────────

async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str):
    query = update.callback_query
    user_id = query.from_user.id
    max_price = db.get_user_max_price(user_id)
    custom = db.get_custom_query(user_id)

    use_wb = mode in ("search_wb", "search_all")
    use_ym = mode in ("search_ym", "search_all")

    source_label = {"search_wb": "Wildberries 🟣", "search_ym": "Яндекс.Маркет 🟡", "search_all": "всех площадках"}.get(mode, "")

    # Определяем что ищем
    if custom:
        query_list = [custom]
        search_label = f"модель <b>{custom}</b>"
    else:
        query_list = BRANDS
        search_label = "топ-10 брендов"

    await query.edit_message_text(
        f"🔍 Ищу {search_label} на {source_label}...\n"
        f"💰 Цена до <b>{max_price} ₽</b> | Размеры: {', '.join(SIZES)}\n\n"
        f"⏳ Подожди, это займёт {len(query_list) * len(SIZES) * (2 if mode == 'search_all' else 1) * 2}–{len(query_list) * len(SIZES) * (2 if mode == 'search_all' else 1) * 5} сек...",
        parse_mode="HTML"
    )

    items = await run_search(
        query_list=query_list,
        sizes=SIZES,
        max_price=max_price,
        use_wb=use_wb,
        use_ym=use_ym,
    )

    if not items:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 Изменить цену", callback_data="set_price")],
            [InlineKeyboardButton("◀️ В меню", callback_data="back_menu")],
        ])
        await query.message.reply_text(
            "😔 Ничего не найдено.\n\nПопробуй увеличить цену или сбросить модель.",
            reply_markup=keyboard
        )
    else:
        cap = min(len(items), 20)
        await query.message.reply_text(
            f"✅ Найдено <b>{len(items)}</b> вариантов. Показываю первые {cap} (дешевле всего):",
            parse_mode="HTML"
        )
        for item in items[:cap]:
            await query.message.reply_text(
                format_item(item), parse_mode="HTML", disable_web_page_preview=True
            )
            await asyncio.sleep(0.3)

    # Возвращаем меню после поиска
    keyboard = main_menu_keyboard(user_id)
    await query.message.reply_text(
        "☝️ Что дальше?", reply_markup=keyboard
    )


# ── Ввод цены и модели ────────────────────────────────────────────────────────

async def receive_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text.strip().replace(" ", "").replace("\u202f", ""))
        if not (500 <= price <= 50000):
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ Введи число от 500 до 50 000:")
        return SET_PRICE

    db.set_user_max_price(update.effective_user.id, price)
    await update.message.reply_text(
        f"✅ Максимальная цена: <b>{price:,} ₽</b>".replace(",", " "),
        parse_mode="HTML"
    )
    await show_main_menu(update, context)
    return ConversationHandler.END


async def receive_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    model = update.message.text.strip()
    if len(model) < 2:
        await update.message.reply_text("⚠️ Слишком короткий запрос. Введи название модели:")
        return SET_MODEL

    db.set_custom_query(update.effective_user.id, model)
    await update.message.reply_text(
        f"✅ Буду искать: <b>{model}</b>\n\n"
        "Теперь нажми «Поиск везде» или выбери площадку.",
        parse_mode="HTML"
    )
    await show_main_menu(update, context)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.")
    await show_main_menu(update, context)
    return ConversationHandler.END


# ── Статус и помощь ───────────────────────────────────────────────────────────

async def show_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    sub = db.is_subscribed(user_id)
    price = db.get_user_max_price(user_id)
    custom = db.get_custom_query(user_id)

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_menu")]])
    await query.edit_message_text(
        f"📊 <b>Статус</b>\n\n"
        f"🔔 Подписка: {'✅ активна' if sub else '❌ отключена'}\n"
        f"💰 Макс. цена: <b>{price:,} ₽</b>\n".replace(",", " ") +
        f"🔎 Модель: <b>{custom or 'все бренды'}</b>\n"
        f"📐 Размеры: {', '.join(SIZES)}\n"
        f"🛒 Площадки: WB + Яндекс.Маркет\n"
        f"⏰ Авто-проверка: каждые 2 часа",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_menu")]])
    await query.edit_message_text(
        "❓ <b>Помощь</b>\n\n"
        "🟣 <b>Поиск на WB</b> — только Wildberries\n"
        "🟡 <b>Поиск на Яндексе</b> — Яндекс.Маркет\n"
        "🔍 <b>Поиск везде</b> — обе площадки\n\n"
        "🔎 <b>Конкретная модель</b> — введи название,\n"
        "например: <code>ASICS Gel-Kayano 30</code>\n\n"
        "💰 <b>Цена</b> — установи лимит (по умолчанию 4000 ₽)\n\n"
        "🔔 <b>Подписка</b> — бот проверяет каждые 2 часа\n"
        "и присылает новые предложения автоматически\n\n"
        "📐 Размеры: 44.5, 45, 45.5\n"
        "🏷 Бренды: ASICS, NB, Nike, Adidas, Saucony,\n"
        "Brooks, Mizuno, Hoka, Puma, Reebok",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# ── Run ───────────────────────────────────────────────────────────────────────

def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    application = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler)],
        states={
            SET_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_price),
                CallbackQueryHandler(button_handler),
            ],
            SET_MODEL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_model),
                CallbackQueryHandler(button_handler),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
        ],
        per_message=False,
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv)

    from scheduler import start_scheduler
    start_scheduler(application.bot, db, loop)

    application.run_polling(stop_signals=None)


if __name__ == "__main__":
    Thread(target=run_bot, daemon=True).start()
    app_flask.run(host="0.0.0.0", port=PORT)
