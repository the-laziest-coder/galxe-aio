import secrets
import math
import random


alp = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'


def random_string(e, n=alp):
    o = ''
    f = len(n)
    h = 256 - 256 % f
    while e > 0:
        t = secrets.token_bytes(math.ceil(256 * e / h))
        i = 0
        while i < len(t) and e > 0:
            r = t[i]
            if r < h:
                o += n[r % f]
                e -= 1
            i += 1
    return o


def random_string_for_entropy(e, n=alp):
    return random_string(math.ceil(e / (math.log(len(n)) / math.log(2))))


def random_user_prefix(n=3):
    prefix = ''
    for _ in range(n):
        prefix += random.choice(alp[-26:])
    return prefix
