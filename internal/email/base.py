import asyncio
from loguru import logger
from typing import Optional

from ..models import AccountInfo

from .constants import FOLDERS


class BaseClient:

    def __init__(self, account: AccountInfo, email_type: str):
        self.account = account
        self.email_type = email_type

    async def close(self):
        raise NotImplementedError()

    async def __aenter__(self) -> "BaseClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    def username(self) -> str:
        raise NotImplementedError()

    async def _login(self):
        raise NotImplementedError()

    async def login(self):
        try:
            await self._login()
            logger.info(f'{self.account.idx}) Successfully logged in {self.email_type} email')
        except Exception as e:
            raise Exception(f'Email login failed: {str(e)}')

    async def _find_email(self, folder: str, subject_condition_func) -> Optional[str]:
        raise NotImplementedError()

    async def find_email(self, subject_condition_func) -> Optional[str]:
        try:
            for folder in FOLDERS:
                result = await self._find_email(folder, subject_condition_func)
                if result is not None:
                    return result
            return None
        except Exception as e:
            raise Exception(f'Find email failed: {str(e)}')

    async def wait_for_email(self, subject_condition_func, timeout=90, polling=10) -> Optional[str]:
        exc_cnt = 0
        for t in range(0, timeout + 1, polling):
            await asyncio.sleep(polling)
            try:
                result = await self.find_email(subject_condition_func)
                exc_cnt = 0
            except Exception as e:
                exc_cnt += 1
                if exc_cnt > 2:
                    raise Exception(f'Wait for email failed: {str(e)}')
                logger.warning(f'{self.account.idx}) Wait for email failed: {str(e)}')
                result = None

            if result is not None:
                return result

            logger.info(f'{self.account.idx}) Email not found. Waiting for {polling}s')

        raise Exception(f'Email was not found')
