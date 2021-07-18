from bot_env import BotEnv
from db.database import Database
from wow.wow_game_api import WowGameApi


class BotContext:
    bot_env: BotEnv
    wow_game_api: WowGameApi
    database: Database

    def __init__(self):
        self.bot_env = BotEnv()
        self.wow_game_api = WowGameApi(self.bot_env.bnet_client_id, self.bot_env.bnet_client_secret)
        self.database = Database(self.bot_env.database)

    @staticmethod
    def get() -> 'BotContext':
        return _bot_context


_bot_context = BotContext()
