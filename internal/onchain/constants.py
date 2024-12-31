import os
import json


def read_file(path):
    return open(os.path.join(os.path.dirname(__file__), path), 'r', encoding='utf-8')


SCANS = {
    'Ethereum': 'https://etherscan.io',
    'Optimism': 'https://optimistic.etherscan.io',
    'BSC': 'https://bscscan.com',
    'Gnosis': 'https://gnosisscan.io',
    'Polygon': 'https://polygonscan.com',
    'Fantom': 'https://ftmscan.com',
    'Arbitrum': 'https://arbiscan.io',
    'Avalanche': 'https://snowtrace.io',
    'zkSync': 'https://explorer.zksync.io',
    'Linea': 'https://lineascan.build',
    'Base': 'https://basescan.org',
    'zkEVM': 'https://zkevm.polygonscan.com',
    'Scroll': 'https://scrollscan.com',
    'Gravity': 'https://explorer.gravity.xyz',
}

ZERO_ADDRESS = '0x0000000000000000000000000000000000000000'

SPACE_STATION_ABI = json.load(read_file('abi/space_station.json'))
LOYALTY_POINTS_ABI = json.load(read_file('abi/loyalty_points.json'))

EIP1559_CHAINS = ['Ethereum', 'Optimism', 'Polygon', 'Arbitrum', 'Linea', 'Base', 'Scroll']
