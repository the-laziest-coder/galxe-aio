import random
import json
import binascii
from urllib.parse import urlparse

from .client_transaction import ClientTransaction
from ..models import AccountInfo
from ..utils import get_proxy_url, handle_aio_response, async_retry, get_conn
from ..config import DISABLE_SSL
from ..tls import TLSClient
from ..vars import USER_AGENT, SEC_CH_UA, SEC_CH_UA_PLATFORM


class UserNotFound(Exception):
    def __init__(self):
        super().__init__('User not found')


def generate_csrf_token(size=16):
    data = random.getrandbits(size * 8).to_bytes(size, "big")
    return binascii.hexlify(data).decode()


def _get_headers() -> dict:
    # if is_empty(info.user_agent):
    #     info.user_agent = USER_AGENT
    #     info.sec_ch_ua = SEC_CH_UA
    #     info.sec_ch_ua_platform = SEC_CH_UA_PLATFORM
    return {
        'accept': '*/*',
        'accept-language': 'en;q=0.9',
        'authorization': 'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
        'content-type': 'application/json',
        'origin': 'https://x.com',
        'referer': 'https://x.com/',
        'sec-ch-ua': SEC_CH_UA,
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': SEC_CH_UA_PLATFORM,
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'x-twitter-active-user': 'yes',
        'x-twitter-auth-type': 'OAuth2Session',
        'x-twitter-client-language': 'en',
        'x-csrf-token': '',
        'user-agent': USER_AGENT,
    }


class Twitter:

    COOKIES_DOMAIN = '.x.com'

    def __init__(self, account_info: AccountInfo):
        self.account = account_info
        self.proxy = get_proxy_url(account_info.proxy)
        self.my_user_id = None
        self.my_username = None
        self.tls = TLSClient(self.account, _get_headers(), debug=True)
        self.client_transaction = ClientTransaction()

    async def start(self):
        await self.client_transaction.init(self.tls)
        self.set_cookies({'auth_token': self.account.twitter_auth_token})
        ct0 = self.account.twitter_ct0
        if ct0 == '':
            ct0 = await self._get_ct0()
            self.account.twitter_ct0 = ct0
        self.set_cookies({'ct0': ct0})
        self.tls.update_headers({'x-csrf-token': ct0})
        self.my_username = await self.get_my_profile_info()
        self.my_user_id = await self.get_user_id(self.my_username)

    def set_cookies(self, cookies):
        for name, value in cookies.items():
            self.tls.sess.cookies.set(name, value, self.COOKIES_DOMAIN)

    async def request(self, method, url, **kwargs):
        try:
            tx_id = self.client_transaction.generate_transaction_id(method, urlparse(url).path)
            headers = {'X-Client-Transaction-Id': tx_id}
            if 'headers' in kwargs:
                headers.update(kwargs.pop('headers'))
            return await self.tls.request(method, url, headers=headers, **kwargs)
        except Exception as e:
            self.account.twitter_error = True
            raise e

    async def _get_ct0(self):
        try:
            await self.tls.get('https://api.x.com/1.1/account/settings.json', raw=True)
            return self.tls.sess.cookies.get('ct0', self.account.twitter_ct0, self.COOKIES_DOMAIN)
        except Exception as e:
            reason = 'Your account has been locked\n' if 'Your account has been locked' in str(e) else ''
            self.account.twitter_error = True
            raise Exception(f'Failed to get ct0 for twitter: {reason}{str(e)}')

    def check_response_errors(self, resp):
        if type(resp) is not dict:
            return
        errors = resp.get('errors', [])
        if type(errors) is not list:
            return
        if len(errors) == 0:
            return
        error_msg = ' | '.join([msg for msg in [err.get('message') for err in errors if type(err) is dict] if msg])
        if len(error_msg) == 0:
            return
        raise Exception(error_msg)

    async def get_my_profile_info(self):
        url = 'https://api.x.com/graphql/UhddhjWCl-JMqeiG4vPtvw/Viewer'
        features = {
            "rweb_tipjar_consumption_enabled": True,
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "creator_subscriptions_tweet_preview_api_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "responsive_web_graphql_timeline_navigation_enabled": True,
        }
        field_toggles = {
            "isDelegate": False,
            "withAuxiliaryUserLabels": False,
        }
        variables = {"withCommunitiesMemberships": True}
        params = {
            "features": features,
            "fieldToggles": field_toggles,
            "variables": variables,
        }
        try:
            return await self.request(
                "GET", url, params=params,
                resp_handler=lambda r: r['data']['viewer']['user_results']['result']['legacy']['screen_name'],
            )
        except Exception as e:
            raise Exception(f'Get my username error: {str(e)}')

    async def get_followers_count(self, username):
        url = 'https://x.com/i/api/graphql/G3KGOASz96M-Qu0nwmGXNg/UserByScreenName'
        params = {
            'variables': to_json({"screen_name": username, "withSafetyModeUserFields": True}),
            'features': to_json({
                "hidden_profile_likes_enabled": True,
                "hidden_profile_subscriptions_enabled": True,
                "responsive_web_graphql_exclude_directive_enabled": True,
                "verified_phone_label_enabled": False,
                "subscriptions_verification_info_is_identity_verified_enabled": True,
                "subscriptions_verification_info_verified_since_enabled": True,
                "highlights_tweets_tab_ui_enabled": True,
                "creator_subscriptions_tweet_preview_api_enabled": True,
                "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                "responsive_web_graphql_timeline_navigation_enabled": True
            }),
            'fieldToggles': to_json({"withAuxiliaryUserLabels": False})
        }
        try:
            return await self.request(
                "GET", url, params=params,
                resp_handler=lambda r: r['data']['user']['result']['legacy']['followers_count']
            )
        except Exception as e:
            raise Exception(f'Get followers count error: {str(e)}')

    async def get_user_id(self, username):
        url = 'https://x.com/i/api/graphql/-0XdHI-mrHWBQd8-oLo1aA/ProfileSpotlightsQuery'
        if username[0] == '@':
            username = username[1:]
        username = username.lower()
        params = {
            'variables': to_json({'screen_name': username})
        }

        def _handler(resp):
            if type(resp) is dict and len(resp.get('data', {})) == 0:
                raise UserNotFound()
            return int(resp['data']['user_result_by_screen_name']['result']['rest_id'])

        try:
            return await self.request("GET", url, params=params, resp_handler=_handler)
        except Exception as e:
            raise Exception(f'Get user id error: {str(e)}')

    async def follow(self, username):
        user_id = await self.get_user_id(username)
        url = 'https://x.com/i/api/1.1/friendships/create.json'
        params = {
            'include_profile_interstitial_type': '1',
            'include_blocking': '1',
            'include_blocked_by': '1',
            'include_followed_by': '1',
            'include_want_retweets': '1',
            'include_mute_edge': '1',
            'include_can_dm': '1',
            'include_can_media_tag': '1',
            'include_ext_has_nft_avatar': '1',
            'include_ext_is_blue_verified': '1',
            'include_ext_verified_type': '1',
            'include_ext_profile_image_shape': '1',
            'skip_status': '1',
            'user_id': user_id,
        }
        headers = {
            'content-type': 'application/x-www-form-urlencoded'
        }
        try:
            await self.request('POST', url, params=params, headers=headers, resp_handler=lambda r: r['id'])
        except Exception as e:
            raise Exception(f'Follow error: {str(e)}')

    async def post_tweet(self, text, tweet_id=None) -> str:
        action = "CreateTweet"
        query_id = "xT36w0XM3A8jDynpkram2A"
        _json = dict(
            variables=dict(
                tweet_text=text,
                media=dict(
                    media_entities=[],
                    possibly_sensitive=False
                ),
                semantic_annotation_ids=[],
                dark_request=False
            ),
            features=dict(
                communities_web_enable_tweet_community_results_fetch=True,
                c9s_tweet_anatomy_moderator_badge_enabled=True,
                tweetypie_unmention_optimization_enabled=True,
                responsive_web_edit_tweet_api_enabled=True,
                graphql_is_translatable_rweb_tweet_is_translatable_enabled=True,
                view_counts_everywhere_api_enabled=True,
                longform_notetweets_consumption_enabled=True,
                responsive_web_twitter_article_tweet_consumption_enabled=True,
                tweet_awards_web_tipping_enabled=False,
                creator_subscriptions_quote_tweet_preview_enabled=False,
                longform_notetweets_rich_text_read_enabled=True,
                longform_notetweets_inline_media_enabled=True,
                articles_preview_enabled=True,
                rweb_video_timestamps_enabled=True,
                rweb_tipjar_consumption_enabled=True,
                responsive_web_graphql_exclude_directive_enabled=True,
                verified_phone_label_enabled=False,
                freedom_of_speech_not_reach_fetch_enabled=True,
                standardized_nudges_misinfo=True,
                tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled=True,
                responsive_web_graphql_skip_user_profile_image_extensions_enabled=False,
                responsive_web_graphql_timeline_navigation_enabled=True,
                responsive_web_enhance_cards_enabled=False,
            ),
            queryId=query_id,
        )

        if tweet_id:
            _json['variables']['reply'] = dict(
                in_reply_to_tweet_id=tweet_id,
                exclude_reply_user_ids=[]
            )

        url = f'https://x.com/i/api/graphql/{query_id}/{action}'

        def _handler(resp):
            _result = resp['data']['create_tweet']['tweet_results']['result']
            _username = _result['core']['user_results']['result']['legacy']['screen_name']
            _tweet_id = _result['rest_id']
            _url = f'https://x.com/{_username}/status/{_tweet_id}'
            return _url

        try:
            return await self.request('POST', url, json=_json, resp_handler=_handler)
        except Exception as e:
            raise Exception(f'Post tweet error: {str(e)}')

    async def retweet(self, tweet_id):
        action = 'CreateRetweet'
        query_id = 'ojPdsZsimiJrUGLR1sjUtA'
        url = f'https://x.com/i/api/graphql/{query_id}/{action}'
        _json = {
            'variables': {
                'tweet_id': tweet_id,
                'dark_request': False
            },
            'queryId': query_id
        }
        try:
            resp = await self.request('POST', url, json=_json, resp_handler=lambda r: r)
            self.check_response_errors(resp)
            return resp
        except Exception as e:
            raise Exception(f'Retweet error: {str(e)}')

    async def like(self, tweet_id) -> bool:
        action = 'FavoriteTweet'
        query_id = 'lI07N6Otwv1PhnEgXILM7A'
        url = f'https://x.com/i/api/graphql/{query_id}/{action}'
        _json = {
            'variables': {
                'tweet_id': tweet_id,
                'dark_request': False
            },
            'queryId': query_id
        }
        try:
            return await self.request(
                'POST', url, json=_json,
                resp_handler=lambda r: r['data']['favorite_tweet'] == 'Done'
            )
        except Exception as e:
            raise Exception(f'Like error: {str(e)}')

    async def find_posted_tweet(self, text_condition_func, count=20) -> str:
        action = "UserTweets"
        query_id = "E3opETHurmVJflFsUBVuUQ"
        params = {
            'variables': to_json({
                "userId": self.my_user_id,
                "count": count,
                "includePromotedContent": False,
                "withQuickPromoteEligibilityTweetFields": False,
                "withVoice": False,
                "withV2Timeline": True,
            }),
            'features': to_json({
                "profile_label_improvements_pcf_label_in_post_enabled": False,
                "rweb_tipjar_consumption_enabled": True,
                "responsive_web_graphql_exclude_directive_enabled": True,
                "verified_phone_label_enabled": False,
                "creator_subscriptions_tweet_preview_api_enabled": True,
                "responsive_web_graphql_timeline_navigation_enabled": True,
                "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                "premium_content_api_read_enabled": False,
                "communities_web_enable_tweet_community_results_fetch": True,
                "c9s_tweet_anatomy_moderator_badge_enabled": True,
                "responsive_web_grok_analyze_button_fetch_trends_enabled": True,
                "responsive_web_grok_analyze_post_followups_enabled": False,
                "responsive_web_grok_share_attachment_enabled": False,
                "articles_preview_enabled": True,
                "responsive_web_edit_tweet_api_enabled": True,
                "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
                "view_counts_everywhere_api_enabled": True,
                "longform_notetweets_consumption_enabled": True,
                "responsive_web_twitter_article_tweet_consumption_enabled": True,
                "tweet_awards_web_tipping_enabled": False,
                "creator_subscriptions_quote_tweet_preview_enabled": False,
                "freedom_of_speech_not_reach_fetch_enabled": True,
                "standardized_nudges_misinfo": True,
                "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
                "rweb_video_timestamps_enabled": True,
                "longform_notetweets_rich_text_read_enabled": True,
                "longform_notetweets_inline_media_enabled": True,
                "responsive_web_enhance_cards_enabled": False,
            }),
        }

        url = f'https://x.com/i/api/graphql/{query_id}/{action}'

        def _handler(resp):
            instructions = resp['data']['user']['result']['timeline_v2']['timeline']['instructions']
            entries = None
            for instruction in instructions:
                if instruction['type'] == 'TimelineAddEntries':
                    entries = instruction['entries']
                    break
            if entries is None:
                return None
            for entry in entries:
                tweet_text = entry['content']['itemContent']['tweet_results']['result']
                tweet_text = tweet_text['legacy']['full_text']
                if not text_condition_func(tweet_text):
                    continue
                tweet_id = entry['entryId']
                if tweet_id.startswith('tweet-'):
                    tweet_id = tweet_id[6:]
                _url = f'https://x.com/{self.my_username}/status/{tweet_id}'
                return _url
            return None

        try:
            return await self.request('GET', url, params=params, resp_handler=_handler)
        except Exception as e:
            raise Exception(f'Find posted tweet error: {str(e)}')


def to_json(obj):
    return json.dumps(obj, separators=(',', ':'), ensure_ascii=True)
