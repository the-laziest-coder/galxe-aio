import email
from email.header import decode_header
from email.message import Message
from typing import Optional, Tuple
from loguru import logger
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
            try:
                await self.imap.close()
            except Exception as e:
                logger.warning(f'{self.account.idx}) Failed to close IMAP client: {str(e)}')

    def username(self) -> str:
        return self.account.email_username

    async def _login(self):
        email_domain = self.account.email_username.split('@')[1]
        if email_domain not in IMAP_SERVERS:
            raise Exception(f'Imap server for {email_domain} not found. Add it in internal/email/constants.py')
        self.imap = aioimaplib.IMAP4_SSL(IMAP_SERVERS[email_domain])
        await self.imap.wait_hello_from_server()
        await self.imap.login(self.account.email_username, self.account.email_password)
        await self.imap.select()

    async def _find_email(self, folder: str, subject_condition_func) -> Tuple[Optional[str], Optional[str]]:
        _, messages = await self.imap.select(folder)
        msg_cnt = 0
        for message in messages:
            if message.endswith(b'EXISTS'):
                msg_cnt = int(message.split()[0])
                break
        for i in range(msg_cnt, 0, -1):
            res, msg = await self.imap.fetch(str(i), '(RFC822)')
            if res != 'OK':
                continue
            raw_email = msg[1]
            msg = email.message_from_bytes(raw_email)
            subject, encoding = decode_header(msg['Subject'])[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding if encoding else 'utf-8')
            if subject_condition_func(subject):
                return subject, self.get_email_body(msg)
        return None, None

    def get_email_body(self, msg: Message):
        if msg.is_multipart():
            return self.get_email_body(msg.get_payload(0))
        return msg.get_payload(decode=True).decode()
