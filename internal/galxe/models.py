from enum import StrEnum


class Recurring(StrEnum):
    DAILY = 'DAILY'


class Credential(StrEnum):
    TWITTER = 'TWITTER'
    EMAIL = 'EMAIL'
    EVM_ADDRESS = 'EVM_ADDRESS'
    GALXE_ID = 'GALXE_ID'
    DISCORD = 'DISCORD'


class CredSource(StrEnum):
    TWITTER_FOLLOW = 'TWITTER_FOLLOW'
    TWITTER_RT = 'TWITTER_RT'
    TWITTER_LIKE = 'TWITTER_LIKE'
    TWITTER_QUOTE = 'TWITTER_QUOTE'
    VISIT_LINK = 'VISIT_LINK'
    QUIZ = 'QUIZ'
    SURVEY = 'SURVEY'
    SPACE_USERS = 'SPACE_USERS'
    WATCH_YOUTUBE = 'WATCH_YOUTUBE'
    CSV = 'CSV'


class ConditionRelation(StrEnum):
    ALL = 'ALL'
    ANY = 'ANY'


class QuizType(StrEnum):
    MULTI_CHOICE = 'MULTI_CHOICE'


class Gamification(StrEnum):
    POINTS = 'Points'
    OAT = 'Oat'
    POINTS_MYSTERY_BOX = 'PointsMysteryBox'
    DROP = 'Drop'
    BOUNTY = 'Bounty'
    DISCORD_ROLE = 'DiscordRole'
    TOKEN = 'Token'


class GasType(StrEnum):
    GAS_LESS = 'Gasless'
    GAS = 'Gas'
