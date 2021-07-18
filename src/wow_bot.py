import atexit
import logging
import os

from telegram.ext import Updater

import bot_commands.add_notification
import bot_commands.list_notifications
import bot_jobs.check
from bot_context import BotContext

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG if os.getenv('DEBUG') == "1" else logging.INFO
)

aps_logger = logging.getLogger('apscheduler')
aps_logger.setLevel(logging.WARNING)


def on_exit():
    BotContext.get().database.close()


# init db
BotContext.get().database.create_tables()
atexit.register(on_exit)

updater = Updater(token=BotContext.get().bot_env.bot_token)
dispatcher = updater.dispatcher

# register commands
bot_commands.list_notifications.register(dispatcher)
bot_commands.add_notification.register(dispatcher)

# register jobs
bot_jobs.check.register(dispatcher)

updater.start_polling()
updater.idle()
