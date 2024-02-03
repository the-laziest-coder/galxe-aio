from typing import Optional
from loguru import logger

from ..tls import TLSClient
from ..models import AccountInfo
from ..utils import get_proxy_url

from .base import BaseClient
from .constants import MAIL3_SIGN_MESSAGE_FORMAT


class Mail3Client(BaseClient):

    API_URL = 'https://api.mail3.me/api/v1/'

    def __init__(self, account: AccountInfo):
        super().__init__(account, 'Mail3.me')
        self.proxy = get_proxy_url(self.account.proxy)
        self.tls = TLSClient(account, {
            'origin': 'https://app.mail3.me',
            'referrer': 'https://app.mail3.me/',
        })

    async def close(self):
        await self.tls.close()

    def username(self) -> str:
        return f'{self.account.evm_address}@mail3.me'

    async def _login(self):
        nonce, resp = await self.tls.get(
            f'{self.API_URL}/address_nonces/{self.account.evm_address}',
            [200, 404], lambda r: (r.get('nonce') or r['metadata'].get('nonce'), r)
        )
        is_new = 'nonce' not in resp
        message = MAIL3_SIGN_MESSAGE_FORMAT.replace('{{nonce}}', str(nonce))
        signature = self.account.sign_message(message)
        payload = {
            'address': self.account.evm_address,
            'message': message,
            'signature': signature,
        }
        if is_new:
            logger.info(f'{self.account.idx}) Registering Mail3.me account')
            await self.tls.post(f'{self.API_URL}/registrations', [200, 204, 400], json=payload)
            logger.info(f'{self.account.idx}) Registered')
        jwt = await self.tls.post(f'{self.API_URL}/sessions', [200], lambda r: r['jwt'], json=payload)
        self.tls.update_headers({'Authorization': 'Bearer ' + jwt})

    async def _get_message_body(self, message_id: str) -> str:
        message = await self.tls.get(f'{self.API_URL}/mailbox/account/message/{message_id}', [200])
        return message['text']['html']

    async def _find_email(self, folder: str, subject_condition_func) -> Optional[str]:
        messages = await self.tls.post(f'{self.API_URL}/mailbox/account/search', [200], lambda r: r['messages'], json={
            'path': folder,
            'pageSize': 20,
            'page': 0,
            'search': {'unseen': True},
        })

        for message in messages:
            if subject_condition_func(message.get('subject')):
                return await self._get_message_body(message.get('id'))

        return None

