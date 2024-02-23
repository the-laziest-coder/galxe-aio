import asyncio
from loguru import logger
from web3 import Web3
from web3.exceptions import TransactionNotFound
from web3.contract.async_contract import AsyncContractConstructor

from ..models import AccountInfo
from ..utils import async_retry, get_proxy_url, get_w3, to_bytes
from ..config import RPCs

from .constants import SCANS, EIP1559_CHAINS, SPACE_STATION_ABI


class OnchainAccount:

    def __init__(self, account: AccountInfo, chain: str):
        self.idx = account.idx
        self.account = account
        self.private_key = account.evm_private_key
        self.proxy = get_proxy_url(self.account.proxy)
        self.chain = chain
        self.w3 = get_w3(RPCs[chain], self.proxy)

    async def close(self):
        pass

    async def __aenter__(self) -> "OnchainAccount":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    @async_retry
    async def _build_and_send_tx(self, func: AsyncContractConstructor, **tx_vars):
        if self.chain in EIP1559_CHAINS:
            max_priority_fee = await self.w3.eth.max_priority_fee
            max_priority_fee = int(max_priority_fee * 2)
            base_fee_per_gas = int((await self.w3.eth.get_block("latest"))["baseFeePerGas"])
            max_fee_per_gas = max_priority_fee + int(base_fee_per_gas * 2)
            gas_vars = {'maxPriorityFeePerGas': max_priority_fee, 'maxFeePerGas': max_fee_per_gas}
        else:
            gas_vars = {'gasPrice': await self.w3.eth.gas_price}
        tx = await func.build_transaction({
            'from': self.account.evm_address,
            'nonce': await self.w3.eth.get_transaction_count(self.account.evm_address),
            'gas': 0,
            **gas_vars,
            **tx_vars,
        })
        try:
            estimate = await self.w3.eth.estimate_gas(tx)
            tx['gas'] = int(estimate * 1.2)
        except Exception as e:
            raise Exception(f'Tx simulation failed: {str(e)}')

        signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
        tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)

        return tx_hash

    async def _tx_verification(self, tx_hash, action, poll_latency=1):
        logger.info(f'{self.idx}) {action} - Tx sent. Waiting for 120s')
        time_passed = 0
        tx_link = f'{SCANS.get(self.chain, "")}/tx/{tx_hash.hex()}'
        while time_passed < 120:
            try:
                tx_data = await self.w3.eth.get_transaction_receipt(tx_hash)
                if tx_data is not None:
                    if tx_data.get('status') == 1:
                        logger.success(f'{self.idx}) {action} - Successful tx: {tx_link}')
                        return
                    msg = f'Failed tx: {tx_link}'
                    logger.error(f'{self.idx}) {msg}')
                    raise Exception(msg)
            except TransactionNotFound:
                pass

            time_passed += poll_latency
            await asyncio.sleep(poll_latency)

        msg = f'{action} - Pending tx: {tx_link}'
        logger.warning(f'{self.idx}) {msg}')
        raise Exception(msg)

    async def build_and_send_tx(self, func: AsyncContractConstructor, action='', **tx_vars) -> str:
        tx_hash = await self._build_and_send_tx(func, **tx_vars)
        await self._tx_verification(tx_hash, action)
        return tx_hash.hex()

    @async_retry
    async def claim(self, space_station_address, number_id, signature, nft_core_address, verify_id, powah) -> str:
        try:
            space_station_address = Web3.to_checksum_address(space_station_address)
            nft_core_address = Web3.to_checksum_address(nft_core_address)
            contract = self.w3.eth.contract(space_station_address, abi=SPACE_STATION_ABI)

            tx_hash = await self.build_and_send_tx(
                contract.functions.claim(number_id, nft_core_address, verify_id, powah, to_bytes(signature)),
                'Claim'
            )
            return tx_hash

        except Exception as e:
            raise Exception(f'Failed to claim: {str(e)}')
