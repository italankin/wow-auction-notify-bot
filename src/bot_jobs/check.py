import concurrent.futures
import datetime
import logging
import random
import threading
import time

from telegram import Update, ChatAction
from telegram.constants import PARSEMODE_MARKDOWN_V2
from telegram.ext import Dispatcher, CallbackContext, CommandHandler

from bot_context import BotContext
from model.auction import Auction
from model.notification import Notification
from utils import to_human_price, wowhead_link, sanitize_str

logger = logging.getLogger(__name__)
executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

MAX_RETRIES = 15
SLEEP_INTERVAL = 300


def register(dispatcher: Dispatcher):
    threading.Thread(name='pick-interval', target=_pick_interval, args=[dispatcher], daemon=True).start()
    dispatcher.add_handler(CommandHandler("checknow", _check_now))


def _pick_interval(dispatcher: Dispatcher):
    logger.debug('Starting _pick_interval')
    api = BotContext.get().wow_game_api
    db = BotContext.get().database
    realms = db.get_all_connected_realms()
    if len(realms) == 0:
        logger.debug('_pick_interval: no available realms')
        _schedule_job(dispatcher)
        return
    realm = random.choice(realms)
    prev_hash = None
    retries = 0
    while retries < MAX_RETRIES:
        retries += 1
        new_hash = api.with_retry(lambda: api.auctions_snapshot(realm.region, realm.connected_realm_id))
        logger.debug(f"_pick_interval: prev_hash={prev_hash} new_hash={new_hash}")
        if not new_hash:
            # no snapshot available
            continue
        if not prev_hash:
            prev_hash = new_hash
        elif prev_hash != new_hash:
            logger.debug('_pick_interval: auction data updated')
            # auction data got an update
            break
        logger.debug(f"_pick_interval: retries left: {MAX_RETRIES - retries}")
        time.sleep(SLEEP_INTERVAL)
    _schedule_job(dispatcher)


def _schedule_job(dispatcher: Dispatcher):
    logger.info('Schedule update job')
    dispatcher.job_queue.run_repeating(
        _callback,
        first=1,
        interval=datetime.timedelta(minutes=BotContext.get().bot_env.update_interval))


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
    try:
        _check_and_notify_unsafe(context, connected_realm_id, notifications)
    except Exception as e:
        logger.error(f"_check_and_notify failed: {e}", exc_info=e)


def _check_and_notify_unsafe(context: CallbackContext, connected_realm_id: int, notifications: list[Notification]):
    api = BotContext.get().wow_game_api
    db = BotContext.get().database
    item_names = _get_item_names(notifications)
    realm = db.get_connected_realm_by_id(connected_realm_id)
    item_ids = [n.item_id for n in notifications]
    auctions = api.with_retry(lambda: api.auctions(realm.region, connected_realm_id, item_ids))
    sent_notifications = 0
    for notification in notifications:
        user = db.get_user_by_id(notification.user_id)
        if not user:
            logger.warning(f"User id={notification.user_id} has active notifications, but not found in the database")
            continue
        if notification.item_id not in auctions:
            continue
        auction = auctions[notification.item_id]
        item_name = item_names[notification.item_id]
        if notification.kind == Notification.Kind.MAX_PRICE:
            sent = _check_min_qty(context, notification, auction, item_name, user.telegram_id, realm.name)
        elif notification.kind == Notification.Kind.MARKET_PRICE:
            sent = _check_market_price(context, notification, auction, item_name, user.telegram_id, realm.name)
        elif notification.kind == Notification.Kind.AVG_PRICE:
            sent = _check_average(context, notification, auction, item_name, user.telegram_id, realm.name)
        else:
            logger.warning(f"{notification.kind.value} is not supported")
            continue
        if sent:
            sent_notifications += 1
    logger.info(
        f"sent {sent_notifications}/{len(notifications)} notifications for connected_realm_id={connected_realm_id}"
    )


def _check_min_qty(
        context: CallbackContext,
        notification: Notification,
        auction: Auction,
        item_name: str,
        telegram_id: int,
        realm_name: str
) -> bool:
    qty_under_min = 0
    price_under_min = 0
    for lot in auction.lots:
        if lot.price <= notification.price:
            qty_under_min += lot.qty
            price_under_min += lot.price * lot.qty
        else:
            break
    if qty_under_min >= notification.value:
        avg_price = int(price_under_min / qty_under_min)
        price = sanitize_str(to_human_price(avg_price))
        item = wowhead_link(notification.item_id, item_name)
        realm_name_san = sanitize_str(realm_name)
        text = f"{item}: {qty_under_min} lots available on *{realm_name_san}* with average price of {price}"
        context.bot.send_message(telegram_id, text, parse_mode=PARSEMODE_MARKDOWN_V2, disable_web_page_preview=True)
        return True
    return False


def _check_market_price(
        context: CallbackContext,
        notification: Notification,
        auction: Auction,
        item_name: str,
        telegram_id: int,
        realm_name: str
) -> bool:
    min_price = None
    for lot in auction.lots:
        if lot.price <= notification.price:
            if not min_price or lot.price < min_price:
                min_price = lot.price
    if min_price:
        price = sanitize_str(to_human_price(min_price))
        item = wowhead_link(notification.item_id, item_name)
        realm_name_san = sanitize_str(realm_name)
        text = f"{item} is available on *{realm_name_san}* with minimum price of {price}"
        context.bot.send_message(telegram_id, text, parse_mode=PARSEMODE_MARKDOWN_V2, disable_web_page_preview=True)
        return True
    return False


def _check_average(
        context: CallbackContext,
        notification: Notification,
        auction: Auction,
        item_name: str,
        telegram_id: int,
        realm_name: str
) -> bool:
    avg = 0
    qty = 0
    for lot in auction.lots:
        new_avg = int(
            (avg * qty + lot.price * lot.qty) / (qty + lot.qty)
        )
        if new_avg <= notification.price:
            avg = new_avg
            qty += lot.qty
        else:
            break
    if qty >= notification.value:
        price = sanitize_str(to_human_price(avg))
        item = wowhead_link(notification.item_id, item_name)
        realm_name_san = sanitize_str(realm_name)
        text = f"{item}: {qty} lots available on *{realm_name_san}* with average price of {price}"
        context.bot.send_message(telegram_id, text, parse_mode=PARSEMODE_MARKDOWN_V2, disable_web_page_preview=True)
        return True
    return False


def _get_item_names(notifications: list[Notification]) -> dict[int, str]:
    items_ids = [n.item_id for n in notifications]
    result = {}
    items = BotContext.get().database.get_items(items_ids)
    for item in items:
        result[item.item_id] = item.name
    return result
