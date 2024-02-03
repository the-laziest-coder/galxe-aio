import random
import json
import binascii
import aiohttp

from ..models import AccountInfo
from ..utils import get_proxy_url, handle_aio_response, async_retry, get_conn
from ..config import DISABLE_SSL
from ..vars import USER_AGENT, SEC_CH_UA, SEC_CH_UA_PLATFORM


def generate_csrf_token(size=16):
    data = random.getrandbits(size * 8).to_bytes(size, "big")
    return binascii.hexlify(data).decode()


def _get_headers(info: AccountInfo) -> dict:
    # if is_empty(info.user_agent):
    #     info.user_agent = USER_AGENT
    #     info.sec_ch_ua = SEC_CH_UA
    #     info.sec_ch_ua_platform = SEC_CH_UA_PLATFORM
    return {
        'accept': '*/*',
        'accept-language': 'en;q=0.9',
        'authorization': 'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
        'content-type': 'application/json',
        'origin': 'https://mobile.twitter.com',
        'referer': 'https://mobile.twitter.com/',
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

    def __init__(self, account_info: AccountInfo):
        self.account = account_info
        self.cookies = {
            'auth_token': account_info.twitter_auth_token,
            'ct0': '',
        }
        self.headers = _get_headers(account_info)
        self.proxy = get_proxy_url(account_info.proxy)
        self.my_user_id = None
        self.my_username = None

    async def start(self):
        ct0 = await self._get_ct0()
        self.cookies.update({'ct0': ct0})
        self.headers.update({'x-csrf-token': ct0})
        self.my_username = await self.get_my_profile_info()
        self.my_user_id = await self.get_user_id(self.my_username)

    def set_cookies(self, resp_cookies):
        self.cookies.update({name: value.value for name, value in resp_cookies.items()})

    @async_retry
    async def request(self, method, url, acceptable_statuses=None, resp_handler=None, with_text=False, **kwargs):
        headers = self.headers.copy()
        cookies = self.cookies.copy()
        if 'headers' in kwargs:
            headers.update(kwargs.pop('headers'))
        if 'cookies' in kwargs:
            cookies.update(kwargs.pop('cookies'))
        if DISABLE_SSL:
            kwargs.update({'ssl': False})
        try:
            async with aiohttp.ClientSession(connector=get_conn(self.proxy), headers=headers, cookies=cookies) as sess:
                if method.lower() == 'get':
                    async with sess.get(url, **kwargs) as resp:
                        self.set_cookies(resp.cookies)
                        return await handle_aio_response(resp, acceptable_statuses, resp_handler, with_text)
                elif method.lower() == 'post':
                    async with sess.post(url, **kwargs) as resp:
                        self.set_cookies(resp.cookies)
                        return await handle_aio_response(resp, acceptable_statuses, resp_handler, with_text)
                else:
                    raise Exception('Wrong request method')
        except Exception as e:
            self.account.twitter_error = True
            raise e

    async def _get_ct0(self):
        try:
            kwargs = {'ssl': False} if DISABLE_SSL else {}
            async with aiohttp.ClientSession(connector=get_conn(self.proxy),
                                             headers=self.headers, cookies=self.cookies) as sess:
                async with sess.get('https://twitter.com/i/api/1.1/dm/user_updates.json?', **kwargs) as resp:
                    new_csrf = resp.cookies.get("ct0")
                    if new_csrf is None:
                        raise Exception('Empty new csrf')
                    new_csrf = new_csrf.value
                    return new_csrf
        except Exception as e:
            reason = 'Your account has been locked\n' if 'Your account has been locked' in str(e) else ''
            self.account.twitter_error = True
            raise Exception(f'Failed to get ct0 for twitter: {reason}{str(e)}')

    async def get_my_profile_info(self):
        url = 'https://api.twitter.com/1.1/account/settings.json'
        params = {
            'include_mention_filter': 'true',
            'include_nsfw_user_flag': 'true',
            'include_nsfw_admin_flag': 'true',
            'include_ranked_timeline': 'true',
            'include_alt_text_compose': 'true',
            'ext': 'ssoConnections',
            'include_country_code': 'true',
            'include_ext_dm_nsfw_media_filter': 'true',
            'include_ext_sharing_audiospaces_listening_data_with_followers': 'true',
        }
        try:
            return await self.request("GET", url, params=params, resp_handler=lambda r: r['screen_name'].lower())
        except Exception as e:
            raise Exception(f'Get my username error: {str(e)}')

    async def get_followers_count(self, username):
        url = 'https://twitter.com/i/api/graphql/G3KGOASz96M-Qu0nwmGXNg/UserByScreenName'
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
        url = 'https://twitter.com/i/api/graphql/9zwVLJ48lmVUk8u_Gh9DmA/ProfileSpotlightsQuery'
        if username[0] == '@':
            username = username[1:]
        username = username.lower()
        params = {
            'variables': to_json({'screen_name': username})
        }
        try:
            return await self.request(
                "GET", url, params=params,
                resp_handler=lambda r: int(r['data']['user_result_by_screen_name']['result']['rest_id'])
            )
        except Exception as e:
            raise Exception(f'Get user id error: {str(e)}')

    async def follow(self, username):
        user_id = await self.get_user_id(username)
        url = 'https://twitter.com/i/api/1.1/friendships/create.json'
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
        query_id = "GUFG748vuvmewdXbB5uPKg"
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
                freedom_of_speech_not_reach_fetch_enabled=True,
                graphql_is_translatable_rweb_tweet_is_translatable_enabled=True,
                longform_notetweets_consumption_enabled=True,
                longform_notetweets_inline_media_enabled=True,
                longform_notetweets_rich_text_read_enabled=True,
                responsive_web_edit_tweet_api_enabled=True,
                responsive_web_enhance_cards_enabled=False,
                responsive_web_graphql_exclude_directive_enabled=True,
                responsive_web_graphql_skip_user_profile_image_extensions_enabled=False,
                responsive_web_graphql_timeline_navigation_enabled=True,
                standardized_nudges_misinfo=True,
                tweet_awards_web_tipping_enabled=False,
                tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled=False,
                tweetypie_unmention_optimization_enabled=True,
                verified_phone_label_enabled=False,
                view_counts_everywhere_api_enabled=True
            ),
            queryId=query_id)

        if tweet_id:
            _json['variables']['reply'] = dict(
                in_reply_to_tweet_id=tweet_id,
                exclude_reply_user_ids=[]
            )

        url = f'https://twitter.com/i/api/graphql/{query_id}/{action}'

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
        url = f'https://twitter.com/i/api/graphql/{query_id}/{action}'
        _json = {
            'variables': {
                'tweet_id': tweet_id,
                'dark_request': False
            },
            'queryId': query_id
        }
        try:
            return await self.request('POST', url, json=_json, resp_handler=lambda r: r)
        except Exception as e:
            raise Exception(f'Retweet error: {str(e)}')

    async def like(self, tweet_id) -> bool:
        action = 'FavoriteTweet'
        query_id = 'lI07N6Otwv1PhnEgXILM7A'
        url = f'https://twitter.com/i/api/graphql/{query_id}/{action}'
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
        query_id = "QWF3SzpHmykQHsQMixG0cg"
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
                "responsive_web_graphql_exclude_directive_enabled": True,
                "verified_phone_label_enabled": False,
                "creator_subscriptions_tweet_preview_api_enabled": True,
                "responsive_web_graphql_timeline_navigation_enabled": True,
                "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                "c9s_tweet_anatomy_moderator_badge_enabled": True,
                "tweetypie_unmention_optimization_enabled": True,
                "responsive_web_edit_tweet_api_enabled": True,
                "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
                "view_counts_everywhere_api_enabled": True,
                "longform_notetweets_consumption_enabled": True,
                "responsive_web_twitter_article_tweet_consumption_enabled": True,
                "tweet_awards_web_tipping_enabled": False,
                "freedom_of_speech_not_reach_fetch_enabled": True,
                "standardized_nudges_misinfo": True,
                "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
                "rweb_video_timestamps_enabled": True,
                "longform_notetweets_rich_text_read_enabled": True,
                "longform_notetweets_inline_media_enabled": True,
                "responsive_web_media_download_video_enabled": False,
                "responsive_web_enhance_cards_enabled": False,
            }),
        }

        url = f'https://twitter.com/i/api/graphql/{query_id}/{action}'

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
