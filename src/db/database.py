import logging
import sqlite3
from typing import Optional

from model.connected_realm import ConnectedRealm
from model.item import Item
from model.notification import Notification
from model.user import User

logger = logging.getLogger(__name__)


class Database:

    def __init__(self, database: str):
        self._database = database
        self._con = None

    def create_tables(self):
        with self._get_connection() as con:
            con.execute(
                'CREATE TABLE IF NOT EXISTS users ('
                'id INTEGER PRIMARY KEY,'
                'telegram_id INTEGER NOT NULL,'
                'level INTEGER DEFAULT 0'  # 0 - user, 1 - admin 
                ')'
            )
            con.execute(
                'CREATE TABLE IF NOT EXISTS items ('
                'id INTEGER PRIMARY KEY,'
                'name TEXT NOT NULL'
                ')'
            )
            con.execute(
                'CREATE TABLE IF NOT EXISTS connected_realms ('
                'id INTEGER PRIMARY KEY,'
                'region TEXT NOT NULL,'
                'slug TEXT NOT NULL,'
                'name TEXT NOT NULL'
                ')'
            )
            con.execute(
                'CREATE TABLE IF NOT EXISTS notifications ('
                'id INTEGER PRIMARY KEY,'
                'user_id INTEGER NOT NULL,'
                'connected_realm_id INTEGER NOT NULL,'
                'item_id INTEGER NOT NULL,'
                'price INTEGER NOT NULL,'
                'min_qty INTEGER DEFAULT 1,'
                'FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,'
                'FOREIGN KEY(connected_realm_id) REFERENCES connected_realms(id) ON DELETE NO ACTION,'
                'FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE NO ACTION'
                ')'
            )

    def add_connected_realm(self, connected_realm_id: int, region: str, slug: str, name: str):
        with self._get_connection() as con:
            sql = 'INSERT INTO connected_realms VALUES(?, ?, ?, ?)'
            con.execute(sql, (connected_realm_id, region, slug, name))
            logger.info(f"added connected realm id={connected_realm_id}: {region}-{name}'")

    def get_connected_realm(self, region: str, slug: str) -> Optional[ConnectedRealm]:
        with self._get_connection() as con:
            sql = 'SELECT * FROM connected_realms WHERE region = ? AND slug = ?'
            cur = con.execute(sql, [region, slug])
            row = cur.fetchone()
            if row:
                return ConnectedRealm(*row)
        logger.info(f"connected realm {region}-{slug} not found")
        return None

    def get_connected_realm_by_id(self, connected_realm_id: int) -> Optional[ConnectedRealm]:
        with self._get_connection() as con:
            sql = 'SELECT * FROM connected_realms WHERE id = ?'
            cur = con.execute(sql, [connected_realm_id])
            row = cur.fetchone()
            if row:
                return ConnectedRealm(*row)
        logger.info(f"connected realm id={connected_realm_id} not found")
        return None

    def get_connected_realms(self, ids: list[int]) -> list[ConnectedRealm]:
        result = []
        with self._get_connection() as con:
            sql = 'SELECT * FROM connected_realms WHERE id in (%s)' % (','.join('?' * len(ids)))
            cur = con.execute(sql, ids)
            for row in cur:
                result.append(ConnectedRealm(*row))
        return result

    def add_item(self, item_id: int, name: str):
        with self._get_connection() as con:
            sql = 'INSERT INTO items VALUES(?, ?)'
            con.execute(sql, (item_id, name))
            logger.info(f"added item id={item_id}, name='{name}'")

    def get_item(self, item_id: int) -> Optional[Item]:
        with self._get_connection() as con:
            sql = 'SELECT name FROM items WHERE id = ?'
            cur = con.execute(sql, [item_id])
            row = cur.fetchone()
            if row:
                return Item(item_id, row[0])
        logger.info(f"item id={item_id} not found")
        return None

    def get_items(self, item_ids: list[int]) -> list[Item]:
        result = []
        with self._get_connection() as con:
            sql = 'SELECT * FROM items WHERE id in (%s)' % (','.join('?' * len(item_ids)))
            cur = con.execute(sql, item_ids)
            for row in cur:
                result.append(Item(*row))
        return result

    def add_user(self, telegram_id: int):
        with self._get_connection() as con:
            sql = 'INSERT INTO users(telegram_id) VALUES (?)'
            con.execute(sql, [telegram_id])
            logger.info(f"added user telegram_id={telegram_id}")

    def get_user(self, telegram_id: int) -> Optional[User]:
        with self._get_connection() as con:
            sql = 'SELECT * FROM users WHERE telegram_id = ?'
            cur = con.execute(sql, [telegram_id])
            row = cur.fetchone()
            if row:
                return User(*row)
        logger.info(f"user telegram_id={telegram_id} not found")
        return None

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        with self._get_connection() as con:
            sql = 'SELECT * FROM users WHERE id = ?'
            cur = con.execute(sql, [user_id])
            row = cur.fetchone()
            if row:
                return User(*row)
        logger.info(f"user id={user_id} not found")
        return None

    def delete_user(self, user_id: int):
        with self._get_connection() as con:
            sql = 'DELETE FROM users WHERE id = ?'
            con.execute(sql, [user_id])
            logger.info(f"deleted user id={user_id}")

    def add_notification(self, user_id: int, connected_realm_id: int, item_id: int, price: int, min_qty: int):
        with self._get_connection() as con:
            sql = ('INSERT INTO notifications(user_id, connected_realm_id, item_id, price, min_qty) '
                   'VALUES (?, ?, ?, ?, ?)')
            cur = con.execute(sql, (user_id, connected_realm_id, item_id, price, min_qty))
            logger.info(f"added notification id={cur.lastrowid}")

    def get_notifications(self) -> list[Notification]:
        result = []
        with self._get_connection() as con:
            sql = 'SELECT * FROM notifications'
            for row in con.execute(sql):
                result.append(Notification(*row))
        return result

    def get_notifications_count(self, user_id) -> int:
        with self._get_connection() as con:
            sql = 'SELECT COUNT(*) FROM notifications WHERE user_id = ?'
            cur = con.execute(sql, [user_id])
            row = cur.fetchone()
            if row:
                return int(row[0])
        return 0

    def get_user_notifications(self, user_id: int) -> list[Notification]:
        result = []
        with self._get_connection() as con:
            sql = 'SELECT * FROM notifications WHERE user_id = ?'
            for row in con.execute(sql, [user_id]):
                result.append(Notification(*row))
        return result

    def get_all_user_realms(self, user_id: int) -> list[ConnectedRealm]:
        result = []
        with self._get_connection() as con:
            sql = ('SELECT DISTINCT n.connected_realm_id, cr.region, cr.slug, cr.name '
                   'FROM notifications n '
                   'INNER JOIN connected_realms cr ON n.connected_realm_id = cr.id '
                   'WHERE n.user_id = ?')
            cur = con.execute(sql, [user_id])
            for row in cur:
                result.append(ConnectedRealm(*row))
        return result

    def get_user_realms(self, user_id: int, region: str) -> list[ConnectedRealm]:
        result = []
        with self._get_connection() as con:
            sql = ('SELECT DISTINCT * FROM connected_realms WHERE region = ? AND '
                   'id in (SELECT connected_realm_id FROM notifications WHERE user_id = ?)')
            cur = con.execute(sql, [region, user_id])
            for row in cur:
                result.append(ConnectedRealm(*row))
        return result

    def delete_notification(self, user_id: int, notification_id: int) -> bool:
        with self._get_connection() as con:
            sql = 'DELETE FROM notifications WHERE user_id = ? AND id = ?'
            cur = con.execute(sql, (user_id, notification_id))
            if cur.rowcount > 0:
                logger.info(f"deleted notification id={notification_id}")
                return True
        return False

    def close(self):
        if self._con:
            self._con.close()
            self._con = None

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self._database)
