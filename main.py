import sys
import csv
import time
import random
import aiohttp
import asyncio

from termcolor import cprint
from loguru import logger
from datetime import datetime
from typing import Tuple, Optional
from eth_account import Account as EthAccount

from internal.config import WAIT_BETWEEN_ACCOUNTS, THREADS_NUM, \
    SKIP_FIRST_ACCOUNTS, RANDOM_ORDER, UPDATE_STORAGE_ACCOUNT_INFO, GALXE_CAMPAIGN_IDS, SPACES_STATS
from internal.utils import async_retry, wait_a_bit, log_long_exc
from internal.galxe import GalxeAccount
from internal.models import AccountInfo
from internal.storage import AccountStorage


logger.remove()
logger.add(sys.stderr, format='<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | '
                              '<level>{level: <7}</level> | '
                              '<level>{message}</level>')


@async_retry
async def change_ip(idx, link: str):
    async with aiohttp.ClientSession() as sess:
        async with sess.get(link) as resp:
            if resp.status != 200:
                raise Exception(f'Failed to change ip: Status = {resp.status}. Response = {await resp.text()}')
            logger.info(f'{idx}) Successfully changed ip: {await resp.text()}')


async def process_account(account_data: Tuple[int, Tuple[str, str, str, str, str]],
                          storage: AccountStorage):

    idx, (evm_wallet, proxy, twitter_token, email, discord) = account_data

    evm_address = EthAccount().from_key(evm_wallet).address

    logger.info(f'{idx}) Processing: {evm_address}')

    if ':' in email:
        email_username, email_password = tuple(email.split(':'))
    else:
        email_username, email_password = email, ''

    account_info = await storage.get_account_info(evm_address)
    if account_info is None:
        logger.info(f'{idx}) Account info was not saved before')
        account_info = AccountInfo(idx=idx, evm_address=evm_address, evm_private_key=evm_wallet,
                                   proxy=proxy, twitter_auth_token=twitter_token, discord_token=discord,
                                   email_username=email_username, email_password=email_password)
    else:
        if account_info.discord_token == '':
            account_info.discord_token = discord
        if UPDATE_STORAGE_ACCOUNT_INFO:
            account_info.proxy = proxy
            account_info.twitter_auth_token = twitter_token
            account_info.email_username = email_username
            account_info.email_password = email_password
            account_info.discord_token = discord
        logger.info(f'{idx}) Saved account info restored')

    account_info.twitter_error = False
    account_info.discord_error = False
    account_info.actual_campaigns = []

    if '|' in account_info.proxy:
        change_link = account_info.proxy.split('|')[1]
        await change_ip(idx, change_link)

    exc: Optional[Exception] = None

    try:
        async with GalxeAccount(idx, account_info, evm_wallet) as galxe_account:
            logger.info(f'{idx}) Galxe signing in')
            await galxe_account.login()
            logger.info(f'{idx}) Galxe signed in')

            await wait_a_bit()

            for campaign_id in GALXE_CAMPAIGN_IDS:
                await galxe_account.complete_campaign(campaign_id)
                await galxe_account.claim_campaign(campaign_id)

            await wait_a_bit()

            logger.info(f'{idx}) Checking spaces stats')
            await galxe_account.spaces_stats()

    except Exception as galxe_exc:
        exc = Exception(f'Galxe error: {galxe_exc}')

    logger.info(f'{idx}) Account stats:\n{account_info.str_stats()}')

    await storage.set_account_info(evm_address, account_info)

    await storage.async_save()

    if exc is not None:
        raise exc


async def process_batch(bid: int, batch, storage: AccountStorage, async_func, sleep):
    await asyncio.sleep(WAIT_BETWEEN_ACCOUNTS[0] / THREADS_NUM * bid)
    failed = []
    for idx, d in enumerate(batch):
        if sleep and idx != 0:
            await asyncio.sleep(random.uniform(WAIT_BETWEEN_ACCOUNTS[0], WAIT_BETWEEN_ACCOUNTS[1]))
        try:
            await async_func(d, storage)
        except Exception as e:
            failed.append(d)
            await log_long_exc(d[0], 'Process account error', e)
        print()
    return failed


async def process(batches, storage: AccountStorage, async_func, sleep=True):
    tasks = []
    for idx, b in enumerate(batches):
        tasks.append(asyncio.create_task(process_batch(idx, b, storage, async_func, sleep)))
    return await asyncio.gather(*tasks)


def main():
    with open('files/evm_wallets.txt', 'r', encoding='utf-8') as file:
        evm_wallets = file.read().splitlines()
        evm_wallets = [w.strip() for w in evm_wallets]
    with open('files/proxies.txt', 'r', encoding='utf-8') as file:
        proxies = file.read().splitlines()
        proxies = [p.strip() for p in proxies]
        proxies = [p if '://' in p.split('|')[0] or p == '' else 'http://' + p for p in proxies]
    with open('files/twitters.txt', 'r', encoding='utf-8') as file:
        twitters = file.read().splitlines()
        twitters = [t.strip() for t in twitters]
    with open('files/emails.txt', 'r', encoding='utf-8') as file:
        emails = file.read().splitlines()
        emails = [e.strip() for e in emails]
    with open('files/discords.txt', 'r', encoding='utf-8') as file:
        discords = file.read().splitlines()
        discords = [d.strip() for d in discords]

    if len(discords) == 0:
        discords = ['' for _ in evm_wallets]
    if len(evm_wallets) != len(proxies):
        logger.error('Proxies count does not match wallets count')
        return
    if len(evm_wallets) != len(twitters):
        logger.error('Twitter count does not match wallets count')
        return
    if len(evm_wallets) != len(emails):
        logger.error('Emails count does not match wallets count')
        return
    if len(evm_wallets) != len(discords):
        logger.error('Discord count does not match wallets count')
        return

    for idx, w in enumerate(evm_wallets, start=1):
        try:
            _ = EthAccount().from_key(w).address
        except Exception as e:
            logger.error(f'Wrong EVM private key #{idx}: {str(e)}')
            return

    want_only = []

    def get_batches(skip: int = None, threads: int = THREADS_NUM):
        _data = list(enumerate(list(zip(evm_wallets, proxies, twitters, emails, discords)), start=1))
        if skip is not None:
            _data = _data[skip:]
        if skip is not None and len(want_only) > 0:
            _data = [d for d in enumerate(list(zip(evm_wallets, proxies, twitters, emails, discords)), start=1)
                     if d[0] in want_only]
        if RANDOM_ORDER:
            random.shuffle(_data)
        _batches = [[] for _ in range(threads)]
        for _idx, d in enumerate(_data):
            _batches[_idx % threads].append(d)
        return _batches

    storage = AccountStorage('storage/data.json')
    storage.init()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    results = loop.run_until_complete(process(get_batches(SKIP_FIRST_ACCOUNTS), storage, process_account))

    failed = [f[0] for r in results for f in r]

    storage.save()

    print()
    logger.info('Finished')
    logger.info(f'Failed cnt: {len(failed)}')
    logger.info(f'Failed ids: {sorted(failed)}')
    print()

    campaigns = {}
    spaces = {}
    for w in evm_wallets:
        account = storage.get_final_account_info(EthAccount().from_key(w).address)
        if account is None:
            continue
        for c_id, value in account.actual_points.items():
            if c_id not in campaigns:
                campaigns[c_id] = value[0]
        for alias, value in account.spaces_points.items():
            if alias not in spaces:
                spaces[alias] = value[0]
    campaigns = list(campaigns.items())
    spaces = [(alias, name) for alias, name in spaces.items() if not SPACES_STATS or alias in SPACES_STATS]

    csv_data = [['#', 'EVM Address', 'Total Points'] + [n for _, n in campaigns] + ['Twitter Error', 'Discord Error']]
    total = {'total_points': 0, 'twitter_error': 0, 'discord_error': 0}
    spaces_csv_data = [['#', 'EVM Address'], ['#', 'EVM Address']]
    for _, name in spaces:
        spaces_csv_data[0].extend([name, name])
        spaces_csv_data[1].extend(['Points', 'Rank'])
    spaces_total = {alias: 0 for alias, _ in spaces}
    for idx, w in enumerate(evm_wallets, start=1):
        evm_address = EthAccount().from_key(w).address
        account = storage.get_final_account_info(evm_address)
        if account is None:
            csv_data.append([idx, evm_address])
            spaces_csv_data.append([idx, evm_address])
            continue

        points = [account.campaign_points_str(c_id) for c_id, _ in campaigns]
        total_points = sum(account.campaign_points(c_id) for c_id, _ in campaigns)

        total['total_points'] += total_points

        for c_id, _ in campaigns:
            if c_id not in total:
                total[c_id] = [0, None, None]
            if c_id not in account.points:
                continue
            total[c_id][0] += account.points[c_id][1]
            if account.points[c_id][2] is not None:
                if total[c_id][1] is None:
                    total[c_id][1] = 0
                total[c_id][1] += 1 if account.points[c_id][2] else 0
        for c_id, _ in campaigns:
            nfts_cnt = account.nfts.get(c_id)
            if nfts_cnt is None:
                continue
            if total[c_id][2] is None:
                total[c_id][2] = 0
            total[c_id][2] += nfts_cnt

        total['twitter_error'] += 1 if account.twitter_error else 0
        total['discord_error'] += 1 if account.discord_error else 0

        csv_data.append([idx, evm_address, total_points] + points +
                        [account.twitter_error_s, account.discord_error_s])

        spaces_info = []
        for alias, _ in spaces:
            space_points, space_rank = 0, None
            if alias in account.spaces_points:
                space_points, space_rank = account.spaces_points[alias][1], account.spaces_points[alias][2]
            spaces_info.extend([space_points, space_rank])
            spaces_total[alias] += space_points

        spaces_csv_data.append([idx, evm_address] + spaces_info)

    csv_data.append([])
    csv_data.append(['', '', total['total_points']] +
                    [(f'{total[c_id][0]} / {total[c_id][1]}'
                      if total[c_id][1] else str(total[c_id][0])) +
                     f'{" / " + str(total[c_id][2]) if total[c_id][2] is not None else ""}'
                     for c_id, _ in campaigns] + [total['twitter_error'], total['discord_error']])
    csv_data.append(['', '', 'Total Points'] + [n for _, n in campaigns] + ['Twitter Error', 'Discord Error'])

    spaces_csv_data.extend([[], ['', ''], ['', ''], ['', '']])
    for alias, name in spaces:
        spaces_csv_data[-3].extend([spaces_total[alias], ''])
        spaces_csv_data[-2].extend(['Points', 'Rank'])
        spaces_csv_data[-1].extend([name, name])

    run_timestamp = str(datetime.now())
    csv_data.extend([[], ['', 'Timestamp', run_timestamp]])
    spaces_csv_data.extend([[], ['', 'Timestamp', run_timestamp]])

    with open('results/stats.csv', 'w', encoding='utf-8', newline='') as file:
        writer = csv.writer(file, delimiter=';')
        writer.writerows(csv_data)
    with open('results/spaces_stats.csv', 'w', encoding='utf-8', newline='') as file:
        writer = csv.writer(file, delimiter=';')
        writer.writerows(spaces_csv_data)

    logger.info('Campaigns stats are stored in results/stats.csv')
    logger.info('Spaces stats are stored in results/spaces_stats.csv')
    logger.info(f'Timestamp: {run_timestamp}')
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
