import aiohttp
import asyncio

from termcolor import cprint
from loguru import logger
from typing import Tuple
from eth_account import Account as EthAccount

from internal.storage import AccountStorage
from internal.models import AccountInfo
from internal.twitter import Twitter
from internal.config import THREADS_NUM, CHECKER_UPDATE_STORAGE
from internal.utils import async_retry, log_long_exc


@async_retry
async def change_ip(link: str):
    async with aiohttp.ClientSession() as sess:
        async with sess.get(link) as resp:
            if resp.status != 200:
                raise Exception(f'Failed to change ip: Status = {resp.status}. Response = {await resp.text()}')


async def check_account(account_data: Tuple[int, Tuple[str, str, str]]):
    idx, (evm_wallet, proxy, twitter_token, _) = account_data
    address = EthAccount().from_key(evm_wallet).address
    logger.info(f'{idx}) Processing {address}')

    account_info = AccountInfo(address=address, proxy=proxy, twitter_auth_token=twitter_token)

    if '|' in account_info.proxy:
        change_link = account_info.proxy.split('|')[1]
        await change_ip(change_link)
        logger.info(f'{idx}) Successfully changed ip')

    twitter = Twitter(account_info)
    await twitter.start()

    await twitter.follow('elonmusk')

    return True


async def process_batch(bid: int, batch, async_func):
    failed = []
    for idx, d in enumerate(batch):
        try:
            await async_func(d)
        except Exception as e:
            e_msg = str(e)
            if 'Could not authenticate you' in e_msg or 'account is suspended' in e_msg \
                    or 'account has been locked' in e_msg:
                failed.append(d)
            await log_long_exc(d[0], 'Process account error', e)
    return failed


async def process(batches, async_func):
    tasks = []
    for idx, b in enumerate(batches):
        tasks.append(asyncio.create_task(process_batch(idx, b, async_func)))
    return await asyncio.gather(*tasks)


def main():
    with open('files/evm_wallets.txt', 'r', encoding='utf-8') as file:
        evm_wallets = file.read().splitlines()
        evm_wallets = [w.strip() for w in evm_wallets]
    with open('files/proxies.txt', 'r', encoding='utf-8') as file:
        proxies = file.read().splitlines()
        proxies = [p.strip() for p in proxies]
        proxies = [p if '://' in p.split('|')[0] else 'http://' + p for p in proxies]
    with open('files/twitters.txt', 'r', encoding='utf-8') as file:
        twitters = file.read().splitlines()
        twitters = [t.strip() for t in twitters]
    with open('files/emails.txt', 'r', encoding='utf-8') as file:
        emails = file.read().splitlines()
        emails = [e.strip() for e in emails]

    if len(evm_wallets) != len(proxies):
        logger.error('Proxies count does not match wallets count')
        return
    if len(evm_wallets) != len(twitters):
        logger.error('Twitter count does not match wallets count')
        return
    if len(evm_wallets) != len(emails):
        logger.error('Emails count does not match wallets count')
        return

    def get_batches(threads: int = THREADS_NUM):
        _data = list(enumerate(list(zip(evm_wallets, proxies, twitters, emails)), start=1))
        _batches = [[] for _ in range(threads)]
        for _idx, d in enumerate(_data):
            _batches[_idx % threads].append(d)
        return _batches

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    results = loop.run_until_complete(process(get_batches(), check_account))

    failed_twitter = set()
    for result in results:
        for r in result:
            failed_twitter.add(r[1][2])

    storage = AccountStorage('storage/data.json')
    storage.init()

    failed_cnt = 0

    print()

    open('results/working_evm_wallets.txt', 'w', encoding='utf-8').close()
    open('results/working_proxies.txt', 'w', encoding='utf-8').close()
    open('results/working_twitters.txt', 'w', encoding='utf-8').close()
    open('results/working_emails.txt', 'w', encoding='utf-8').close()
    for evm_wallet, proxy, twitter, email in zip(evm_wallets, proxies, twitters, emails):
        if twitter in failed_twitter:
            failed_cnt += 1
            address = EthAccount().from_key(evm_wallet).address
            logger.info(f'Removed for EVM address {address} twitter token {twitter}, proxy {proxy}')
            if CHECKER_UPDATE_STORAGE:
                storage.remove(address)
            continue
        with open('results/working_evm_wallets.txt', 'a', encoding='utf-8') as file:
            file.write(f'{evm_wallet}\n')
        with open('results/working_proxies.txt', 'a', encoding='utf-8') as file:
            file.write(f'{proxy}\n')
        with open('results/working_twitters.txt', 'a', encoding='utf-8') as file:
            file.write(f'{twitter}\n')
        with open('results/working_emails.txt', 'a', encoding='utf-8') as file:
            file.write(f'{email}\n')

    logger.info(f'Total failed count: {failed_cnt}')

    if CHECKER_UPDATE_STORAGE:
        storage.save()

    print()


if __name__ == '__main__':
    cprint('###############################################################', 'cyan')
    cprint('#################', 'cyan', end='')
    cprint(' https://t.me/thelaziestcoder ', 'magenta', end='')
    cprint('################', 'cyan')
    cprint('#################', 'cyan', end='')
    cprint(' https://t.me/thelaziestcoder ', 'magenta', end='')
    cprint('################', 'cyan')
    cprint('#################', 'cyan', end='')
    cprint(' https://t.me/thelaziestcoder ', 'magenta', end='')
    cprint('################', 'cyan')
    cprint('###############################################################\n', 'cyan')
    main()
