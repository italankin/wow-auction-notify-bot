import concurrent.futures
import datetime
import logging

from telegram import Update, ChatAction
from telegram.constants import PARSEMODE_MARKDOWN_V2
from telegram.ext import Dispatcher, CallbackContext, CommandHandler

from bot_context import BotContext
from model.notification import Notification
from utils import to_human_price, wowhead_link

logger = logging.getLogger(__name__)
executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def register(dispatcher: Dispatcher):
    dispatcher.job_queue.run_repeating(
        _callback,
        interval=datetime.timedelta(minutes=BotContext.get().bot_env.update_interval))
    dispatcher.add_handler(CommandHandler("checknow", _check_now))


def _callback(context: CallbackContext):
    db = BotContext.get().database
    by_realms = {}
    for notification in db.get_notifications():
        lst = by_realms.setdefault(notification.connected_realm_id, [])
        lst.append(notification)
    for realm_id, notifications in by_realms.items():
        executor.submit(_check_and_notify, context, realm_id, notifications)


def _check_now(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    user = BotContext.get().database.get_user(user_id)
    if user and user.level == 1:
        context.bot.send_chat_action(chat_id=update.effective_message.chat_id, action=ChatAction.TYPING)
        _callback(context)


def _check_and_notify(context: CallbackContext, connected_realm_id: int, notifications: list[Notification]):
    api = BotContext.get().wow_game_api
    db = BotContext.get().database
    item_names = _get_item_names(notifications)
    realm_name = db.get_connected_realm_by_id(connected_realm_id).name
    auctions = api.auctions(connected_realm_id, [n.item_id for n in notifications])
    sent_notifications = 0
    for notification in notifications:
        item_auctions = auctions[notification.item_id]
        if not item_auctions:
            continue
        qty_under_min = 0
        price_under_min = 0
        for lot in item_auctions.lots:
            if lot.price <= notification.price:
                qty_under_min += lot.qty
                price_under_min += lot.price * lot.qty
        if qty_under_min >= notification.min_qty:
            avg_price = int(price_under_min / qty_under_min)
            user = db.get_user_by_id(notification.user_id)
            price = to_human_price(avg_price).replace('.', '\\.')
            item = wowhead_link(notification.item_id, item_names[notification.item_id])
            text = f"{item}: {qty_under_min} lots available on *{realm_name}* with average price of {price}"
            context.bot.send_message(
                user.telegram_id,
                text,
                parse_mode=PARSEMODE_MARKDOWN_V2,
                disable_web_page_preview=True
            )
            sent_notifications += 1
    logger.info(f"sent {sent_notifications} notifications")


def _get_item_names(notifications: list[Notification]) -> dict[int, str]:
    items_ids = [n.item_id for n in notifications]
    result = {}
    items = BotContext.get().database.get_items(items_ids)
    for item in items:
        result[item.item_id] = item.name
    return result
