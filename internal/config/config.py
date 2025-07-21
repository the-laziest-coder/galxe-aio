import csv
import sys
import toml
import platform
import subprocess
from importlib.metadata import version


cfg = toml.load(open('config.toml', 'r', encoding='utf-8'))


WAIT_BETWEEN_ACCOUNTS = cfg.get('WAIT_BETWEEN_ACCOUNTS')
MAX_TRIES = cfg.get('MAX_TRIES')
CAP_MONSTER_API_KEY = cfg.get('CAP_MONSTER_API_KEY')
TWO_CAPTCHA_API_KEY = cfg.get('TWO_CAPTCHA_API_KEY')
CAP_SOLVER_API_KEY = cfg.get('CAP_SOLVER_API_KEY')
THREADS_NUM = cfg.get('THREADS_NUM')
DISABLE_SSL = cfg.get('DISABLE_SSL')
CHECKER_UPDATE_STORAGE = cfg.get('CHECKER_UPDATE_STORAGE')
UPDATE_STORAGE_ACCOUNT_INFO = cfg.get('UPDATE_STORAGE_ACCOUNT_INFO')
SKIP_FIRST_ACCOUNTS = cfg.get('SKIP_FIRST_ACCOUNTS')
RANDOM_ORDER = cfg.get('RANDOM_ORDER')
FAKE_TWITTER = cfg.get('FAKE_TWITTER')
FORCE_LINK_EMAIL = cfg.get('FORCE_LINK_EMAIL')
GALXE_CAMPAIGN_IDS = cfg.get('GALXE_CAMPAIGN_IDS')
WAIT_BETWEEN_TASKS = cfg.get('WAIT_BETWEEN_TASKS')
REFERRAL_LINKS = [line.strip() for line in open('files/referral_links.txt', 'r', encoding='utf-8').read().splitlines()
                  if line.strip() != '']
with open('files/surveys.csv', 'r', encoding='utf-8') as file:
    reader = csv.reader(file)
    SURVEYS = [row for row in reader]
SURVEYS = {row[0].lower(): row[1:] for row in SURVEYS}
HIDE_UNSUPPORTED = cfg.get('HIDE_UNSUPPORTED')
SPACES_STATS = cfg.get('SPACES_STATS')
RPCs = cfg.get('RPCs')


curl_cffi_installed_version = version('curl_cffi')
if platform.system() == 'Windows':
    if curl_cffi_installed_version == '0.8.1b8':
        print('\nNeed to downgrade curl-cffi version for Windows')
        subprocess.check_call([sys.executable, "-m", "pip", "install", 'curl_cffi==0.7.4'])
        print('Successfully installed curl_cffi==0.7.4\n')
else:
    if curl_cffi_installed_version != '0.8.1b8':
        print('\nNeed to upgrade curl-cffi version for Mac/Linux')
        subprocess.check_call([sys.executable, "-m", "pip", "install", 'curl_cffi==0.8.1b8'])
        print('Successfully installed curl_cffi==0.8.1b8\n')
