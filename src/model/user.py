class User:
    user_id: int
    telegram_id: int
    level: int

    def __init__(self, user_id: int, telegram_id: int, level: int):
        self.user_id = user_id
        self.telegram_id = telegram_id
        self.level = level
