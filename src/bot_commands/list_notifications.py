import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatAction
from telegram.constants import PARSEMODE_MARKDOWN_V2
from telegram.ext import CommandHandler, Dispatcher, CallbackQueryHandler, CallbackContext, Filters

from bot_context import BotContext
from model.notification import Notification
from utils import to_human_price, wowhead_link


def register(dispatcher: Dispatcher):
    dispatcher.add_handler(CommandHandler('list', _command, filters=~Filters.update.edited_message))
    dispatcher.add_handler(CallbackQueryHandler(_callback_query, pattern=re.compile("remove:\\d+")))


def _command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    db = BotContext.get().database
    user = db.get_user(user_id)
    if not user:
        return

    context.bot.send_chat_action(chat_id=update.effective_message.chat_id, action=ChatAction.TYPING)

    notifications = db.get_user_notifications(user.user_id)
    if len(notifications) == 0:
        update.effective_user.send_message("You don't have active notifications")
        return
    item_names = _get_item_names(notifications)
    for notification in notifications:
        callback_data = f"remove:{notification.n_id}"
        button_list = [[InlineKeyboardButton("Delete", callback_data=callback_data)]]
        reply_markup = InlineKeyboardMarkup(button_list)
        name = item_names[notification.item_id]
        price = to_human_price(notification.price).replace('.', '\\.')
        text = (f"{wowhead_link(notification.item_id, name)} "
                f"for {price} with minimum quantity of {notification.min_qty}")
        update.effective_user.send_message(
            text,
            parse_mode=PARSEMODE_MARKDOWN_V2,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )


def _callback_query(update: Update, context: CallbackContext):
    update.callback_query.answer()
    db = BotContext.get().database
    user = db.get_user(update.effective_user.id)
    if not user:
        return

    context.bot.send_chat_action(chat_id=update.effective_message.chat_id, action=ChatAction.TYPING)

    _, notification_id = update.callback_query.data.split(':')
    if db.delete_notification(user.user_id, notification_id):
        update.effective_message.delete()
        count = db.get_notifications_count(user.user_id)
        if count == 0:
            update.effective_user.send_message("You don't have active notifications")


def _get_item_names(notifications: list[Notification]) -> dict[int, str]:
    items_ids = [n.item_id for n in notifications]
    result = {}
    items = BotContext.get().database.get_items(items_ids)
    for item in items:
        result[item.item_id] = item.name
    return result
