import requests
import datetime as dt
import time
import gzip
import math


class BitpostInterface:

    wallettoken = None
    api_key = None
    baseURL = "https://api.bitpost.co"
    next_target = round(time.time() + 3600)
    _cached_getUTXOsData = None
    _cache_timestamp = 0
    _cache_showrawtx = False
    _cache_timeout = 3

    def __init__(self, wallettoken=None, api_key=None, testnet=False):
        self.wallettoken = wallettoken
        self.api_key = api_key
        if testnet:
            self.baseURL = "https://testnet-api.bitpost.co"
        else:
            self.baseURL = "https://api.bitpost.co"

    def set_future_target(self, target):
        self.next_target = target

    def get_wallettoken(self, pub_key_hex, signature_base64):
        signature_proof = {'signature': signature_base64.decode('ascii'), 'publickey': pub_key_hex}
        signature_proofs = [signature_proof]
        answer = requests.post(self.baseURL + '/wallettokens', data=str(signature_proofs))
        if answer.status_code == 200 and len(answer.json()['data']['wallettokens']['active']) > 0:
            return answer.json()['data']['wallettokens']['active'][0]
        return None

    def create_bitpost_request(self, rawTxs, target=3600, delay=1, broadcast_lowest_feerate=False, feerates=[]):
        self._cache_timestamp = time.time()
        return BitpostRequest(rawTxs, target_in_seconds=target, delay=delay,
                              broadcast_lowest_feerate=broadcast_lowest_feerate, feerates=feerates,
                              api_key=self.api_key, wallettoken=self.wallettoken, baseURL=self.baseURL)

    def get_utxos_used_by_bitpost(self):
        self._fetch_utxos_data()
        used_utxos = []
        for request_group_data in self._cached_getUTXOsData:
            used_utxos += request_group_data['used']
        return used_utxos

    def get_change_utxos_from_bitpost(self):
        self._fetch_utxos_data()
        return self._cached_getUTXOsData

    def get_psts_for_verification(self):
        self._fetch_utxos_data(showrawtx=True)
        if not self._cached_getUTXOsData.keys().contains('path/to/psts'):
            return []
        return self._cached_getUTXOsData['path/to/psts']

    def _fetch_utxos_data(self, showrawtx = False):
        if self.wallettoken is None and self.api_key is None:
            print('Cant change request if wallettoken and API key is not set.')
            raise Exception('Unauthorized API call: wallettoken and API key not set.')

        if time.time() - self._cache_timestamp < 3 and (self._cache_showrawtx or not showrawtx):
            return
        getUTXOsQuery = self.baseURL + '/utxos?wallettoken=' + self.wallettoken + '&target=' + str(self.next_target) + \
                        '&showrawtx=' + str(showrawtx)
        answer = requests.get(getUTXOsQuery)
        if answer.status_code >= 400:
            raise Exception("Failed to reach /utxos endpoint")

        self._cache_timestamp = time.time()
        self._cache_showrawtx = showrawtx
        self._cached_getUTXOsData = answer.json()['data']['utxos']

    def get_feerates(self, max_feerate, size=50, can_reduce_fee=True, target=None):
        parameters = {'maxfeerate': max_feerate, 'size': min(size, math.floor(max_feerate)), 'canreducefee': str(can_reduce_fee)}
        if target is not None:
            parameters['target'] = target
        answer = requests.get(self.baseURL + '/feerateset', params=parameters)
        if answer.status_code >= 400:
            raise Exception("Failed to get set of feerates!")
        return answer.json()['data']['feerates']


class BitpostRequest:

    absolute_epoch_target = 3600
    delay = 1
    broadcast_lowest_feerate = False

    api_key = None
    wallettoken = None
    baseURL = ''

    rawTxs = []
    feerates = []
    id = None
    answer = None

    def __init__(self, rawTxs, target_in_seconds=3600, delay=1, broadcast_lowest_feerate=False,
                 feerates=[], api_key = None, wallettoken=None, baseURL=None):
        self.rawTxs = rawTxs
        self.delay = delay
        self.absolute_epoch_target = BitpostRequest._to_epoch(target_in_seconds)
        self.broadcast_lowest_feerate = broadcast_lowest_feerate
        self.feerates = feerates
        self.api_key = api_key
        self.answer = None
        self.wallettoken = wallettoken
        self.notifications = []
        self.baseURL = baseURL

    @classmethod
    def _to_epoch(cls, raw_target):
        if raw_target < 100_000_000:
            return round(dt.datetime.now().timestamp() + raw_target)
        elif raw_target > 10_000_000_000:
            return round(raw_target/1000)  # must be an absolute timestamp in milliseconds
        else:
            return raw_target

    def change_request(self, new_target=None, new_delay=None, new_rawtx=[], print_answer=True):
        if self.wallettoken is None and self.api_key is None:
            print('Cant change request if wallettoken and API key is not set.')
            raise Exception('Unauthorized API call: wallettoken and API key not set.')

        query = self._create_change_query(BitpostRequest._to_epoch(new_target), new_delay, new_rawtx)
        answer = requests.put(query, data=str(new_rawtx))
        if print_answer:
            print("status code: " + str(answer.status_code))
            print(str(answer.json()))

        if answer != 200:
            return answer.json()

        self.absolute_epoch_target = BitpostRequest._to_epoch(new_target)
        self.delay = new_delay
        if new_rawtx != None:
            self.rawTxs += new_rawtx
        return answer.json()

    def _create_change_query(self, absolute_epoch_target, new_delay, new_rawtx):
        if self.wallettoken is None or self.id is None:
            print('Cant change a request without its id and wallettoken!')
            raise Exception('Invalid request change.')

        query = self.baseURL + '/request?&wallettoken=' + self.wallettoken + '&id=' + self.id
        if absolute_epoch_target is not None:
            query += '&target=' + str(absolute_epoch_target)

        if new_delay is None:
            query += '&query=' + str(new_delay)

        if self.api_key is not None:
            query += '&key=' + self.api_key

        return query

    def _create_query(self):
        query = self.baseURL + "/request?target=" + str(self.absolute_epoch_target) + "&delay=" + str(self.delay)

        if self.wallettoken is not None:
            query += '&wallettoken=' + self.wallettoken

        if self.broadcast_lowest_feerate:
            query += '&broadcast=' + str(0)

        if self.api_key is not None:
            query += '&key=' + self.api_key
        return query

    def send_request(self, print_before=True, print_answer=True):
        query = self._create_query()

        if print_before:
            print("feerates = " + str(self.feerates))
            print(query)
            print('Sending ' + str(len(self.rawTxs)) + ' signed transactions...')

        data = {}
        data['rawtxs'] = self.rawTxs
        data['notifications'] = self.notifications
        answer = requests.post(query, headers={'content-encoding': 'gzip'}, data=gzip.compress(bytes(str(data), 'utf-8')))

        if print_answer:
            print("status code: " + str(answer.status_code))
            print(str(answer.json()))

        if answer.status_code < 400:
            self.id = answer.json()['data']['id']
        self.answer = answer.json()


        return answer

    def cancel_request(self):
        if self.id == None:
            print('Cant cancel request... no id found')
            return
        query = self.baseURL + "/request?wallettoken=" + self.wallettoken + "&id=" + self.id
        answer = requests.delete(query)
        if answer.status_code >=400:
            print('Failed to cancel request with id=' + self.id)

    # Warning: untested feature. Currently supported platforms are: twitter (DM), email, webhook
    def add_notification(self, platform, address, subscription=None):
        platforms = set([channel['platform'] for channel in self.notifications])
        if not platform in platforms:
            subscriptions = []
            if subscription != None:
                subscriptions = [{"name": subscription}]
            self.notifications.append({"platform": platform, "address": address, "subscriptions": subscriptions})
        elif subscription != None:
            channel = [ch for ch in self.notifications if ch['platform'] == platform][0]
            existing_subs = [sub['name'] for sub in channel['subscriptions']]
            if subscription not in existing_subs:
                channel['subscriptions'].append({'name': subscription})
