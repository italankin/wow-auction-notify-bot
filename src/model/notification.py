from enum import Enum


class Notification:
    n_id: int
    user_id: int
    connected_realm_id: int
    item_id: int
    kind: 'Notification.Kind'
    price: int
    value: int

    def __init__(self, n_id, user_id: int, connected_realm_id: int, item_id: int, kind: str, price: int, value: int):
        self.n_id = n_id
        self.user_id = user_id
        self.connected_realm_id = connected_realm_id
        self.item_id = item_id
        self.kind = Notification.Kind.from_str(kind)
        self.price = price
        self.value = value

    class Kind(Enum):
        MAX_PRICE = "max_price",
        MARKET_PRICE = "market_price",
        AVG_PRICE = "avg_price"

        @staticmethod
        def from_str(kind: str) -> 'Notification.Kind':
            for k in Notification.Kind:
                if k.value[0] == kind:
                    return k
            return Notification.Kind.MAX_PRICE
