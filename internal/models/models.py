from typing import Tuple, Optional
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
from eth_account import Account as EvmAccount
from eth_account.messages import encode_defunct


STATUS_BY_BOOL = {
    False: '❌',
    True: '✅',
}


@dataclass_json
@dataclass
class AccountInfo:
    idx: int = 0
    evm_address: str = ''
    evm_private_key: str = ''
    proxy: str = ''
    twitter_auth_token: str = ''
    email_username: str = ''
    email_password: str = ''
    twitter_error: bool = False
    points: dict[str, Tuple[str, int, Optional[bool]]] = field(default_factory=dict)

    def sign_message(self, msg):
        return EvmAccount().sign_message(encode_defunct(text=msg), self.evm_private_key).signature.hex()

    def str_stats(self) -> str:
        stats = {n: self.campaign_points_str(c_id) for c_id, (n, _, _) in self.points.items()}
        return ''.join([f'\t{name}: {value}\n' for name, value in stats.items()])[:-1]

    def campaign_points_str(self, campaign_id) -> str:
        points = self.points.get(campaign_id)
        if not points:
            return '0'
        s = str(points[1])
        if points[2] is not None:
            s += ' / ' + STATUS_BY_BOOL[points[2]]
        return s

    @property
    def twitter_error_s(self):
        return '🔴' if self.twitter_error else ''
