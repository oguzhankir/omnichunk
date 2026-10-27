
import random
import time
import json
import base64
import blowfish
import requests
from requests.adapters import HTTPAdapter

from .errors import PandoraException


DEFAULT_API_HOST = "tuner.pandora.com/services/json/"


# This decorator is a temporary workaround for handling SysCallErrors, see:
# https://github.com/shazow/urllib3/issues/367. Should be removed once a fix is
# applied in urllib3.
def retries(max_tries, exceptions=(Exception,)):
    
    def decorator(func):
        def function(*args, **kwargs):

            retries_left = max_tries
            while retries_left > 0:
                try:
                    retries_left -= 1
                    return func(*args, **kwargs)

                except exceptions as exc:
                    # Don't retry for PandoraExceptions - unlikely that result
                    # will change for same set of input parameters.
                    if isinstance(exc, PandoraException):
                        raise
                    if retries_left > 0:
                        time.sleep(delay_exponential(
                            0.5, 2, max_tries - retries_left))
                    else:
                        raise

        return function

    return decorator


def delay_exponential(base, growth_factor, attempts):
    
    if base == 'rand':
        base = random.random()
    elif base <= 0:
        raise ValueError("The 'base' param must be greater than 0, "
                         "got: {}".format(base))
    time_to_sleep = base * (growth_factor ** (attempts - 1))
    return time_to_sleep


class RetryingSession(requests.Session):
    

    def __init__(self):
        super().__init__()
        self.mount('https://', HTTPAdapter(max_retries=3))
        self.mount('http://', HTTPAdapter(max_retries=3))


class APITransport:
    

    API_VERSION = "5"

    REQUIRE_RESET = ("auth.partnerLogin", )
    NO_ENCRYPT = ("auth.partnerLogin", )
    REQUIRE_TLS = ("auth.partnerLogin", "auth.userLogin",
                   "station.getPlaylist", "user.createUser")

    def __init__(self, cryptor, api_host=DEFAULT_API_HOST, proxy=None):
        self.cryptor = cryptor
        self.api_host = api_host
        self._http = RetryingSession()

        if proxy:
            self._http.proxies = {"http": proxy, "https": proxy}

        self.reset()

    def reset(self):
        self.partner_auth_token = None
        self.user_auth_token = None

        self.partner_id = None
        self.user_id = None

        self.start_time = None
        self.server_sync_time = None

    def set_partner(self, data):
        self.sync_time = data["syncTime"]
        self.partner_auth_token = data["partnerAuthToken"]
        self.partner_id = data["partnerId"]

    def set_user(self, data):
        self.user_id = data["userId"]
        self.user_auth_token = data["userAuthToken"]

    @property
    def auth_token(self):
        if self.user_auth_token:
            return self.user_auth_token

        if self.partner_auth_token:
            return self.partner_auth_token

        return None

    @property
    def sync_time(self):
        if not self.server_sync_time:
            return None

        return int(self.server_sync_time + (time.time() - self.start_time))

    def remove_empty_values(self, data):
        return {k: v for k, v in data.items() if v is not None}

    @sync_time.setter
    def sync_time(self, sync_time):
        self.server_sync_time = self.cryptor.decrypt_sync_time(sync_time)

    def _start_request(self, method):
        if method in self.REQUIRE_RESET:
            self.reset()

        if not self.start_time:
            self.start_time = int(time.time())

    def _make_http_request(self, url, data, params):
        try:
            data = data.encode("utf-8")
        except AttributeError:
            pass

        params = self.remove_empty_values(params)

        result = self._http.post(url, data=data, params=params)
        result.raise_for_status()
        return result.content

    def test_url(self, url):
        return self._http.head(url).status_code == requests.codes.OK

    def _build_params(self, method):
        return {
            "method": method,
            "auth_token": self.auth_token,
            "partner_id": self.partner_id,
            "user_id": self.user_id,
        }

    def _build_url(self, method):
        return "{}://{}".format(
            "https" if method in self.REQUIRE_TLS else "http",
            self.api_host)

    def _build_data(self, method, data):
        data["userAuthToken"] = self.user_auth_token

        if not self.user_auth_token and self.partner_auth_token:
            data["partnerAuthToken"] = self.partner_auth_token

        data["syncTime"] = self.sync_time
        data = json.dumps(self.remove_empty_values(data))

        if method not in self.NO_ENCRYPT:
            data = self.cryptor.encrypt(data)

        return data

    def _parse_response(self, result):
        result = json.loads(result.decode("utf-8"))

        if result["stat"] == "ok":
            return result["result"] if "result" in result else None
        else:
            raise PandoraException.from_code(result["code"], result["message"])

    @retries(3)
    def __call__(self, method, **data):
        self._start_request(method)

        url = self._build_url(method)
        data = self._build_data(method, data)
        params = self._build_params(method)
        result = self._make_http_request(url, data, params)

        return self._parse_response(result)


class BlowfishCryptor:
    

    block_size = 8

    def _add_padding(self, data):
        pad_size = self.block_size - (len(data) % self.block_size)
        padding = (chr(pad_size) * pad_size).encode("ascii")
        return data.encode("utf-8") + padding

    @staticmethod
    def _strip_padding(data):
        pad_size = int(data[-1])

        computed = b"".join([chr(pad_size).encode("ascii")] * pad_size)
        if not data[-pad_size:] == computed:
            raise ValueError('Invalid padding')

        return data[:-pad_size]


class PurePythonBlowfish(BlowfishCryptor):
    

    def __init__(self, key):
        self.cipher = blowfish.Cipher(key.encode("ascii"))

    def decrypt(self, data, strip_padding=True):
        data = b"".join(self.cipher.decrypt_ecb(data))
        return self._strip_padding(data) if strip_padding else data

    def encrypt(self, data):
        return b"".join(self.cipher.encrypt_ecb(self._add_padding(data)))


class Encryptor:
    

    def __init__(self, in_key, out_key, crypto_class=PurePythonBlowfish):
        self.bf_out = crypto_class(out_key)
        self.bf_in = crypto_class(in_key)

    @staticmethod
    def _decode_hex(data):
        return base64.b16decode(data.encode("ascii").upper())

    @staticmethod
    def _encode_hex(data):
        return base64.b16encode(data).lower()

    def decrypt(self, data):
        return json.loads(self.bf_out.decrypt(self._decode_hex(data)))

    def decrypt_sync_time(self, data):
        return int(self.bf_in.decrypt(self._decode_hex(data), False)[4:-2])

    def encrypt(self, data):
        return self._encode_hex(self.bf_out.encrypt(data))
