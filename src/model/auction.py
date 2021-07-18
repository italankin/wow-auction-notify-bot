class Auction:
    item_id: int
    lots: list['Auction.Lot']

    def __init__(self, item_id: int):
        self.item_id = item_id
        self.lots = []

    class Lot:
        price: int
        qty: int

        def __init__(self, price: int, qty: int):
            self.price = price
            self.qty = qty
