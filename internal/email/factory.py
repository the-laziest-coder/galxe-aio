from ..models import AccountInfo

from .base import BaseClient
from .imap import IMAPClient
from .mail3 import Mail3Client


class Email:

    @classmethod
    def from_account(cls, account: AccountInfo) -> BaseClient:
        if 'mail3.me' in account.email_username:
            return Mail3Client(account)
        return IMAPClient(account)
