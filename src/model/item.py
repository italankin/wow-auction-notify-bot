class Item:
    item_id: int
    name: str

    def __init__(self, item_id: int, name: str):
        self.item_id = item_id
        self.name = name
