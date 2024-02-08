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
    VISIT_LINK = 'VISIT_LINK'
    QUIZ = 'QUIZ'
    SPACE_USERS = 'SPACE_USERS'


class ConditionRelation(StrEnum):
    ALL = 'ALL'
    ANY = 'ANY'


class QuizType(StrEnum):
    MULTI_CHOICE = 'MULTI_CHOICE'


class Gamification(StrEnum):
    POINTS = 'Points'
    OAT = 'Oat'
    POINTS_MYSTERY_BOX = 'PointsMysteryBox'
