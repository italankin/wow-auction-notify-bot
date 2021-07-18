import logging
from typing import Optional

from telegram import Update, ChatAction
from telegram.constants import PARSEMODE_MARKDOWN_V2
from telegram.ext import CommandHandler, Dispatcher, CallbackContext, Filters, ConversationHandler, MessageHandler

from bot_context import BotContext
from db.database import Item
from model.connected_realm import ConnectedRealm
from utils import from_human_price, to_human_price, wowhead_link

logger = logging.getLogger(__name__)

STAGE_REALM = 0
STAGE_ITEM = 1
STAGE_PRICE = 2
STAGE_MIN_QTY = 3

KEY_REALM = 'realm'
KEY_ITEM = 'item'
KEY_PRICE = 'price'


def register(dispatcher: Dispatcher):
    dispatcher.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler('add', _add, filters=~Filters.update.edited_message)],
            states={
                STAGE_REALM: [MessageHandler(filters=Filters.text & ~Filters.command, callback=_select_realm)],
                STAGE_ITEM: [MessageHandler(filters=Filters.text & ~Filters.command, callback=_select_item)],
                STAGE_PRICE: [MessageHandler(filters=Filters.text & ~Filters.command, callback=_enter_price)],
                STAGE_MIN_QTY: [MessageHandler(filters=Filters.text & ~Filters.command, callback=_enter_min_qty)]
            },
            fallbacks=[
                CommandHandler('add', _add, filters=~Filters.update.edited_message),
                CommandHandler('cancel', _cancel, filters=~Filters.update.edited_message)
            ]
        )
    )


def _add(update: Update, context: CallbackContext):
    logger.info(f"user_id={update.effective_user.id} state={context.user_data}")
    update.effective_user.send_message('Enter the realm:')
    return STAGE_REALM


def _cancel(update: Update, context: CallbackContext):
    context.user_data.clear()
    update.effective_user.send_message("Canceling operation")
    return ConversationHandler.END


def _select_realm(update: Update, context: CallbackContext):
    logger.info(f"user_id={update.effective_user.id} state={context.user_data}")

    context.bot.send_chat_action(chat_id=update.effective_message.chat_id, action=ChatAction.TYPING)

    slug = update.message.text.replace('\'', '').replace(' ', '-').lower()
    realm = _get_connected_realm(slug)
    if not realm:
        update.effective_user.send_message(f"Error: can't find realm '{update.message.text}'")
        return STAGE_REALM
    context.user_data[KEY_REALM] = realm
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
    item = _get_item_info(item_id)
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
    if price < 100:
        update.effective_user.send_message('Error: price must be >= 0.01g')
        return STAGE_PRICE
    if price > 10_000_000 * 10000:
        update.effective_user.send_message('Error: price is too high')
        return STAGE_PRICE
    context.user_data[KEY_PRICE] = price
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
    if min_qty < 1 or min_qty > 50000:
        update.effective_user.send_message(f"Invalid quantity: {min_qty}")
        return STAGE_MIN_QTY

    db = BotContext.get().database

    user = _get_or_create_user(update.effective_user.id)
    connected_realm = context.user_data[KEY_REALM]
    item = context.user_data[KEY_ITEM]
    price = context.user_data[KEY_PRICE]

    db.add_notification(user.user_id, connected_realm.connected_realm_id, item.item_id, price, min_qty)

    item_link = wowhead_link(item.item_id, item.name)
    price_str = to_human_price(price).replace('.', '\\.')
    text = f"Added notification for {item_link} on *{connected_realm.name}* " \
           f"with price {price_str} and minimum quantity of {min_qty}"
    update.effective_user.send_message(
        text,
        parse_mode=PARSEMODE_MARKDOWN_V2,
        disable_web_page_preview=True
    )
    context.user_data.clear()
    return ConversationHandler.END


def _get_or_create_user(telegram_id: int):
    db = BotContext.get().database
    user = db.get_user(telegram_id)
    if user:
        return user
    else:
        db.add_user(telegram_id)
        return db.get_user(telegram_id)


def _get_connected_realm(slug: str) -> Optional[ConnectedRealm]:
    db = BotContext.get().database
    realm = db.get_connected_realm(slug)
    if realm:
        return realm
    realm = BotContext.get().wow_game_api.connected_realm(slug)
    if realm:
        db.add_connected_realm(realm.connected_realm_id, realm.slug, realm.name)
    return realm


def _get_item_info(item_id: int) -> Optional[Item]:
    db = BotContext.get().database
    item = db.get_item(item_id)
    if item:
        return item
    item = BotContext.get().wow_game_api.item_info(item_id)
    if item:
        db.add_item(item_id, item.name)
    return item
