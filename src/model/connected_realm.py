class ConnectedRealm:
    connected_realm_id: int
    slug: str
    name: str

    def __init__(self, connected_realm_id: int, slug: str, name: str):
        self.connected_realm_id = connected_realm_id
        self.slug = slug
        self.name = name
