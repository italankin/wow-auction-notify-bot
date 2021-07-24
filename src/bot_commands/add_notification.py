import re
from typing import Optional

from telegram import Update, ChatAction, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import PARSEMODE_MARKDOWN_V2
from telegram.ext import CommandHandler, Dispatcher, CallbackContext, Filters, ConversationHandler, MessageHandler, \
    CallbackQueryHandler

from bot_context import BotContext
from db.database import Item
from model.connected_realm import ConnectedRealm
from model.notification import Notification
from utils import from_human_price, to_human_price, wowhead_link, sanitize_str
from wow.wow_game_api import REGIONS

MAX_USER_REALMS = 3

MIN_PRICE = 100  # 1 silver
MAX_PRICE = 2_000_000 * 10000  # 2 mil gold
VALUE_UPPER_BOUND = 50000

STAGE_REGION = 0
STAGE_REALM = 1
STAGE_USER_REALM = 2
STAGE_ITEM = 3
STAGE_KIND = 4
STAGE_PRICE = 5
STAGE_VALUE = 6

KEY_REGION = 'region'
KEY_REALM = 'realm'
KEY_ITEM = 'item'
KEY_KIND = 'kind'
KEY_PRICE = 'price'
KEY_VALUE = 'value'


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
                STAGE_ITEM: [
                    MessageHandler(filters=Filters.text & ~Filters.command, callback=_select_item),
                    CallbackQueryHandler(callback=_select_item, pattern=re.compile("item:\\d+"))
                ],
                STAGE_KIND: [CallbackQueryHandler(callback=_select_kind, pattern=re.compile("kind:.+"))],
                STAGE_PRICE: [MessageHandler(filters=Filters.text & ~Filters.command, callback=_enter_price)],
                STAGE_VALUE: [MessageHandler(filters=Filters.text & ~Filters.command, callback=_enter_value)]
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
    if update.callback_query:
        update.callback_query.answer()
        update.callback_query.message.delete()

    reply_markup = InlineKeyboardMarkup([[
        InlineKeyboardButton(r.upper(), callback_data=f"region:{r}") for r in REGIONS
    ]])
    update.effective_user.send_message('Select region:', reply_markup=reply_markup)
    return STAGE_REGION


def _select_region(update: Update, context: CallbackContext):
    if not update.callback_query:
        return STAGE_REGION

    update.callback_query.answer()
    update.callback_query.message.delete()

    region = update.callback_query.data.split(':')[1]
    context.user_data[KEY_REGION] = region

    # prompt realm
    db = BotContext.get().database
    user = db.get_user(update.effective_user.id)
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
    if update.callback_query:
        update.callback_query.answer()
        update.callback_query.message.delete()

        db = BotContext.get().database
        realm_id = int(update.callback_query.data.split(':')[1])
        realm = db.get_connected_realm_by_id(realm_id)
    else:
        context.bot.send_chat_action(chat_id=update.effective_message.chat_id, action=ChatAction.TYPING)

        slug = update.message.text.replace('\'', '').replace(' ', '-').lower()
        region = context.user_data[KEY_REGION]
        realm = _get_connected_realm(region, slug)
        if not realm:
            update.effective_user.send_message(f"Error: can't find realm")
            return STAGE_REALM
    context.user_data[KEY_REALM] = realm

    # prompt item
    update.effective_user.send_message('Enter item name or ID:')
    return STAGE_ITEM


def _select_item(update: Update, context: CallbackContext):
    realm = context.user_data[KEY_REALM]

    if update.callback_query:
        update.callback_query.answer()
        update.callback_query.message.delete()

        item_id = int(update.callback_query.data.split(':')[1])
        item = _get_item_info(realm, item_id)
        context.user_data[KEY_ITEM] = item

        return _prompt_kind(update, context)

    context.bot.send_chat_action(chat_id=update.effective_message.chat_id, action=ChatAction.TYPING)

    if re.fullmatch('\\d+', update.message.text):
        item_id = int(update.message.text)
        item = _get_item_info(realm, item_id)
        if not item:
            update.effective_user.send_message(f"Error: can't find item")
            return STAGE_ITEM
    else:
        items = _get_item_infos_by_name(realm, update.message.text[:64])
        if len(items) == 0:
            update.effective_user.send_message('Error: no items found')
            return STAGE_ITEM
        elif len(items) == 1:
            item = items[0]
        else:
            keyboard = []
            for it in items:
                keyboard.append([
                    InlineKeyboardButton(f"{it.name} ({it.item_id})", callback_data=f"item:{it.item_id}")
                ])
            text = "Select item or refine query:"
            update.effective_user.send_message(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return STAGE_ITEM
    context.user_data[KEY_ITEM] = item

    text = f"Selected {wowhead_link(item.item_id, item.name)} \\({item.item_id}\\)"
    update.effective_user.send_message(text, parse_mode=PARSEMODE_MARKDOWN_V2, disable_web_page_preview=True)

    return _prompt_kind(update, context)


def _prompt_kind(update: Update, context: CallbackContext):
    reply_markup = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "Maximum price", callback_data=f"kind:{Notification.Kind.MAX_PRICE.value[0]}"),
        InlineKeyboardButton(
            "Market price", callback_data=f"kind:{Notification.Kind.MARKET_PRICE.value[0]}"),
        InlineKeyboardButton(
            "Average price", callback_data=f"kind:{Notification.Kind.AVG_PRICE.value[0]}")
    ]])
    update.effective_user.send_message('Select notification type:', reply_markup=reply_markup)
    return STAGE_KIND


def _select_kind(update: Update, context: CallbackContext):
    if not update.callback_query:
        return STAGE_KIND

    update.callback_query.answer()
    update.callback_query.message.delete()

    kind = Notification.Kind.from_str(update.callback_query.data.split(':')[1])
    context.user_data[KEY_KIND] = kind

    if kind == Notification.Kind.MARKET_PRICE:
        context.user_data[KEY_VALUE] = 1

    # prompt price
    if kind == Notification.Kind.MAX_PRICE:
        text = 'Enter maximum price:'
    elif kind == Notification.Kind.MARKET_PRICE:
        text = 'Enter market price:'
    else:
        text = 'Enter average price:'
    update.effective_user.send_message(text)
    return STAGE_PRICE


def _enter_price(update: Update, context: CallbackContext):
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

    if context.user_data[KEY_KIND] == Notification.Kind.MARKET_PRICE:
        _add_notification(update, context.user_data)
        return ConversationHandler.END

    # prompt min qty
    update.effective_user.send_message('Enter minimum available quantity:')
    return STAGE_VALUE


def _enter_value(update: Update, context: CallbackContext):
    try:
        value = int(update.message.text)
    except:
        update.effective_user.send_message(f"Invalid quantity: {update.message.text}")
        return STAGE_VALUE
    if value < 1 or value > VALUE_UPPER_BOUND:
        update.effective_user.send_message(
            f"Invalid quantity: {value}, must be within bounds [1, {VALUE_UPPER_BOUND}]")
        return STAGE_VALUE
    context.user_data[KEY_VALUE] = value

    context.bot.send_chat_action(chat_id=update.effective_message.chat_id, action=ChatAction.TYPING)

    _add_notification(update, context.user_data)
    context.user_data.clear()
    return ConversationHandler.END


def _add_notification(update, user_data):
    user = _get_or_create_user(update.effective_user.id)
    realm = user_data[KEY_REALM]
    item = user_data[KEY_ITEM]
    price = user_data[KEY_PRICE]
    kind = user_data[KEY_KIND]
    value = user_data[KEY_VALUE]

    db = BotContext.get().database
    if not db.get_item(item.item_id):
        db.add_item(item.item_id, item.name)
    if not db.get_connected_realm_by_id(realm.connected_realm_id):
        db.add_connected_realm(realm.connected_realm_id, realm.region, realm.slug, realm.name)
    db.add_notification(user.user_id, realm.connected_realm_id, item.item_id, kind.value[0], price, value)

    item_link = wowhead_link(item.item_id, item.name)
    price_str = sanitize_str(to_human_price(price))
    realm_name = sanitize_str(realm.name)
    if kind == Notification.Kind.MAX_PRICE:
        text = (f"Added notification for {item_link} on *{realm.region.upper()}\\-{realm_name}* "
                f"with maximum price {price_str} and minimum quantity of {value}")
    elif kind == Notification.Kind.MARKET_PRICE:
        text = (f"Added notification for {item_link} on *{realm.region.upper()}\\-{realm_name}* "
                f"with market price of {price_str}")
    else:
        text = (f"Added notification for {item_link} on *{realm.region.upper()}\\-{realm_name}* "
                f"with average price {price_str} and minimum quantity of {value}")
    update.effective_user.send_message(text, parse_mode=PARSEMODE_MARKDOWN_V2, disable_web_page_preview=True)


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
    return realm


def _get_item_info(realm: ConnectedRealm, item_id: int) -> Optional[Item]:
    db = BotContext.get().database
    item = db.get_item(item_id)
    if item:
        return item
    api = BotContext.get().wow_game_api
    item = api.with_retry(lambda: api.item_info_by_id(realm.region, item_id))
    return item


def _get_item_infos_by_name(realm: ConnectedRealm, item_name: str) -> list[Item]:
    api = BotContext.get().wow_game_api
    items = api.with_retry(lambda: api.item_info_by_name(realm.region, item_name))
    for item in items:
        if item_name.lower() == item.name.lower():
            # exact match
            return [item]
    return items
