class Notification:
    n_id: int
    user_id: int
    connected_realm_id: int
    item_id: int
    price: int
    min_qty: int

    def __init__(self, n_id, user_id: int, connected_realm_id: int, item_id: int, price: int, min_qty: int):
        self.n_id = n_id
        self.user_id = user_id
        self.connected_realm_id = connected_realm_id
        self.item_id = item_id
        self.price = price
        self.min_qty = min_qty
