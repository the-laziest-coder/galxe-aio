from ..models import AccountInfo
from ..tls import TLSClient


class Client(TLSClient):
    GRAPH_URL = 'https://graphigo.prd.galaxy.eco/query'

    def __init__(self, account: AccountInfo):
        self.with_evm = True
        super().__init__(account, {
            'origin': 'https://galxe.com',
            'sec-fetch-site': 'cross-site',
        })

    async def api_request(self, body, response_extract_func=None, exc_condition=None):

        def resp_handler(resp):
            if resp.get('errors') is not None and len(resp['errors']) > 0:
                raise Exception(' | '.join([err['message'] for err in resp['errors']]))
            if exc_condition is not None:
                if exc_condition(resp):
                    operation_name = body['operationName']
                    operation_name = operation_name[0].lower() + operation_name[1:]
                    if 'data' in resp and operation_name in resp['data'] and 'message' in resp['data'][operation_name]:
                        raise Exception(resp['data'][operation_name]['message'])
                    raise Exception()
            if response_extract_func is not None:
                return response_extract_func(resp)
            return resp

        try:
            return await self.post(self.GRAPH_URL, json=body, timeout=60,
                                   acceptable_statuses=[200], resp_handler=resp_handler)
        except Exception as e:
            raise Exception(f"{body['operationName']} request failed: {str(e)}")

    @property
    def full_address(self):
        if self.with_evm:
            return f'EVM:{self.account.evm_address.lower()}'
        else:
            return f'APTOS:{self.account.aptos_address.lower()}'

    @property
    def raw_address(self):
        return self.account.evm_address.lower() if self.with_evm else self.account.aptos_address.lower()

    @property
    def address(self):
        if self.with_evm:
            return self.raw_address
        else:
            return self.full_address

    @property
    def address_type(self):
        return 'EVM' if self.with_evm else 'APTOS'

    async def galxe_id_exist(self) -> bool:
        body = {
            "operationName": "GalxeIDExist",
            "variables": {
                "schema": self.full_address,
            },
            "query": "query GalxeIDExist($schema: String!) {\n  galxeIdExist(schema: $schema)\n}\n"
        }
        return await self.api_request(body, lambda resp: resp['data']['galxeIdExist'])

    async def sign_in(self, msg, signature, with_aptos=False):
        self.with_evm = not with_aptos
        body = {
            'operationName': 'SignIn',
            'query': 'mutation SignIn($input: Auth) {\n  signin(input: $input)\n}\n',
            'variables': {
                'input': {
                    'address': self.raw_address,
                    'addressType': self.address_type,
                    'message': msg,
                    'signature': signature,
                },
            },
        }
        auth_token = await self.api_request(body, lambda resp: resp['data']['signin'])
        self.update_headers({'Authorization': auth_token})

    async def is_username_exist(self, username: str):
        body = {
            "operationName": "IsUsernameExisting",
            "variables": {"username": username},
            "query": "query IsUsernameExisting($username: String!) {\n  usernameExist(username: $username)\n}\n"
        }
        return await self.api_request(body, lambda resp: resp['data']['usernameExist'])

    async def create_account(self, username):
        body = {
            "operationName": "CreateNewAccount",
            "variables": {
                "input": {
                    "schema": self.full_address,
                    "socialUsername": "",
                    "username": username,
                }
            },
            "query": "mutation CreateNewAccount($input: CreateNewAccount!) {\n  createNewAccount(input: $input)\n}\n"
        }
        await self.api_request(body)

    async def basic_user_info(self):
        body = {
            "operationName": "BasicUserInfo",
            "variables": {
                "address": self.address,
            },
            "query": "query BasicUserInfo($address: String!) {\n  addressInfo(address: $address) {\n    id\n    username\n    avatar\n    address\n    evmAddressSecondary {\n      address\n      __typename\n    }\n    hasEmail\n    solanaAddress\n    aptosAddress\n    seiAddress\n    injectiveAddress\n    flowAddress\n    starknetAddress\n    bitcoinAddress\n    hasEvmAddress\n    hasSolanaAddress\n    hasAptosAddress\n    hasInjectiveAddress\n    hasFlowAddress\n    hasStarknetAddress\n    hasBitcoinAddress\n    hasTwitter\n    hasGithub\n    hasDiscord\n    hasTelegram\n    displayEmail\n    displayTwitter\n    displayGithub\n    displayDiscord\n    displayTelegram\n    displayNamePref\n    email\n    twitterUserID\n    twitterUserName\n    githubUserID\n    githubUserName\n    discordUserID\n    discordUserName\n    telegramUserID\n    telegramUserName\n    enableEmailSubs\n    subscriptions\n    isWhitelisted\n    isInvited\n    isAdmin\n    accessToken\n    __typename\n  }\n}\n"
        }
        return await self.api_request(body, lambda resp: resp['data']['addressInfo'])

    async def update_user_address(self, input_vars):
        body = {
            'operationName': 'UpdateUserAddress',
            'query': 'mutation UpdateUserAddress($input: UpdateUserAddressInput!) {\n  updateUserAddress(input: $input) {\n    code\n    message\n    __typename\n  }\n}\n',
            'variables': {
                'input': input_vars,
            },
        }
        await self.api_request(body)

    async def remove_user_address(self, input_vars):
        body = {
            'operationName': 'RemoveUserAddress',
            'query': 'mutation RemoveUserAddress($input: UpdateUserAddressInput!) {\n  removeUserAddress(input: $input) {\n    code\n    __typename\n  }\n}\n',
            'variables': {
                'input': input_vars,
            },
        }
        await self.api_request(body)

    async def check_twitter_account(self, tweet_url):
        body = {
            'operationName': 'checkTwitterAccount',
            'query': 'mutation checkTwitterAccount($input: VerifyTwitterAccountInput!) {\n  checkTwitterAccount(input: $input) {\n    address\n    twitterUserID\n    twitterUserName\n    __typename\n  }\n}\n',
            'variables': {
                'input': {
                    'address': self.address,
                    'tweetURL': tweet_url,
                },
            },
        }
        await self.api_request(body, exc_condition=lambda resp: resp['data']['checkTwitterAccount'] is None)

    async def verify_twitter_account(self, tweet_url):
        body = {
            'operationName': 'VerifyTwitterAccount',
            'query': 'mutation VerifyTwitterAccount($input: VerifyTwitterAccountInput!) {\n  verifyTwitterAccount(input: $input) {\n    address\n    twitterUserID\n    twitterUserName\n    __typename\n  }\n}\n',
            'variables': {
                'input': {
                    'address': self.address,
                    'tweetURL': tweet_url,
                },
            },
        }
        await self.api_request(body, exc_condition=lambda resp: resp['data']['verifyTwitterAccount'] is None)

    async def get_campaign_info(self, campaign_id):
        body = {
            'operationName': 'CampaignDetailAll',
            'query': 'query CampaignDetailAll($id: ID!, $address: String!, $withAddress: Boolean!) {\n  campaign(id: $id) {\n    ...CampaignForSiblingSlide\n    coHostSpaces {\n      ...SpaceDetail\n      isAdmin(address: $address) @include(if: $withAddress)\n      isFollowing @include(if: $withAddress)\n      followersCount\n      categories\n      __typename\n    }\n    bannerUrl\n    ...CampaignDetailFrag\n    userParticipants(address: $address, first: 1) @include(if: $withAddress) {\n      list {\n        status\n        premintTo\n        __typename\n      }\n      __typename\n    }\n    space {\n      ...SpaceDetail\n      isAdmin(address: $address) @include(if: $withAddress)\n      isFollowing @include(if: $withAddress)\n      followersCount\n      categories\n      __typename\n    }\n    isBookmarked(address: $address) @include(if: $withAddress)\n    inWatchList\n    claimedLoyaltyPoints(address: $address) @include(if: $withAddress)\n    parentCampaign {\n      id\n      isSequencial\n      thumbnail\n      __typename\n    }\n    isSequencial\n    numNFTMinted\n    childrenCampaigns {\n      ...ChildrenCampaignsForCampaignDetailAll\n      __typename\n    }\n    __typename\n  }\n}\n\nfragment CampaignDetailFrag on Campaign {\n  id\n  ...CampaignMedia\n  ...CampaignForgePage\n  ...CampaignForCampaignParticipantsBox\n  name\n  numberID\n  type\n  inWatchList\n  cap\n  info\n  useCred\n  smartbalancePreCheck(mintCount: 1)\n  smartbalanceDeposited\n  formula\n  status\n  seoImage\n  creator\n  tags\n  thumbnail\n  gasType\n  isPrivate\n  createdAt\n  requirementInfo\n  description\n  enableWhitelist\n  chain\n  startTime\n  endTime\n  requireEmail\n  requireUsername\n  blacklistCountryCodes\n  whitelistRegions\n  rewardType\n  distributionType\n  rewardName\n  claimEndTime\n  loyaltyPoints\n  tokenRewardContract {\n    id\n    address\n    chain\n    __typename\n  }\n  tokenReward {\n    userTokenAmount\n    tokenAddress\n    depositedTokenAmount\n    tokenRewardId\n    tokenDecimal\n    tokenLogo\n    tokenSymbol\n    __typename\n  }\n  nftHolderSnapshot {\n    holderSnapshotBlock\n    __typename\n  }\n  spaceStation {\n    id\n    address\n    chain\n    __typename\n  }\n  ...WhitelistInfoFrag\n  ...WhitelistSubgraphFrag\n  gamification {\n    ...GamificationDetailFrag\n    __typename\n  }\n  creds {\n    id\n    name\n    type\n    credType\n    credSource\n    referenceLink\n    description\n    lastUpdate\n    lastSync\n    syncStatus\n    credContractNFTHolder {\n      timestamp\n      __typename\n    }\n    chain\n    eligible(address: $address, campaignId: $id)\n    subgraph {\n      endpoint\n      query\n      expression\n      __typename\n    }\n    dimensionConfig\n    value {\n      gitcoinPassport {\n        score\n        lastScoreTimestamp\n        __typename\n      }\n      __typename\n    }\n    commonInfo {\n      participateEndTime\n      modificationInfo\n      __typename\n    }\n    __typename\n  }\n  credentialGroups(address: $address) {\n    ...CredentialGroupForAddress\n    __typename\n  }\n  rewardInfo {\n    discordRole {\n      guildId\n      guildName\n      roleId\n      roleName\n      inviteLink\n      __typename\n    }\n    premint {\n      startTime\n      endTime\n      chain\n      price\n      totalSupply\n      contractAddress\n      banner\n      __typename\n    }\n    loyaltyPoints {\n      points\n      __typename\n    }\n    loyaltyPointsMysteryBox {\n      points\n      weight\n      __typename\n    }\n    __typename\n  }\n  participants {\n    participantsCount\n    bountyWinnersCount\n    __typename\n  }\n  taskConfig(address: $address) {\n    participateCondition {\n      conditions {\n        ...ExpressionEntity\n        __typename\n      }\n      conditionalFormula\n      eligible\n      __typename\n    }\n    rewardConfigs {\n      id\n      conditions {\n        ...ExpressionEntity\n        __typename\n      }\n      conditionalFormula\n      description\n      rewards {\n        ...ExpressionReward\n        __typename\n      }\n      eligible\n      rewardAttrVals {\n        attrName\n        attrTitle\n        attrVal\n        __typename\n      }\n      __typename\n    }\n    referralConfig {\n      id\n      conditions {\n        ...ExpressionEntity\n        __typename\n      }\n      conditionalFormula\n      description\n      rewards {\n        ...ExpressionReward\n        __typename\n      }\n      eligible\n      rewardAttrVals {\n        attrName\n        attrTitle\n        attrVal\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  referralCode(address: $address)\n  recurringType\n  latestRecurringTime\n  nftTemplates {\n    id\n    image\n    treasureBack\n    __typename\n  }\n  __typename\n}\n\nfragment CampaignMedia on Campaign {\n  thumbnail\n  rewardName\n  type\n  gamification {\n    id\n    type\n    __typename\n  }\n  __typename\n}\n\nfragment CredentialGroupForAddress on CredentialGroup {\n  id\n  description\n  credentials {\n    ...CredForAddressWithoutMetadata\n    __typename\n  }\n  conditionRelation\n  conditions {\n    expression\n    eligible\n    ...CredentialGroupConditionForVerifyButton\n    __typename\n  }\n  rewards {\n    expression\n    eligible\n    rewardCount\n    rewardType\n    __typename\n  }\n  rewardAttrVals {\n    attrName\n    attrTitle\n    attrVal\n    __typename\n  }\n  claimedLoyaltyPoints\n  __typename\n}\n\nfragment CredForAddressWithoutMetadata on Cred {\n  id\n  name\n  type\n  credType\n  credSource\n  referenceLink\n  description\n  lastUpdate\n  lastSync\n  syncStatus\n  credContractNFTHolder {\n    timestamp\n    __typename\n  }\n  chain\n  eligible(address: $address)\n  subgraph {\n    endpoint\n    query\n    expression\n    __typename\n  }\n  dimensionConfig\n  value {\n    gitcoinPassport {\n      score\n      lastScoreTimestamp\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment CredentialGroupConditionForVerifyButton on CredentialGroupCondition {\n  expression\n  eligibleAddress\n  __typename\n}\n\nfragment WhitelistInfoFrag on Campaign {\n  id\n  whitelistInfo(address: $address) {\n    address\n    maxCount\n    usedCount\n    claimedLoyaltyPoints\n    currentPeriodClaimedLoyaltyPoints\n    currentPeriodMaxLoyaltyPoints\n    __typename\n  }\n  __typename\n}\n\nfragment WhitelistSubgraphFrag on Campaign {\n  id\n  whitelistSubgraph {\n    query\n    endpoint\n    expression\n    variable\n    __typename\n  }\n  __typename\n}\n\nfragment GamificationDetailFrag on Gamification {\n  id\n  type\n  nfts {\n    nft {\n      id\n      animationURL\n      category\n      powah\n      image\n      name\n      treasureBack\n      nftCore {\n        ...NftCoreInfoFrag\n        __typename\n      }\n      traits {\n        name\n        value\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  airdrop {\n    name\n    contractAddress\n    token {\n      address\n      icon\n      symbol\n      __typename\n    }\n    merkleTreeUrl\n    addressInfo(address: $address) {\n      index\n      amount {\n        amount\n        ether\n        __typename\n      }\n      proofs\n      __typename\n    }\n    __typename\n  }\n  forgeConfig {\n    minNFTCount\n    maxNFTCount\n    requiredNFTs {\n      nft {\n        category\n        powah\n        image\n        name\n        nftCore {\n          capable\n          contractAddress\n          __typename\n        }\n        __typename\n      }\n      count\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment NftCoreInfoFrag on NFTCore {\n  id\n  capable\n  chain\n  contractAddress\n  name\n  symbol\n  dao {\n    id\n    name\n    logo\n    alias\n    __typename\n  }\n  __typename\n}\n\nfragment ExpressionEntity on ExprEntity {\n  cred {\n    id\n    name\n    type\n    credType\n    credSource\n    dimensionConfig\n    referenceLink\n    description\n    lastUpdate\n    lastSync\n    chain\n    eligible(address: $address)\n    metadata {\n      visitLink {\n        link\n        __typename\n      }\n      twitter {\n        isAuthentic\n        __typename\n      }\n      __typename\n    }\n    commonInfo {\n      participateEndTime\n      modificationInfo\n      __typename\n    }\n    __typename\n  }\n  attrs {\n    attrName\n    operatorSymbol\n    targetValue\n    __typename\n  }\n  attrFormula\n  eligible\n  eligibleAddress\n  __typename\n}\n\nfragment ExpressionReward on ExprReward {\n  arithmetics {\n    ...ExpressionEntity\n    __typename\n  }\n  arithmeticFormula\n  rewardType\n  rewardCount\n  rewardVal\n  __typename\n}\n\nfragment CampaignForgePage on Campaign {\n  id\n  numberID\n  chain\n  spaceStation {\n    address\n    __typename\n  }\n  gamification {\n    forgeConfig {\n      maxNFTCount\n      minNFTCount\n      requiredNFTs {\n        nft {\n          category\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment CampaignForCampaignParticipantsBox on Campaign {\n  ...CampaignForParticipantsDialog\n  id\n  chain\n  space {\n    id\n    isAdmin(address: $address)\n    __typename\n  }\n  participants {\n    participants(first: 10, after: \"-1\", download: false) {\n      list {\n        address {\n          id\n          avatar\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    participantsCount\n    bountyWinners(first: 10, after: \"-1\", download: false) {\n      list {\n        createdTime\n        address {\n          id\n          avatar\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    bountyWinnersCount\n    __typename\n  }\n  __typename\n}\n\nfragment CampaignForParticipantsDialog on Campaign {\n  id\n  name\n  type\n  rewardType\n  chain\n  nftHolderSnapshot {\n    holderSnapshotBlock\n    __typename\n  }\n  space {\n    isAdmin(address: $address)\n    __typename\n  }\n  rewardInfo {\n    discordRole {\n      guildName\n      roleName\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment SpaceDetail on Space {\n  id\n  name\n  info\n  thumbnail\n  alias\n  status\n  links\n  isVerified\n  discordGuildID\n  followersCount\n  nftCores(input: {first: 1}) {\n    list {\n      id\n      marketLink\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment ChildrenCampaignsForCampaignDetailAll on Campaign {\n  space {\n    ...SpaceDetail\n    isAdmin(address: $address) @include(if: $withAddress)\n    isFollowing @include(if: $withAddress)\n    followersCount\n    categories\n    __typename\n  }\n  ...CampaignDetailFrag\n  claimedLoyaltyPoints(address: $address) @include(if: $withAddress)\n  userParticipants(address: $address, first: 1) @include(if: $withAddress) {\n    list {\n      status\n      __typename\n    }\n    __typename\n  }\n  parentCampaign {\n    id\n    isSequencial\n    __typename\n  }\n  __typename\n}\n\nfragment CampaignForSiblingSlide on Campaign {\n  id\n  space {\n    id\n    alias\n    __typename\n  }\n  parentCampaign {\n    id\n    thumbnail\n    isSequencial\n    childrenCampaigns {\n      id\n      ...CampaignForGetImage\n      ...CampaignForCheckFinish\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n\nfragment CampaignForCheckFinish on Campaign {\n  claimedLoyaltyPoints(address: $address)\n  whitelistInfo(address: $address) {\n    usedCount\n    __typename\n  }\n  __typename\n}\n\nfragment CampaignForGetImage on Campaign {\n  ...GetImageCommon\n  nftTemplates {\n    image\n    __typename\n  }\n  __typename\n}\n\nfragment GetImageCommon on Campaign {\n  ...CampaignForTokenObject\n  id\n  type\n  thumbnail\n  __typename\n}\n\nfragment CampaignForTokenObject on Campaign {\n  tokenReward {\n    tokenAddress\n    tokenSymbol\n    tokenDecimal\n    tokenLogo\n    __typename\n  }\n  tokenRewardContract {\n    id\n    chain\n    __typename\n  }\n  __typename\n}\n',
            'variables': {
                'address': self.address,
                'id': campaign_id,
                'withAddress': True,
            },
        }
        return await self.api_request(body, lambda resp: resp['data']['campaign'])

    async def read_quiz(self, quiz_id):
        body = {
            'operationName': 'readQuiz',
            'query': 'query readQuiz($id: ID!) {\n  credential(id: $id) {\n    ...CredQuizFrag\n    __typename\n  }\n}\n\nfragment CredQuizFrag on Cred {\n  credQuiz {\n    quizzes {\n      title\n      type\n      items {\n        value\n        __typename\n      }\n      __typename\n    }\n    __typename\n  }\n  __typename\n}\n',
            'variables': {
                'id': quiz_id,
            },
        }
        return await self.api_request(body, lambda resp: resp['data']['credential']['credQuiz']['quizzes'])

    async def add_typed_credential_items(self, campaign_id, credential_id, captcha):
        body = {
            'operationName': 'AddTypedCredentialItems',
            'query': 'mutation AddTypedCredentialItems($input: MutateTypedCredItemInput!) {\n  typedCredentialItems(input: $input) {\n    id\n    __typename\n  }\n}\n',
            'variables': {
                'input': {
                    'campaignId': campaign_id,
                    'captcha': captcha,
                    'credId': credential_id,
                    'items': [self.address],
                    'operation': 'APPEND',
                }
            }
        }
        await self.api_request(body)

    async def sync_credential_value(self, sync_options, only_allow=True, quiz=False):
        body = {
            'operationName': 'SyncCredentialValue',
            'query': 'mutation SyncCredentialValue($input: SyncCredentialValueInput!) {\n  syncCredentialValue(input: $input) {\n    value {\n      address\n      spaceUsers {\n        follow\n        points\n        participations\n        __typename\n      }\n      campaignReferral {\n        count\n        __typename\n      }\n      gitcoinPassport {\n        score\n        lastScoreTimestamp\n        __typename\n      }\n      walletBalance {\n        balance\n        __typename\n      }\n      multiDimension {\n        value\n        __typename\n      }\n      allow\n      survey {\n        answers\n        __typename\n      }\n      quiz {\n        allow\n        correct\n        __typename\n      }\n      __typename\n    }\n    message\n    __typename\n  }\n}\n',
            'variables': {
                'input': {
                    'syncOptions': sync_options
                },
            },
        }

        def exc_cond(resp):
            value = resp['data']['syncCredentialValue']['value']
            if quiz:
                value = value['quiz']
            return not value['allow']

        return await self.api_request(
            body,
            lambda resp: resp['data']['syncCredentialValue']['value'],
            exc_condition=exc_cond if only_allow else None,
        )

    async def prepare_participate(self, campaign_id, captcha, chain):
        body = {
            'operationName': 'PrepareParticipate',
            'query': 'mutation PrepareParticipate($input: PrepareParticipateInput!) {\n  prepareParticipate(input: $input) {\n    allow\n    disallowReason\n    signature\n    nonce\n    mintFuncInfo {\n      funcName\n      nftCoreAddress\n      verifyIDs\n      powahs\n      cap\n      __typename\n    }\n    extLinkResp {\n      success\n      data\n      error\n      __typename\n    }\n    metaTxResp {\n      metaSig2\n      autoTaskUrl\n      metaSpaceAddr\n      forwarderAddr\n      metaTxHash\n      reqQueueing\n      __typename\n    }\n    solanaTxResp {\n      mint\n      updateAuthority\n      explorerUrl\n      signedTx\n      verifyID\n      __typename\n    }\n    aptosTxResp {\n      signatureExpiredAt\n      tokenName\n      __typename\n    }\n    tokenRewardCampaignTxResp {\n      signatureExpiredAt\n      verifyID\n      __typename\n    }\n    loyaltyPointsTxResp {\n      TotalClaimedPoints\n      __typename\n    }\n    __typename\n  }\n}\n',
            'variables': {
                'input': {
                    'address': self.address,
                    'campaignID': campaign_id,
                    'captcha': captcha,
                    'chain': chain,
                    'mintCount': 1,
                    'signature': '',
                },
            },
        }

        def handle_resp(resp):
            result = resp['data']['prepareParticipate']
            if not result['allow']:
                raise Exception(f'Not allowed, reason: {result["disallowReason"]}')
            return result

        return await self.api_request(body, handle_resp)

    async def participate(self, campaign_id, chain, nonce, tx_hash, verify_id):
        body = {
            'operationName': 'Participate',
            'query': 'mutation Participate($input: ParticipateInput!) {\n  participate(input: $input) {\n    participated\n    __typename\n  }\n}\n',
            'variables': {
                'input': {
                    'address': self.address,
                    'campaignID': campaign_id,
                    'chain': chain,
                    'nonce': nonce,
                    'signature': '',
                    'tx': tx_hash,
                    'verifyIDs': [verify_id],
                },
            },
        }
        await self.api_request(body, exc_condition=lambda resp: not resp['data']['participate']['participated'])

    async def send_verify_code(self, email_username, captcha):
        body = {
            'operationName': 'SendVerifyCode',
            'query': 'mutation SendVerifyCode($input: SendVerificationEmailInput!) {\n  sendVerificationCode(input: $input) {\n    code\n    message\n    __typename\n  }\n}\n',
            'variables': {
                'input': {
                    'address': self.address,
                    'captcha': captcha,
                    'email': email_username,
                },
            },
        }
        await self.api_request(body)

    async def update_email(self, email_username, code):
        body = {
            'operationName': 'UpdateEmail',
            'query': 'mutation UpdateEmail($input: UpdateEmailInput!) {\n  updateEmail(input: $input) {\n    code\n    message\n    __typename\n  }\n}\n',
            'variables': {
                'input': {
                    'address': self.address,
                    'email': email_username,
                    'verificationCode': code,
                },
            },
        }
        await self.api_request(body)

    async def follow_space(self, space_id):
        body = {
            'operationName': 'followSpace',
            'query': 'mutation followSpace($spaceIds: [Int!]) {\n  followSpace(spaceIds: $spaceIds)\n}\n',
            'variables': {
                'spaceIds': [space_id],
            }
        }
        await self.api_request(body, exc_condition=lambda r: r['data']['followSpace'] != 1)

    async def sync_evaluate_credential_value(self, eval_expr, sync_options):
        body = {
            'operationName': 'syncEvaluateCredentialValue',
            'query': 'mutation syncEvaluateCredentialValue($input: SyncEvaluateCredentialValueInput!) {\n  syncEvaluateCredentialValue(input: $input) {\n    result\n    value {\n      allow\n      survey {\n        answers\n        __typename\n      }\n      quiz {\n        allow\n        correct\n        __typename\n      }\n      __typename\n    }\n    message\n    __typename\n  }\n}\n',
            'variables': {
                'input': {
                    'evalExpr': eval_expr,
                    'syncOptions': sync_options
                },
            },
        }
        return await self.api_request(
            body,
            exc_condition=lambda r: not r['data']['syncEvaluateCredentialValue']['result'],
        )