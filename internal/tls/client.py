import platform
import warnings
from curl_cffi.requests import AsyncSession, BrowserType

from ..models import AccountInfo
from ..config import DISABLE_SSL
from ..utils import async_retry, get_proxy_url
from ..vars import USER_AGENT, SEC_CH_UA, SEC_CH_UA_PLATFORM


warnings.filterwarnings('ignore', module='curl_cffi')


if platform.system() == 'Windows':
    IMPERSONATE = BrowserType.chrome124
else:
    IMPERSONATE = BrowserType.chrome131


def get_default_headers():
    return {
        'accept': '*/*',
        'accept-encoding': 'gzip, deflate, br',
        'accept-language': 'en-US,en;q=0.9',
        'sec-ch-ua': SEC_CH_UA,
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': SEC_CH_UA_PLATFORM,
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'user-agent': USER_AGENT,
    }


class TLSClient:

    def __init__(self, account: AccountInfo, custom_headers: dict = None, custom_cookies: dict = None, debug=False):
        self.account = account
        self._headers = {}
        self.proxy = get_proxy_url(self.account.proxy)
        self.proxies = {'http': self.proxy, 'https': self.proxy} if self.proxy else {}
        headers = get_default_headers()
        if custom_headers is not None:
            headers.update(custom_headers)
        self.sess = AsyncSession(
            proxies=self.proxies,
            headers=headers,
            cookies=custom_cookies,
            impersonate=IMPERSONATE,
        )
        self.debug = debug

    async def close(self):
        await self.sess.close()

    @classmethod
    def _handle_response(cls, resp_raw, acceptable_statuses=None, resp_handler=None, with_text=False):
        if acceptable_statuses and len(acceptable_statuses) > 0:
            if resp_raw.status_code not in acceptable_statuses:
                raise Exception(f'Bad status code [{resp_raw.status_code}]: Response = {resp_raw.text}')
        try:
            if with_text:
                return resp_raw.text if resp_handler is None else resp_handler(resp_raw.text)
            else:
                return resp_raw.json() if resp_handler is None else resp_handler(resp_raw.json())
        except Exception as e:
            raise Exception(f'{str(e)}: Status = {resp_raw.status_code}. '
                            f'Response saved in logs/errors.txt\n{resp_raw.text}')

    def update_headers(self, new_headers: dict):
        self.sess.headers.update(new_headers)

    @async_retry
    async def _raw_request(self, method, url, debug=False, **kwargs):
        if debug:
            print('tls cookies', self.sess.cookies)
            print('new cookies', kwargs.get('cookies'))
            print('tls headers', self.sess.headers)
            print('new headers', kwargs.get('headers'))
        match method.lower():
            case 'get':
                resp = await self.sess.get(url, **kwargs)
            case 'post':
                resp = await self.sess.post(url, **kwargs)
            case unexpected:
                raise Exception(f'Wrong request method: {unexpected}')
        return resp

    async def request(self, method, url, acceptable_statuses=None, resp_handler=None, with_text=False,
                      raw=False, **kwargs):
        if 'timeout' not in kwargs:
            kwargs.update({'timeout': 60})
        if DISABLE_SSL:
            kwargs.update({'verify': False})
        resp = await self._raw_request(method, url, **kwargs)
        if raw:
            return resp
        return self._handle_response(resp, acceptable_statuses, resp_handler, with_text)

    async def get(self, url, acceptable_statuses=None, resp_handler=None, with_text=False, **kwargs):
        return await self.request('GET', url, acceptable_statuses, resp_handler, with_text, **kwargs)

    async def post(self, url, acceptable_statuses=None, resp_handler=None, with_text=False, **kwargs):
        return await self.request('POST', url, acceptable_statuses, resp_handler, with_text, **kwargs)
