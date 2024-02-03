from typing import Dict
from web3.providers.async_rpc import AsyncHTTPProvider

from ..vars import USER_AGENT


class AsyncHTTPProviderWithUA(AsyncHTTPProvider):

    def __init__(
        self,
        endpoint_uri: str = None,
        request_kwargs=None,
    ) -> None:
        super().__init__(endpoint_uri, request_kwargs)

    @classmethod
    def get_request_headers(cls) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }
