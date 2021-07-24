import logging
from typing import Optional, Callable, TypeVar

import requests

from model.auction import Auction
from model.connected_realm import ConnectedRealm
from model.item import Item

REGIONS = ['us', 'eu', 'kr', 'tw']

TOKEN_URL = 'https://us.battle.net/oauth/token'
DATA_URL = 'https://%s.api.blizzard.com'

PATH_SEARCH_CONNECTED_REALM = '/data/wow/search/connected-realm'
PATH_AUCTION_CONNECTED_REALM = '/data/wow/connected-realm/%d/auctions'
PATH_ITEM = '/data/wow/item/%d'
PATH_ITEM_SEARCH = '/data/wow/search/item'

PARAM_DYNAMIC_NAMESPACE = 'dynamic-%s'
PARAM_STATIC_NAMESPACE = 'static-%s'
PARAM_LOCALE = 'en_US'

logger = logging.getLogger(__name__)


class WowGameApi:

    def __init__(self, client_id: str, client_secret: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token = None

    def connected_realm(self, region: str, slug: str) -> Optional[ConnectedRealm]:
        params = {
            'namespace': PARAM_DYNAMIC_NAMESPACE % region,
            'realms.slug': slug
        }
        headers = {'Authorization': f"Bearer {self._get_access_token()}"}
        response = requests.get(f"{DATA_URL % region}{PATH_SEARCH_CONNECTED_REALM}", headers=headers, params=params)
        self._check_status_code(response.status_code)
        if response.status_code != 200:
            logger.error(f"failed to find connected realm: status={response.status_code}\n{response.text}")
            return None
        results = response.json()['results']
        for result in results:
            data = result['data']
            realm_id = data['id']
            if realm_id:
                name = slug
                for realms in data['realms']:
                    name = realms['name'][PARAM_LOCALE]
                    break
                return ConnectedRealm(realm_id, region, slug, name)
        logger.info(f"no connected realms found for slug={slug}")
        return None

    def auctions(self, region: str, connected_realm_id: int, item_ids: list[int]) -> dict[int, Auction]:
        params = {
            'namespace': PARAM_DYNAMIC_NAMESPACE % region,
            'locale': PARAM_LOCALE
        }
        headers = {'Authorization': f"Bearer {self._get_access_token()}"}
        response = requests.get(
            f"{DATA_URL % region}{PATH_AUCTION_CONNECTED_REALM % connected_realm_id}", headers=headers, params=params)
        self._check_status_code(response.status_code)
        if response.status_code != 200:
            logger.error(f"failed to fetch auction data for connected_realm_id={connected_realm_id}: "
                         f"status={response.status_code}\n{response.text}")
            return {}
        auctions_data = {}
        auctions = response.json()['auctions']
        for auction in auctions:
            item_id = auction['item']['id']
            if item_id in item_ids:
                qty = auction['quantity']
                price = auction['unit_price'] or auction['buyout']
                item = auctions_data.setdefault(item_id, Auction(item_id))
                item.lots.append(Auction.Lot(price, qty))
        for _, auction in auctions_data.items():
            auction.lots.sort(key=lambda lot: lot.price)
        return auctions_data

    def item_info_by_id(self, region: str, item_id: int) -> Optional[Item]:
        params = {
            'namespace': PARAM_STATIC_NAMESPACE % region,
            'locale': PARAM_LOCALE
        }
        headers = {'Authorization': f"Bearer {self._get_access_token()}"}
        response = requests.get(f"{DATA_URL % region}{PATH_ITEM % item_id}", headers=headers, params=params)
        self._check_status_code(response.status_code)
        if response.status_code == 404:
            logger.info(f"item with id={item_id} not found")
            return None
        if response.status_code != 200:
            logger.error(f"failed to fetch item id={item_id} info: "
                         f"status={response.status_code}\n{response.text}")
            return None
        name = response.json()['name']
        return Item(item_id, name)

    def item_info_by_name(self, region: str, item_name: str, max_results: int = 5) -> list[Item]:
        params = {
            'namespace': PARAM_STATIC_NAMESPACE % region,
            'name.%s' % PARAM_LOCALE: item_name,
            '_pageSize': max_results
        }
        headers = {'Authorization': f"Bearer {self._get_access_token()}"}
        response = requests.get(f"{DATA_URL % region}{PATH_ITEM_SEARCH}", headers=headers, params=params)
        self._check_status_code(response.status_code)
        if response.status_code != 200:
            logger.error(f"failed to fetch item name={item_name} info: "
                         f"status={response.status_code}\n{response.text}")
            return []
        results = []
        for node in response.json()['results']:
            data = node['data']
            item_id = data['id']
            item_name = data['name'][PARAM_LOCALE]
            results.append(Item(item_id, item_name))
        return results

    T = TypeVar('T')

    def with_retry(self, func: Callable[[], T], max_retries=5) -> T:
        count = 0
        while True:
            try:
                return func()
            except WowGameApi.UnauthorizedError as e:
                count += 1
                if count >= max_retries:
                    raise e

    def _check_status_code(self, status_code):
        if status_code == 401:
            self._access_token = None
            raise WowGameApi.UnauthorizedError()

    def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token
        response = requests.post(
            TOKEN_URL,
            auth=(self._client_id, self._client_secret),
            data={'grant_type': 'client_credentials'}
        )
        if response.status_code != 200:
            raise ValueError(f"failed to fetch access token:\n{response.text}")
        token = response.json()['access_token']
        if token:
            self._access_token = token
            return self._access_token
        raise ValueError(f"access token not found in response:\n{response.text}")

    class UnauthorizedError(Exception):
        pass
