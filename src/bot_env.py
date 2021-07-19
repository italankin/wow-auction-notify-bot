import os


class BotEnv:
    bot_token: str
    database: str
    bnet_client_id: str
    bnet_client_secret: str
    max_notifications: int
    update_interval: int

    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.database = os.getenv('DATABASE')
        self.bnet_client_id = os.getenv('BNET_CLIENT_ID')
        self.bnet_client_secret = os.getenv('BNET_CLIENT_SECRET')
        self.max_notifications = int(os.getenv('MAX_NOTIFICATIONS', '10'))
        self.update_interval = int(os.getenv('UPDATE_INTERVAL', '60'))
