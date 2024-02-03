# Galxe AIO

 - Link Twitter account
 - Link email: IMAP or mail3.me
 - Complete Galxe tasks
 - Claim Galxe points and gas-less OATs
 - Quiz solver
 - Accounts statistics

### Supported tasks:
 - Twitter: Follow, Retweet, Like
 - Visit link
 - Solve quiz
 - Follow Galxe space

### Follow: https://t.me/thelaziestcoder

### Settings
 - `files/evm_wallets.txt` - Wallets with EVM private keys
 - `files/proxies.txt` - Corresponding proxies for wallets
 - `files/twitters.txt` - Corresponding twitters for wallets
 - `files/emails.txt` - Corresponding emails for wallets
 - `config.toml` - Custom settings

### Config
 - `FAKE_TWITTER` - Verify Twitter tasks without real Twitter actions
 - `GALXE_CAMPAIGN_IDS` - Campaigns to complete, parent campaigns are supported
 - `HIDE_UNSUPPORTED` - Don't log unsuccessful completing of unsupported tasks

### Run

Python version: 3.10, 3.11

Installing virtual env: \
`python3 -m venv venv`

Activating:
 - Mac/Linux - `source venv/bin/activate`
 - Windows - `.\venv\Scripts\activate`

Installing all dependencies: \
`pip install -r requirements.txt` \
`playwright install`

Run main script: \
`python main.py`

Run twitter checker: \
`python checker.py`

### Results

`results/` - Folder with results of run \
`logs/` - Folder with logs of run \
`storage/` - Local database

### Donate :)

TRC-20 - `TX7yeJVHwhNsNy4ksF1pFRFnunF1aFRmet` \
ERC-20 - `0x5aa3c82045f944f5afa477d3a1d0be3c96196319`
