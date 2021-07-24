import logging
import re
from typing import Optional

from telegram import Update, ChatAction, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import PARSEMODE_MARKDOWN_V2
from telegram.ext import CommandHandler, Dispatcher, CallbackContext, Filters, ConversationHandler, MessageHandler, \
    CallbackQueryHandler

from bot_context import BotContext
from db.database import Item
from model.connected_realm import ConnectedRealm
from utils import from_human_price, to_human_price, wowhead_link, sanitize_str
from wow.wow_game_api import REGIONS

logger = logging.getLogger(__name__)

MAX_USER_REALMS = 3

MIN_PRICE = 100  # 1 silver
MAX_PRICE = 2_000_000 * 10000  # 2 mil gold
MIN_QTY_UPPER_BOUND = 50000

STAGE_REGION = 0
STAGE_REALM = 1
STAGE_USER_REALM = 2
STAGE_ITEM = 3
STAGE_PRICE = 4
STAGE_MIN_QTY = 5

KEY_REGION = 'region'
KEY_REALM = 'realm'
KEY_ITEM = 'item'
KEY_PRICE = 'price'


def register(dispatcher: Dispatcher):
    dispatcher.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler('add', _entry_point, filters=~Filters.update.edited_message)],
            states={
                STAGE_REGION: [
                    CallbackQueryHandler(callback=_select_region, pattern=re.compile("region:.."))
                ],
                STAGE_REALM: [
                    MessageHandler(filters=Filters.text & ~Filters.command, callback=_select_realm),
                    CallbackQueryHandler(callback=_select_realm, pattern=re.compile("realm:\\d+"))
                ],
                STAGE_USER_REALM: [
                    CallbackQueryHandler(callback=_select_realm, pattern=re.compile("realm:\\d+")),
                    CallbackQueryHandler(callback=_prompt_region, pattern=re.compile("other"))
                ],
                STAGE_ITEM: [MessageHandler(filters=Filters.text & ~Filters.command, callback=_select_item)],
                STAGE_PRICE: [MessageHandler(filters=Filters.text & ~Filters.command, callback=_enter_price)],
                STAGE_MIN_QTY: [MessageHandler(filters=Filters.text & ~Filters.command, callback=_enter_min_qty)]
            },
            fallbacks=[
                CommandHandler('add', _entry_point, filters=~Filters.update.edited_message),
                CommandHandler('cancel', _cancel, filters=~Filters.update.edited_message)
            ]
        )
    )


def _entry_point(update: Update, context: CallbackContext):
    db = BotContext.get().database
    user = db.get_user(update.effective_user.id)
    if user:
        user_realms = db.get_all_user_realms(user.user_id)[:MAX_USER_REALMS]
        if len(user_realms) > 0:
            keyboard = [[]]
            for realm in user_realms:
                keyboard[0].append(InlineKeyboardButton(
                    f"{realm.region.upper()}-{realm.name}",
                    callback_data=f"realm:{realm.connected_realm_id}")
                )
            keyboard[0].append(InlineKeyboardButton('Other', callback_data="other"))
            update.effective_user.send_message('Select realm:', reply_markup=InlineKeyboardMarkup(keyboard))
            return STAGE_USER_REALM
    return _prompt_region(update, context)


def _prompt_region(update: Update, context: CallbackContext):
    telegram_id = update.effective_user.id
    logger.info(f"user_id={telegram_id} state={context.user_data}")
    reply_markup = InlineKeyboardMarkup([[
        InlineKeyboardButton(r.upper(), callback_data=f"region:{r}") for r in REGIONS
    ]])
    update.effective_user.send_message('Select region:', reply_markup=reply_markup)
    return STAGE_REGION


def _select_region(update: Update, context: CallbackContext):
    telegram_id = update.effective_user.id
    logger.info(f"user_id={telegram_id} state={context.user_data}")
    update.callback_query.answer()
    region = update.callback_query.data.split(':')[1]
    context.user_data[KEY_REGION] = region

    # prompt realm
    db = BotContext.get().database
    user = db.get_user(telegram_id)
    if user:
        user_realms = db.get_user_realms(user.user_id, region)
        if len(user_realms) == 0:
            update.effective_user.send_message('Enter realm name:')
        else:
            reply_markup = InlineKeyboardMarkup([[
                InlineKeyboardButton(r.name, callback_data=f"realm:{r.connected_realm_id}") for r in user_realms
            ]])
            update.effective_user.send_message('Enter or choose realm:', reply_markup=reply_markup)
    else:
        update.effective_user.send_message('Enter realm name:')
    return STAGE_REALM


def _select_realm(update: Update, context: CallbackContext):
    logger.info(f"user_id={update.effective_user.id} state={context.user_data}")

    if update.callback_query:
        update.callback_query.answer()
        db = BotContext.get().database
        realm_id = int(update.callback_query.data.split(':')[1])
        realm = db.get_connected_realm_by_id(realm_id)
    else:
        context.bot.send_chat_action(chat_id=update.effective_message.chat_id, action=ChatAction.TYPING)

        slug = update.message.text.replace('\'', '').replace(' ', '-').lower()
        region = context.user_data[KEY_REGION]
        realm = _get_connected_realm(region, slug)
        if not realm:
            update.effective_user.send_message(f"Error: can't find realm '{update.message.text}'")
            return STAGE_REALM
    context.user_data[KEY_REALM] = realm

    # prompt item id
    update.effective_user.send_message('Enter item ID:')
    return STAGE_ITEM


def _select_item(update: Update, context: CallbackContext):
    logger.info(f"user_id={update.effective_user.id} state={context.user_data}")

    context.bot.send_chat_action(chat_id=update.effective_message.chat_id, action=ChatAction.TYPING)

    try:
        item_id = int(update.message.text)
    except:
        update.effective_user.send_message('Error: invalid item ID')
        return STAGE_ITEM

    # prompt max price
    realm = context.user_data[KEY_REALM]
    item = _get_item_info(realm, item_id)
    if not item:
        update.effective_user.send_message(f"Error: can't find item with ID '{update.message.text}'")
        return STAGE_ITEM
    context.user_data[KEY_ITEM] = item
    update.effective_user.send_message('Enter maximum price:')
    return STAGE_PRICE


def _enter_price(update: Update, context: CallbackContext):
    logger.info(f"user_id={update.effective_user.id} state={context.user_data}")

    context.bot.send_chat_action(chat_id=update.effective_message.chat_id, action=ChatAction.TYPING)

    try:
        price = from_human_price(update.message.text)
    except ValueError as e:
        update.effective_user.send_message(str(e))
        return STAGE_PRICE
    if price < MIN_PRICE:
        update.effective_user.send_message('Error: price must be >= 0.01g')
        return STAGE_PRICE
    if price > MAX_PRICE:
        update.effective_user.send_message('Error: price is too high')
        return STAGE_PRICE
    context.user_data[KEY_PRICE] = price

    # prompt min qty
    update.effective_user.send_message('Enter minimum available quantity:')
    return STAGE_MIN_QTY


def _enter_min_qty(update: Update, context: CallbackContext):
    logger.info(f"user_id={update.effective_user.id} state={context.user_data}")

    context.bot.send_chat_action(chat_id=update.effective_message.chat_id, action=ChatAction.TYPING)

    try:
        min_qty = int(update.message.text)
    except:
        update.effective_user.send_message(f"Invalid quantity: {update.message.text}")
        return STAGE_MIN_QTY
    if min_qty < 1 or min_qty > MIN_QTY_UPPER_BOUND:
        update.effective_user.send_message(
            f"Invalid quantity: {min_qty}, must be within bounds [1, {MIN_QTY_UPPER_BOUND}]")
        return STAGE_MIN_QTY

    user = _get_or_create_user(update.effective_user.id)
    connected_realm = context.user_data[KEY_REALM]
    item = context.user_data[KEY_ITEM]
    price = context.user_data[KEY_PRICE]

    db = BotContext.get().database
    db.add_notification(user.user_id, connected_realm.connected_realm_id, item.item_id, price, min_qty)

    item_link = wowhead_link(item.item_id, item.name)
    price_str = sanitize_str(to_human_price(price))
    realm_name = sanitize_str(connected_realm.name)
    text = (f"Added notification for {item_link} on *{connected_realm.region.upper()}\\-{realm_name}* "
            f"with price {price_str} and minimum quantity of {min_qty}")
    update.effective_user.send_message(
        text,
        parse_mode=PARSEMODE_MARKDOWN_V2,
        disable_web_page_preview=True
    )
    context.user_data.clear()
    return ConversationHandler.END


def _cancel(update: Update, context: CallbackContext):
    context.user_data.clear()
    update.effective_user.send_message("Canceling operation")
    return ConversationHandler.END


def _get_or_create_user(telegram_id: int):
    db = BotContext.get().database
    user = db.get_user(telegram_id)
    if user:
        return user
    else:
        db.add_user(telegram_id)
        return db.get_user(telegram_id)


def _get_connected_realm(region: str, slug: str) -> Optional[ConnectedRealm]:
    db = BotContext.get().database
    realm = db.get_connected_realm(region, slug)
    if realm:
        return realm
    api = BotContext.get().wow_game_api
    realm = api.with_retry(lambda: api.connected_realm(region, slug))
    if realm:
        db.add_connected_realm(realm.connected_realm_id, realm.region, realm.slug, realm.name)
    return realm


def _get_item_info(realm: ConnectedRealm, item_id: int) -> Optional[Item]:
    db = BotContext.get().database
    item = db.get_item(item_id)
    if item:
        return item
    api = BotContext.get().wow_game_api
    item = api.with_retry(lambda: api.item_info(realm.region, item_id))
    if item:
        db.add_item(item_id, item.name)
    return item
