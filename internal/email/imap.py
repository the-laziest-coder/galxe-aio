import email
from email.header import decode_header
from typing import Optional
from aioimaplib import aioimaplib

from ..models import AccountInfo

from .base import BaseClient
from .constants import IMAP_SERVERS


class IMAPClient(BaseClient):

    def __init__(self, account: AccountInfo):
        super().__init__(account, 'IMAP')
        self.imap: aioimaplib.IMAP4_SSL | None = None

    async def close(self):
        if self.imap is not None:
            await self.imap.close()

    def username(self) -> str:
        return self.account.email_username

    async def _login(self):
        self.imap = aioimaplib.IMAP4_SSL(IMAP_SERVERS[self.account.email_username.split('@')[1]])
        await self.imap.wait_hello_from_server()
        await self.imap.login(self.account.email_username, self.account.email_password)
        await self.imap.select()

    async def _find_email(self, folder: str, subject_condition_func) -> Optional[str]:
        _, messages = await self.imap.select(folder)
        msg_cnt = int(messages[0].split()[0])
        for i in range(msg_cnt, 0, -1):
            res, msg = await self.imap.fetch(str(i), '(RFC822)')
            if res != 'OK':
                continue
            raw_email = msg[1]
            msg = email.message_from_bytes(raw_email)
            subject, encoding = decode_header(msg['Subject'])[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding)
            if subject_condition_func(subject):
                body = msg.get_payload(decode=True).decode()
                return body
        return None
