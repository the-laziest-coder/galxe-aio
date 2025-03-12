import re
import time
import json
import random
import base64
import asyncio
import colorama
from uuid import uuid4
from faker import Faker
from loguru import logger
from asyncio import Lock
from datetime import datetime, timedelta
from termcolor import colored

from ..vars import GALXE_CAPTCHA_ID
from ..email import Email
from ..models import AccountInfo
from ..storage import Storage
from ..twitter import Twitter, UserNotFound
from ..onchain import OnchainAccount
from ..captcha import solve_geetest
from ..config import FAKE_TWITTER, HIDE_UNSUPPORTED, MAX_TRIES, FORCE_LINK_EMAIL, REFERRAL_LINKS, SURVEYS
from ..utils import wait_a_bit, get_query_param, get_proxy_url, async_retry, log_long_exc, plural_str

from .client import Client
from .fingerprint import fingerprints, captcha_retry
from .utils import random_string_for_entropy
from .models import Recurring, Credential, CredSource, ConditionRelation, QuizType, Gamification, GasType
from .constants import DISCORD_AUTH_URL, GALXE_DISCORD_CLIENT_ID, CHAIN_NAME_MAPPING, VERIFY_TRIES

colorama.init()
Faker.seed(int(time.time() * 1000))
faker = Faker()
faker_lock = asyncio.Lock()

quiz_storage = Storage('storage/quizzes.json')
quiz_storage.init()


class GalxeAccount:

    def __init__(self, idx, account: AccountInfo, private_key: str):
        self.idx = idx
        self.account = account
        self.proxy = get_proxy_url(self.account.proxy)
        self.private_key = private_key
        self.client = Client(account)
        self.twitter = None
        self.profile = None
        self.captcha = None
        self.captcha_lock = Lock()
        self.twitter_credentials_done = set()

    async def close(self):
        await self.client.close()

    async def __aenter__(self) -> "GalxeAccount":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    @async_retry
    async def get_captcha(self):
        try:
            solution = await solve_geetest(
                self.idx, 'https://app.galxe.com/quest', self.account.proxy,
                GALXE_CAPTCHA_ID, str(uuid4()), 4,
                {
                    'captcha_id': GALXE_CAPTCHA_ID,
                    'client_type': 'web',
                    'lang': 'en-us',
                }
            )
            return {
                'lotNumber': solution['lot_number'],
                'captchaOutput': solution['captcha_output'],
                'passToken': solution['pass_token'],
                'genTime': solution['gen_time'],
            }
        except Exception as e:
            raise Exception(f'Failed to solve captcha: {str(e)}')

    async def _get_evm_login_signature(self):
        exp_time = (datetime.utcnow() + timedelta(days=7)).isoformat()[:-3] + 'Z'
        iss_time = datetime.utcnow().isoformat()[:-3] + 'Z'
        msg = f'galxe.com wants you to sign in with your Ethereum account:\n{self.account.evm_address}\n\n' \
              f'Sign in with Ethereum to the app.\n\n' \
              f'URI: https://galxe.com\n' \
              f'Version: 1\n' \
              f'Chain ID: 1\n' \
              f'Nonce: {random_string_for_entropy(96)}\n' \
              f'Issued At: {iss_time}\n' \
              f'Expiration Time: {exp_time}'

        return msg, self.account.sign_message(msg)

    async def sign_in(self):
        msg, signature = await self._get_evm_login_signature()
        await self.client.sign_in(msg, signature)

    @classmethod
    async def fake_username(cls):
        async with faker_lock:
            return faker.user_name()

    async def create_account(self):
        username = await self.fake_username()
        while await self.client.is_username_exist(username):
            username += str(random.randint(0, 9))
        logger.info(f'{self.idx}) Creating Galxe account with {username} username')
        await self.client.create_account(username)

    async def login(self):
        exists = await self.client.galxe_id_exist()
        await self.sign_in()
        if not exists:
            await self.create_account()
        await self.refresh_profile()

    async def refresh_profile(self):
        self.profile = await self.client.basic_user_info()

    async def link_twitter(self, fake_twitter=FAKE_TWITTER):
        existed_twitter_username = self.profile.get('twitterUserName', '')
        if existed_twitter_username != '' and fake_twitter:
            return

        if self.twitter is None:
            try:
                self.twitter = Twitter(self.account)
                await self.twitter.start()
            except Exception as e:
                self.twitter = None
                raise e

        if existed_twitter_username != '':
            if existed_twitter_username.lower() == self.twitter.my_username.lower():
                return
            else:
                logger.info(f'{self.idx}) Another Twitter account already linked with this EVM address: '
                            f'{existed_twitter_username}. Current: {self.twitter.my_username}')

        logger.info(f'{self.idx}) Starting link new Twitter account')

        galxe_id = self.profile.get('id')
        tweet_text = f'Verifying my Twitter account for my #GalxeID gid:{galxe_id} @Galxe \n\n galxe.com/id '

        try:
            try:
                tweet_url = await self.twitter.post_tweet(tweet_text)
            except Exception as e:
                if 'Authorization: Status is a duplicate. (187)' in str(e):
                    logger.info(f'{self.idx}) Duplicate tweet. Trying to find original one')
                    tweet_url = await self.twitter.find_posted_tweet(lambda t: tweet_text.split('\n')[0] in t)
                    if tweet_url is None:
                        raise Exception("Tried to post duplicate tweet. Can't find original one")
                    logger.info(f'{self.idx}) Duplicate tweet found: {tweet_url}')
                else:
                    raise e
            logger.info(f'{self.idx}) Posted link tweet: {tweet_url}')
            await wait_a_bit()
            await self.client.check_twitter_account(tweet_url)
            await self.client.verify_twitter_account(tweet_url)
        except Exception as e:
            raise Exception(f'Failed ot link Twitter: {str(e)}')

        logger.info(f'{self.idx}) Twitter account linked')
        await wait_a_bit(4)
        await self.refresh_profile()

    async def link_email(self, strict=False):
        existed_email = self.profile.get('email', '')
        if existed_email != '':
            current_email = Email.from_account(self.account).username()
            if existed_email.lower() == current_email.lower():
                return
            else:
                if not strict:
                    return
                logger.info(f'{self.idx}) Another email already linked with this EVM address: '
                            f'{existed_email}. Current: {current_email}')

        logger.info(f'{self.idx}) Starting link new email')

        try:
            async with Email.from_account(self.account) as email_client:
                await email_client.login()
                email_username = email_client.username()
                captcha = await self.get_captcha()
                await self.client.send_verify_code(email_username, captcha)
                logger.info(f'{self.idx}) Verify code was sent to {email_username}')
                email_subj, _ = await email_client.wait_for_email(
                    lambda s: s.startswith('Your Galxe Verification Code is '),
                )
                code = self._extract_code_from_email_subj(email_subj)
                await self.client.update_email(email_username, code)
        except Exception as e:
            raise Exception(f'Failed to link email: {str(e)}')

        logger.info(f'{self.idx}) Email linked')
        await wait_a_bit(4)
        await self.refresh_profile()

    async def link_discord(self):
        existed_discord = self.profile.get('discordUserID', '')
        existed_discord_username = self.profile.get('discordUserName', '')
        discord_user_id = self._get_discord_user_id()

        if existed_discord != '':
            if existed_discord == discord_user_id:
                return
            else:
                logger.info(f'{self.idx}) Another Discord account already linked with this EVM address: '
                            f'{existed_discord_username}')

        discord_auth_link = await self.client.get_social_auth_url()
        state = get_query_param(discord_auth_link, 'state')

        params = {
            'client_id': GALXE_DISCORD_CLIENT_ID,
            'response_type': 'code',
            'redirect_uri': 'https://galxe.com',
            'scope': 'identify guilds guilds.members.read',
            'state': f'Discord_Auth,{self.account.evm_address},false,{state}',
        }
        body = {
            'permissions': '0',
            'authorize': True,
            'integration_type': 0,
        }
        token = None
        try:
            location = await self.client.post(DISCORD_AUTH_URL, [200], lambda r: r['location'],
                                              params=params, json=body,
                                              headers={'Authorization': self.account.discord_token})
            token = get_query_param(location, 'code')
            await self.client.check_discord_account(state, token)
            await self.client.verify_discord_account(state, token)
        except Exception as e:
            if token is None:
                self.account.discord_error = True
            raise Exception(f'Failed to link Discord: {str(e)}')

        logger.info(f'{self.idx}) Discord account linked')
        await wait_a_bit(4)
        await self.refresh_profile()

    def _get_discord_user_id(self):
        if self.account.discord_token == '':
            raise Exception('Empty Discord token')
        token = self.account.discord_token.split('.')[0]
        token += '=' * (4 - len(token) % 4)
        return str(base64.b64decode(token.encode("utf-8")), 'utf-8')

    @classmethod
    def _extract_code_from_email_subj(cls, subj):
        return subj.split()[5]

    @classmethod
    def _is_parent_campaign(cls, campaign):
        return campaign.get('type') == 'Parent'

    @classmethod
    def _is_daily_campaign(cls, campaign):
        return campaign.get('recurringType') == Recurring.DAILY

    @classmethod
    def _is_sequential_campaign(cls, campaign):
        return campaign['parentCampaign'].get('isSequencial')

    @classmethod
    def _get_gamification_type(cls, campaign):
        if 'gamification' not in campaign:
            return None
        return campaign['gamification']['type']

    def _update_campaign_points(self, campaign, process_result=None):
        if self._is_parent_campaign(campaign):
            return
        daily_claimed = None
        if self._is_daily_campaign(campaign):
            daily_claimed = self._daily_points_claimed(campaign)
            if process_result and type(process_result) is tuple \
                    and process_result[0] == 'Points' and process_result[1] > 0:
                daily_claimed = True
        self.account.points[campaign['id']] = (campaign['name'], campaign['claimedLoyaltyPoints'], daily_claimed)
        if self._get_gamification_type(campaign) in [Gamification.OAT, Gamification.DROP]:
            self.account.nfts[campaign['id']] = campaign['whitelistInfo']['usedCount']

    async def _process_campaign(self, campaign_id, process_async_func, aggr_func=None):
        info = await self.client.get_campaign_info(campaign_id)
        self._update_campaign_points(info)

        if self._is_parent_campaign(info):
            results = [await self._process_campaign(child['id'], process_async_func, aggr_func)
                       for child in info['childrenCampaigns']]
            if aggr_func is None:
                return
            return aggr_func(results)

        if campaign_id not in self.account.actual_campaigns:
            self.account.actual_campaigns.append(campaign_id)
        if await self.verify_all_credentials(info):
            info = await self.client.get_campaign_info(campaign_id)

        result = await process_async_func(info)
        await wait_a_bit(5)

        info = await self.client.get_campaign_info(campaign_id)
        self._update_campaign_points(info, result)
        return result

    # Complete part

    async def complete_campaign(self, campaign_id: str):
        return await self._process_campaign(campaign_id, self._complete_campaign_process)

    async def _complete_campaign_process(self, campaign):
        logger.info(f'{self.idx}) Starting complete {campaign["name"]}')

        if campaign['requireEmail']:
            try:
                await self.link_email()
            except Exception as e:
                logger.warning(f'{self.idx}) Campaign require email: {str(e)}')

        if campaign['taskConfig'] and campaign['taskConfig'].get('participateCondition') is not None:
            logger.info(f'{self.idx}) Completing requirements')
            for i in range(max(VERIFY_TRIES, MAX_TRIES)):
                if i > 0:
                    logger.info(f'{self.idx}) Waiting for 30s to retry')
                    await asyncio.sleep(31)
                    campaign = await self.client.get_campaign_info(campaign['id'])
                conditions = campaign['taskConfig']['participateCondition']['conditions']
                credentials = [c['cred'] for c in conditions]
                conditions = [{'eligible': c['eligible']} for c in conditions]
                cred_group = {'conditions': conditions, 'credentials': credentials}
                need_retry = await self._complete_cred_group(campaign['id'], cred_group)
                await wait_a_bit(2)
                if not need_retry:
                    break
            await wait_a_bit(5)
            if await self.verify_all_credentials(campaign):
                campaign = await self.client.get_campaign_info(campaign['id'])
            await asyncio.sleep(5)

        logger.info(f'{self.idx}) Completing main tasks')

        for i in range(max(VERIFY_TRIES, MAX_TRIES)):

            if i > 0:
                logger.info(f'{self.idx}) Waiting for 30s to retry')
                await asyncio.sleep(31)
                campaign = await self.client.get_campaign_info(campaign['id'])

            try_again = False
            for group_id in range(len(campaign['credentialGroups'])):

                cred_group = campaign['credentialGroups'][group_id]
                need_retry = await self._complete_cred_group(campaign['id'], cred_group)
                try_again = need_retry or try_again
                await wait_a_bit(2)

            if not try_again:
                break

    async def _complete_cred_group(self, campaign_id: str, cred_group) -> bool:
        try_again = False
        for condition, credential in zip(cred_group['conditions'], cred_group['credentials']):
            try:
                try:
                    await self._complete_credential(campaign_id, condition, credential, FAKE_TWITTER)
                except Exception as exc:
                    if FAKE_TWITTER and ('Error: pass_token used' in str(exc)):
                        logger.info(f"{self.idx}) Probably can't complete with fake twitter. Trying without it")
                        await self._complete_credential(campaign_id, condition, credential, False)
                    else:
                        raise exc
                await wait_a_bit()
            except Exception as e:
                s_e = str(e)
                if ('try again in 30 seconds' in s_e or 'please verify after 1 minutes' in s_e or
                        ('Message: "None": Status = 200' in s_e and
                         'Galxe Web3 Score - Humanity Score' not in credential["name"])):
                    try_again = True
                if 'Message: "None": Status = 200' in s_e:
                    logger.info(f'{self.idx}) Completion was not registered, need to wait')
                    continue
                await log_long_exc(self.idx, f'Failed to complete "{credential["name"]}"', e, warning=True)
        return try_again

    async def _complete_credential(self, campaign_id: str, condition, credential, fake_twitter):
        if condition['eligible']:
            return

        match credential['type']:
            case Credential.TWITTER:
                need_sync = await self._complete_twitter(campaign_id, credential, fake_twitter)
            case Credential.EMAIL:
                need_sync = await self._complete_email(campaign_id, credential)
            case Credential.EVM_ADDRESS:
                need_sync = await self._complete_eth(campaign_id, credential)
            case Credential.GALXE_ID:
                need_sync = await self._complete_galxe_id(campaign_id, credential)
            case Credential.DISCORD:
                need_sync = await self._complete_discord(credential)
            case unexpected:
                if HIDE_UNSUPPORTED:
                    return
                raise Exception(f'{unexpected} credential type is not supported yet')

        if need_sync:
            await self._sync_credential(campaign_id, credential['id'], credential['type'])
            logger.success(f'{self.idx}) Verified "{credential["name"]}"')

        if credential['type'] == Credential.DISCORD:
            logger.info(f'{self.idx}) Extra wait 15s after Discord task verification')
            await asyncio.sleep(15)

    quote_mention_re = re.compile(r'mention \d+ friends')

    async def _complete_twitter(self, campaign_id: str, credential, fake_twitter) -> bool:
        await self.link_twitter(fake_twitter)
        await self.add_typed_credential(campaign_id, credential)
        if credential['id'] in self.twitter_credentials_done:
            logger.info(f'{self.idx}) Twitter action was already done. Just verifying it')
            return True
        if fake_twitter:
            return True
        try:
            match credential['credSource']:
                case CredSource.TWITTER_FOLLOW:
                    user_to_follow = get_query_param(credential['referenceLink'], 'screen_name')
                    await self.twitter.follow(user_to_follow)
                    logger.info(f'{self.idx}) @{user_to_follow} followed')
                case CredSource.TWITTER_RT:
                    tweet_id = get_query_param(credential['referenceLink'], 'tweet_id')
                    await self.twitter.retweet(tweet_id)
                    logger.info(f'{self.idx}) Retweet done')
                case CredSource.TWITTER_LIKE:
                    logger.info(f'{self.idx}) Currently can skip likes, because it\'s not visible')
                    # tweet_id = get_query_param(credential['referenceLink'], 'tweet_id')
                    # await self.twitter.like(tweet_id)
                case CredSource.TWITTER_QUOTE:
                    text = get_query_param(credential['referenceLink'], 'text')
                    tweet_link = text[text.rfind(' ') + 1:]
                    text = text[:text.rfind(' ')]
                    mentions = self.quote_mention_re.findall(credential['name'].lower())
                    if mentions:
                        mentions_number = int(mentions[0].split()[1])
                        usernames = []
                        for _ in range(mentions_number):
                            username = await self.fake_username()
                            for _ in range(5):
                                try:
                                    await self.twitter.get_user_id(username)
                                except UserNotFound:
                                    username = await self.fake_username()
                                    continue
                                break
                            usernames.append(username)
                        text += ''.join([f' @{un}' for un in usernames])
                    logger.info(f'{self.idx}) Tweet quote with text: {text}')
                    text += '\n' + tweet_link
                    quote_url = await self.twitter.post_tweet(text)
                    logger.info(f'{self.idx}) Quote done: {quote_url}')
                case unexpected:
                    if HIDE_UNSUPPORTED:
                        return False
                    raise Exception(f'{unexpected} credential source for Twitter task is not supported yet')
            self.twitter_credentials_done.add(credential['id'])
        except Exception as e:
            await log_long_exc(self.idx, 'Twitter action failed. Trying to verify anyway', e, warning=True)
        return True

    async def _complete_email(self, campaign_id: str, credential) -> bool:
        await self.link_email()
        match credential['credSource']:
            case CredSource.VISIT_LINK:
                await self.add_typed_credential(campaign_id, credential)
                return True
            case CredSource.QUIZ:
                await self.solve_quiz(credential)
                return False
            case CredSource.WATCH_YOUTUBE:
                await self.add_typed_credential(campaign_id, credential)
                return True
            case CredSource.SURVEY:
                await self._complete_survey(campaign_id, credential)
                return False
            case unexpected:
                if HIDE_UNSUPPORTED:
                    return False
                raise Exception(f'{unexpected} credential source for Email task is not supported yet')

    async def _complete_eth(self, campaign_id: str, credential) -> bool:
        match credential['credSource']:
            case CredSource.VISIT_LINK:
                await self.add_typed_credential(campaign_id, credential)
                return True
            case CredSource.QUIZ:
                await self.solve_quiz(credential)
                return False
            case CredSource.SURVEY:
                await self._complete_survey(campaign_id, credential)
                return False
            case CredSource.WATCH_YOUTUBE:
                await self.add_typed_credential(campaign_id, credential)
                return True
            case CredSource.CSV:
                raise Exception(f'{self.idx}) It seems like you are not eligible for custom project requirements')
        logger.warning(f'{self.idx}) {credential["name"]} is not done or not updated yet. Trying to verify it anyway')
        return True

    async def _complete_galxe_id(self, campaign_id: str, credential) -> bool:
        match credential['credSource']:
            case CredSource.SPACE_USERS | CredSource.SPACE_FOLLOWER:
                await self._follow_space(campaign_id, credential['id'])
            case CredSource.QUIZ:
                await self.solve_quiz(credential)
            case CredSource.SURVEY:
                await self._complete_survey(campaign_id, credential)
            case CredSource.VISIT_LINK:
                await self.add_typed_credential(campaign_id, credential)
                return True
            case CredSource.WATCH_YOUTUBE:
                await self.add_typed_credential(campaign_id, credential)
                return True
            case unexpected:
                if not HIDE_UNSUPPORTED:
                    raise Exception(f'{unexpected} credential source for Galxe ID task is not supported yet')
        return False

    async def _complete_discord(self, credential) -> bool:
        await self.link_discord()
        return True

    async def _follow_space(self, campaign_id: str, credential_id):
        info = await self.client.get_campaign_info(campaign_id)
        space = info['space']
        space_id = int(space['id'])
        if not space['isFollowing']:
            await self.client.follow_space(space_id)
            logger.info(f'{self.idx}) Space {space["name"]} followed')
        sync_options = self._default_sync_options(credential_id)
        eval_expr = sync_options.copy()
        eval_expr.update({
            'entityExpr': {
                'attrFormula': 'ALL',
                'attrs': [{
                    'attrName': 'follow',
                    'operatorSymbol': '==',
                    'targetValue': '1',
                    '__typename': 'ExprEntityAttr',
                }],
                'credId': credential_id,
            },
        })
        await self.client.sync_evaluate_credential_value(eval_expr, sync_options)

    def _default_sync_options(self, credential_id: str):
        return {
            'address': self.client.full_address,
            'credId': credential_id,
        }

    async def solve_quiz(self, quiz):
        quiz_id = quiz['id']
        answers = await quiz_storage.get_value(quiz_id)
        if answers is None:
            quizzes = await self.client.read_quiz(quiz_id)

            if any(q['type'] != QuizType.MULTI_CHOICE for q in quizzes):
                raise Exception(f"Can't solve quiz with not multi-choice items: {quiz_id}")

            answers = [-1 for _ in quizzes]
            correct = [False for _ in quizzes]

            while not all(correct):
                answers = [answers[i] if correct[i] else answers[i] + 1 for i in range(len(answers))]
                if any(a >= len(quizzes[i]['items']) for i, a in enumerate(answers)):
                    raise Exception(f"Can't find answers for {quiz['name']}")

                logger.info(f'{self.idx}) {quiz["name"]} attempt to answer with {answers}')
                sync_options = self._default_sync_options(quiz_id)
                sync_options.update({'quiz': {'answers': [str(a) for a in answers]}})

                result = await self.client.sync_credential_value(sync_options, only_allow=False, quiz=True)
                correct = result['quiz']['correct']

            logger.success(f'{self.idx}) {quiz["name"]} solved')
            await quiz_storage.set_value(quiz_id, answers)
            await quiz_storage.async_save()
        else:
            sync_options = self._default_sync_options(quiz_id)
            sync_options.update({'quiz': {'answers': [str(a) for a in answers]}})
            await self.client.sync_credential_value(sync_options, quiz=True)
            logger.success(f'{self.idx}) {quiz["name"]} answers restored and verified')

    async def _complete_survey(self, campaign_id, survey):
        survey_id = survey['id']
        survey_name = survey['name']
        logger.info(f'{self.idx}) Processing survey "{survey_name}"')
        questions = await self.client.read_survey(survey_id)
        answers = SURVEYS.get(self.account.evm_address.lower(), {}).get(campaign_id)
        if not answers:
            logger.warning(f'{self.idx}) No answers provided for {self.account.evm_address}')
            return False
        answers = [a.strip() for a in answers.split('|')]
        if len(answers) != len(questions):
            logger.warning(f'{self.idx}) Expected {len(questions)} answers, but only {len(answers)} provided')
            return False
        sync_options = self._default_sync_options(survey_id)
        logger.info(f'{self.idx}) Sending answers: {answers}')
        sync_options.update({'survey': {'answers': answers}})
        await self.client.sync_credential_value(sync_options, only_allow=False)
        logger.success(f'{self.idx}) "{survey_name}" submitted')

    @captcha_retry
    async def add_typed_credential(self, campaign_id: str, credential):
        captcha = await self.get_captcha()
        await self.client.add_typed_credential_items(campaign_id, credential['id'], captcha)
        await wait_a_bit(3)

    @captcha_retry
    async def _sync_credential(self, campaign_id: str, credential_id: str, cred_type: str):
        sync_options = self._default_sync_options(credential_id)
        match cred_type:
            case Credential.TWITTER:
                await self.client.twitter_oauth2_status()
                captcha = await self.get_captcha()
                sync_options.update({
                    'twitter': {
                        'campaignID': campaign_id,
                        'captcha': captcha,
                    }
                })
        await self.client.sync_credential_value(sync_options)

    async def verify_all_credentials(self, campaign):
        cred_ids = []
        for cred_group in campaign['credentialGroups']:
            cred_ids.extend([cred['id'] for cred in cred_group['credentials'] if cred['eligible'] == 0])
        if campaign['taskConfig'] and campaign['taskConfig'].get('participateCondition') is not None:
            conditions = campaign['taskConfig']['participateCondition']['conditions']
            cred_ids.extend([c['cred']['id'] for c in conditions])
        if len(cred_ids) == 0:
            return False
        await self.client.verify_credentials(cred_ids)
        await wait_a_bit(3)
        return True

    # Claim part

    def _daily_points_claimed(self, campaign):
        if not self._is_daily_campaign(campaign) or self._is_parent_campaign(campaign):
            return True
        if campaign['whitelistInfo']['currentPeriodClaimedLoyaltyPoints'] < \
                campaign['whitelistInfo']['currentPeriodMaxLoyaltyPoints']:
            return False
        if campaign['whitelistInfo']['currentPeriodMaxLoyaltyPoints'] > 0:
            return True
        return all(cg['claimedLoyaltyPoints'] > 0 for cg in campaign['credentialGroups'])

    def _campaign_points_claimed(self, campaign) -> bool:
        return campaign['whitelistInfo']['currentPeriodClaimedLoyaltyPoints'] >= \
            campaign['whitelistInfo']['currentPeriodMaxLoyaltyPoints'] and \
            campaign['claimedLoyaltyPoints'] >= campaign['loyaltyPoints'] and self._daily_points_claimed(campaign)

    @classmethod
    def _campaign_nft_claimed(cls, campaign) -> bool:
        return 0 < campaign['whitelistInfo']['maxCount'] <= campaign['whitelistInfo']['usedCount']

    def already_claimed(self, campaign) -> bool:
        gamification_type = self._get_gamification_type(campaign)
        if gamification_type is None:
            return True
        match gamification_type:
            case Gamification.POINTS:
                return self._campaign_points_claimed(campaign)
            case Gamification.OAT | Gamification.DROP:
                return self._campaign_points_claimed(campaign) and self._campaign_nft_claimed(campaign)
            case Gamification.POINTS_MYSTERY_BOX | Gamification.BOUNTY | Gamification.DISCORD_ROLE | Gamification.TOKEN:
                return self._campaign_nft_claimed(campaign)
            case unexpected:
                if HIDE_UNSUPPORTED:
                    return False
                logger.warning(f'{self.idx}) {unexpected} gamification type is not supported yet')
                return False

    async def claim_campaign(self, campaign_id: str):
        return await self._process_campaign(campaign_id, self._claim_campaign_process)

    async def _claim_campaign_process(self, campaign):
        if self.already_claimed(campaign):
            nft_cnt = self.account.nfts.get(campaign["id"])
            nft_info = f' and {plural_str(nft_cnt, "NFT")}' if nft_cnt is not None else ''
            bounty_info, discord_role_info, raffle_info = '', '', ''
            match self._get_gamification_type(campaign):
                case Gamification.BOUNTY:
                    bounty_info = ' and participated in bounty'
                case Gamification.DISCORD_ROLE:
                    discord_role_info = ' and discord role claimed'
                case Gamification.TOKEN:
                    raffle_info = ' and participated in raffle'
            logger.info(f'{self.idx}) {campaign["name"]} already claimed '
                        f'{self.account.points[campaign["id"]][1]} points'
                        f'{nft_info}{bounty_info}{discord_role_info}{raffle_info}')
            return
        logger.info(f'{self.idx}) Starting claim {campaign["name"]}')
        claimable = False
        for cred_idx, cred_group in enumerate(campaign['credentialGroups'], start=1):
            if claimable:
                break
            try:
                claimable = await self._is_cred_group_claimable(cred_group, cred_idx)
            except Exception as e:
                await log_long_exc(self.idx, f'Failed to check cred group#{cred_idx} for claim', e, warning=True)
        if not claimable:
            return
        try:
            two_step_claim = self._is_two_step_claim(campaign)
            claim_res = await self._claim_campaign_rewards(campaign)
            if two_step_claim:
                logger.info(f'{self.idx}) Two step claim')
                await asyncio.sleep(random.uniform(4.5, 5.5))
                try:
                    campaign = await self.client.get_campaign_info(campaign['id'])
                    await self._claim_campaign_rewards(campaign)
                except Exception as e:
                    await log_long_exc(self.idx, 'Second claim step failed', e, warning=True)
            return claim_res
        except Exception as e:
            await log_long_exc(self.idx, 'Failed to claim campaign', e, warning=True)

    @classmethod
    def _is_two_step_claim(cls, campaign) -> bool:
        wl_info = campaign['whitelistInfo']
        point_mint_amount = wl_info['currentPeriodMaxLoyaltyPoints'] - wl_info['currentPeriodClaimedLoyaltyPoints']
        mint_amount = 0 if wl_info['maxCount'] == -1 else wl_info['maxCount'] - wl_info['usedCount']
        return point_mint_amount > 0 and mint_amount > 0

    async def _is_cred_group_claimable(self, cred_group, cred_idx):
        points_rewards = [r for r in cred_group['rewards'] if r['rewardType'] == 'LOYALTYPOINTS']
        only_points = len(points_rewards) == len(cred_group['rewards'])
        available_points = sum(0 if '{{' in r['expression'] else int(r['expression']) for r in points_rewards)
        claimed_points = cred_group['claimedLoyaltyPoints']
        if claimed_points >= available_points and only_points:
            return False
        eligible = [c['eligible'] for c in cred_group['conditions']]
        left_points = available_points - claimed_points

        claimable = False
        match cred_group['conditionRelation']:
            case ConditionRelation.ALL:
                claimable = all(eligible)
            case ConditionRelation.ANY:
                claimable = any(eligible)
            case unexpected:
                if not HIDE_UNSUPPORTED:
                    logger.warning(f'{self.idx}) {unexpected} condition relation is not supported yet')
        if not claimable:
            not_claimable_msg = ([('[+] ' if c['eligible'] == 1 else '[-] ') + c["name"]
                                  for c in cred_group["credentials"]] +
                                 [f"{left_points} points left"])
            if len(not_claimable_msg) > 1:
                not_claimable_msg[0] = ' ' + not_claimable_msg[0]
            not_claimable_msg = f'group#{cred_idx} [{" | ".join(not_claimable_msg)}]'
            not_claimable_msg = colored(f'Not enough conditions eligible to claim {not_claimable_msg}', 'cyan')
            logger.info(f'{self.idx}) ' + not_claimable_msg)
        return claimable

    async def _claim_campaign_rewards(self, campaign):
        campaign = await self.client.get_campaign_info(campaign['id'])

        reward_type = self._get_gamification_type(campaign)
        if reward_type is None:
            return

        params = self._get_claim_params(campaign)
        point_mint_amount, mint_amount = params['pointMintAmount'], params['mintCount']

        chains = []
        if point_mint_amount > 0: chains.append('GRAVITY_ALPHA')
        if mint_amount > 0: chains.append(campaign['chain'])
        if campaign['gasType'] == GasType.GAS_LESS:
            sufficient = await self.client.sufficient_for_gasless_chain_query(int(campaign['space']['id']), chains)
            insuff_for_points = any(suff['chain'] == 'GRAVITY_ALPHA' and not suff['sufficient'] for suff in sufficient)
            if insuff_for_points:
                logger.info(f'{self.idx}) Need $G token to claim points')
        else:
            sufficient = []
            insuff_for_points = False
            if campaign['chain'] == 'GRAVITY_ALPHA' and point_mint_amount > 0:
                sufficient = await self.client.sufficient_for_gasless_chain_query(int(campaign['space']['id']), chains)
                insuff_for_points = any(
                    suff['chain'] == 'GRAVITY_ALPHA' and not suff['sufficient'] for suff in sufficient)
                if insuff_for_points:
                    logger.info(f'{self.idx}) Need $G token to claim points')

        claim_data = await self._get_claim_data(campaign)

        if reward_type != Gamification.POINTS and point_mint_amount > 0 and mint_amount == 0:
            reward_type = Gamification.POINTS

        claimed_points = 0
        claimed_nfts = 0
        nft_type = ''
        match reward_type:
            case Gamification.POINTS | Gamification.POINTS_MYSTERY_BOX:
                lp_tx_resp = claim_data.get('loyaltyPointsTxResp', {})
                claimed_points = sum(lp_tx_resp.get('Points', []))
                if lp_tx_resp.get('loyaltyPointContract'):
                    await self._claim_gravity_points(
                        campaign,
                        lp_tx_resp,
                        claimed_points,
                    )
                allowed = lp_tx_resp.get('allow')
                claimed_points = claimed_points if allowed else 0
                claimed_log = f'{claimed_points} points'
                if reward_type == Gamification.POINTS_MYSTERY_BOX:
                    claimed_log += ' from Mystery Box'
            case Gamification.OAT | Gamification.DROP:
                nft_type = 'NFT' if reward_type == Gamification.DROP else 'OAT'
                gas_less = campaign['gasType'] == GasType.GAS_LESS
                was_gasless = False
                if gas_less:
                    sufficient = await self.client.sufficient_for_gasless_chain_query(
                        int(campaign['space']['id']),
                        campaign['chain'],
                    )
                    if not sufficient:
                        logger.info(f'{self.idx}) Insufficient space balance for gasless claim')
                        gas_less, was_gasless = False, True
                if not gas_less and claim_data['mintFuncInfo'].get('nftCoreAddress'):
                    await self._claim_gas_reward(campaign, claim_data, was_gasless)
                claimed_nfts = len(claim_data['mintFuncInfo']['verifyIDs'])
                claimed_log = plural_str(claimed_nfts, nft_type)
            case Gamification.BOUNTY:
                claimed_log = '[Participated in Bounty]'
            case Gamification.DISCORD_ROLE:
                claimed_log = '[Discord Role]'
            case Gamification.TOKEN:
                if campaign.get('distributionType') == 'RAFFLE':
                    claimed_log = '[Participated in Raffle]'
                else:
                    raise Exception('Unexpected distribution type for token reward')
            case unexpected:
                raise Exception(f'{unexpected} reward type is not supported for claim yet')

        logger.success(f'{self.idx}) Campaign {campaign["name"]} claimed {claimed_log}')

        result = ('Points', claimed_points) if claimed_points > 0 else None
        result = (nft_type, claimed_nfts) if claimed_nfts > 0 else result

        return result

    @classmethod
    def get_referral_code(cls, campaign):
        for campaign_id, ref_code in REFERRAL_LINKS:
            if campaign['id'] == campaign_id:
                return ref_code
            if campaign['parentCampaign'] is not None and campaign['parentCampaign']['id'] == campaign_id:
                return ref_code
        return None

    def _get_claim_params(self, campaign, silent=False):
        wl_info = campaign['whitelistInfo']
        point_mint_amount = wl_info['currentPeriodMaxLoyaltyPoints'] - wl_info['currentPeriodClaimedLoyaltyPoints']
        mint_amount = 0 if wl_info['maxCount'] == -1 else wl_info['maxCount'] - wl_info['usedCount']
        chain = 'GRAVITY_ALPHA' if point_mint_amount > 0 else campaign['chain']
        if point_mint_amount <= 0 and mint_amount <= 0:
            raise Exception('Nothing to claim')
        if chain.lower() == 'aptos':
            raise Exception(f'Aptos claim rewards is not supported')
        mint_log = []
        if point_mint_amount > 0: mint_log.append(f'{point_mint_amount} points')
        if mint_amount > 0: mint_log.append(plural_str(mint_amount, self._get_gamification_type(campaign).upper()))
        mint_log = ' and '.join(mint_log)
        if not silent:
            logger.info(f'{self.idx}) Will claim {mint_log}')
        return {
            'pointMintAmount': point_mint_amount,
            'mintCount': mint_amount,
            'chain': chain,
        }

    @captcha_retry
    async def _get_claim_data(self, campaign):
        chain = campaign['chain']
        if chain == 'APTOS':
            raise Exception(f'Aptos claim rewards is not supported')
        params = self._get_claim_params(campaign, silent=True)
        if params['pointMintAmount'] > 0 and params['mintCount'] > 0:
            params['pointMintAmount'] = 0
        captcha = await self.get_captcha()
        return await self.client.prepare_participate(
            campaign['id'], captcha, chain,
            referral_code=self.get_referral_code(campaign),
            input_kwargs=params,
        )

    async def _claim_gravity_points(self, campaign, lp_tx_resp, amount):
        async with OnchainAccount(self.account, 'Gravity') as onchain:
            tx_hash = await onchain.claim_loyalty_points(
                lp_tx_resp['loyaltyPointDistributionStation'],
                lp_tx_resp['loyaltyPointContract'],
                lp_tx_resp['VerifyIDs'][0],
                lp_tx_resp.get('claimFeeAmount', 0),
                amount,
                lp_tx_resp['signature'],
            )

        try:
            await self.client.participate_point(campaign['id'], lp_tx_resp['nonce'], tx_hash, lp_tx_resp['VerifyIDs'])
        except Exception as e:
            await log_long_exc(self.idx, 'Claim points confirmation in API failed', e, warning=True)

    async def _claim_gas_reward(self, campaign, claim_data, was_gasless=False):
        space_station = campaign['spaceStation']
        space_station_address, space_chain = space_station['address'], space_station['chain']
        if was_gasless:
            space_chain = campaign['chain']
        chain = CHAIN_NAME_MAPPING.get(space_chain, space_chain.capitalize())
        number_id = campaign['numberID']

        signature = claim_data['signature']
        nonce = claim_data['nonce']
        nft_core_address = claim_data['mintFuncInfo']['nftCoreAddress']
        verify_id = claim_data['mintFuncInfo']['verifyIDs'][0]
        powah = claim_data['mintFuncInfo']['powahs'][0]
        cap = claim_data['mintFuncInfo'].get('cap')

        async with OnchainAccount(self.account, chain) as onchain:
            if cap:
                tx_hash = await onchain.claim_capped(
                    space_station_address,
                    number_id, signature, nft_core_address, verify_id, powah, cap
                )
            else:
                tx_hash = await onchain.claim(
                    space_station_address,
                    number_id, signature, nft_core_address, verify_id, powah
                )

        try:
            await self.client.participate(campaign['id'], space_chain, nonce, tx_hash, verify_id)
        except Exception as e:
            await log_long_exc(self.idx, 'Claim confirmation in API failed', e, warning=True)

    # Stats part

    async def spaces_stats(self):
        cursor, has_next_page = '', True
        while has_next_page:
            result = await self.client.profile_leaderboard(cursor)
            page_info = result['pageInfo']
            cursor, has_next_page = page_info['endCursor'], page_info['hasNextPage']
            for edge in result['edges']:
                node = edge['node']
                space = node['space']
                self.account.spaces_points[space['alias']] = (space['name'], node['points'], node['rank'])
