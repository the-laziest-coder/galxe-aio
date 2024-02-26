from typing import Tuple, Optional
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
from eth_account import Account as EvmAccount
from eth_account.messages import encode_defunct

from ..utils import plural_str


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
    discord_token: str = ''
    twitter_error: bool = False
    discord_error: bool = False
    points: dict[str, Tuple[str, int, Optional[bool]]] = field(default_factory=dict)
    nfts: dict[str, Optional[int]] = field(default_factory=dict)
    actual_campaigns: list[str] = field(default_factory=list)
    spaces_points: dict[str, Tuple[str, int, int]] = field(default_factory=dict)

    def sign_message(self, msg):
        return EvmAccount().sign_message(encode_defunct(text=msg), self.evm_private_key).signature.hex()

    @property
    def actual_points(self):
        return {k: v for k, v in self.points.items() if k in self.actual_campaigns}

    def str_stats(self) -> str:
        stats = [(n, self.campaign_points_str(c_id, with_nft=False), self.nfts.get(c_id))
                 for c_id, (n, _, _) in self.actual_points.items()]
        total = sum(v for _, v, _ in self.actual_points.values())
        total_nfts = sum(v for _, _, v in stats if v is not None)
        if not any(v is not None for _, _, v in stats):
            total_nfts = None
        stats.append(('Total', total, total_nfts))
        return ''.join([f'\t{name}: {pv} Points{", " + plural_str(nv, "NFT") if nv is not None else ""}\n'
                        for name, pv, nv in stats])[:-1]

    def campaign_points(self, campaign_id) -> int:
        return self.points.get(campaign_id, ('', 0, None))[1]

    def campaign_points_str(self, campaign_id, with_nft=True) -> str:
        points = self.points.get(campaign_id)
        if not points:
            return '0'
        s = str(points[1])
        if points[2] is not None:
            s += ' / ' + STATUS_BY_BOOL[points[2]]
        nft_cnt = self.nfts.get(campaign_id)
        if with_nft and nft_cnt is not None:
            s += f' / {nft_cnt}'
        return s

    @property
    def twitter_error_s(self):
        return '🔴' if self.twitter_error else ''

    @property
    def discord_error_s(self):
        return '🔴' if self.discord_error else ''
