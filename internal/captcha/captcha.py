import json
import asyncio
import aiohttp
from enum import Enum
from loguru import logger
from urllib.parse import urlparse

from ..utils import async_retry, get_proxy_url
from ..config import TWO_CAPTCHA_API_KEY, CAP_MONSTER_API_KEY, CAP_SOLVER_API_KEY, DISABLE_SSL
from ..vars import USER_AGENT

from .constants import TWO_CAPTCHA_API_URL, CAP_MONSTER_API_URL, CAP_SOLVER_API_URL


def solve_captcha_retry(async_func):
    async def wrapper(idx, *args, **kwargs):
        last_exc = None
        for _ in range(5):
            try:
                return await async_func(idx, *args, **kwargs)
            except Exception as e:
                last_exc = e
        if last_exc is not None:
            raise last_exc

    return wrapper


class TaskType(Enum):
    RECAPTCHA_V2 = 'RecaptchaV2Task'
    RECAPTCHA_V3 = 'RecaptchaV3Task'
    RECAPTCHA_V3_PROXY_LESS = 'RecaptchaV3TaskProxyless'
    TURNSTILE_TASK = 'TurnstileTask'
    ANTI_CLOUDFLARE_TASK = 'AntiCloudflareTask'
    GEETEST = 'GeeTestTask'


@solve_captcha_retry
async def solve_recaptcha_v2(idx, url, site_key, proxy=None, **kwargs):
    if CAP_SOLVER_API_KEY:
        return await _solve_captcha(
            CAP_SOLVER_API_URL, CAP_SOLVER_API_KEY, TaskType.RECAPTCHA_V2,
            idx, url, site_key, proxy, proxy_one_line=True,
            userAgent=USER_AGENT, **kwargs,
        )
    elif TWO_CAPTCHA_API_KEY:
        return await _solve_captcha(
            TWO_CAPTCHA_API_URL, TWO_CAPTCHA_API_KEY, TaskType.RECAPTCHA_V2,
            idx, url, site_key, proxy, userAgent=USER_AGENT, **kwargs,
        )
    elif CAP_MONSTER_API_KEY:
        return await _solve_captcha(
            CAP_MONSTER_API_URL, CAP_MONSTER_API_KEY, TaskType.RECAPTCHA_V2,
            idx, url, site_key, proxy, userAgent=USER_AGENT, **kwargs,
        )
    else:
        raise Exception('No captcha service API keys specified for recaptcha v2')


@solve_captcha_retry
async def solve_recaptcha_v3(idx, url, site_key, page_action, proxy=None, **kwargs):
    if CAP_SOLVER_API_KEY:
        return await _solve_captcha(
            CAP_SOLVER_API_URL, CAP_SOLVER_API_KEY, TaskType.RECAPTCHA_V3,
            idx, url, site_key, proxy, proxy_one_line=True,
            pageAction=page_action, minScore=0.9, userAgent=USER_AGENT, **kwargs,
        )
    elif TWO_CAPTCHA_API_KEY:
        return await _solve_captcha(
            TWO_CAPTCHA_API_URL, TWO_CAPTCHA_API_KEY, TaskType.RECAPTCHA_V3_PROXY_LESS,
            idx, url, site_key, proxy, pageAction=page_action, minScore=0.9, userAgent=USER_AGENT, **kwargs,
        )
    elif CAP_MONSTER_API_KEY:
        return await _solve_captcha(
            CAP_MONSTER_API_URL, CAP_MONSTER_API_KEY, TaskType.RECAPTCHA_V3_PROXY_LESS,
            idx, url, site_key, proxy, pageAction=page_action, minScore=0.9, userAgent=USER_AGENT, **kwargs,
        )
    else:
        raise Exception('No captcha service API keys specified for recaptcha v3')


@solve_captcha_retry
async def solve_cloudflare_challenge(idx, url, site_key, proxy):
    if TWO_CAPTCHA_API_KEY:
        return await _solve_captcha(
            TWO_CAPTCHA_API_URL, TWO_CAPTCHA_API_KEY, TaskType.TURNSTILE_TASK,
            idx, url, site_key, proxy=proxy, userAgent=USER_AGENT,
        )
    else:
        raise Exception('No captcha service API keys specified for cloudflare')


async def solve_geetest(idx, url, proxy, gt, challenge, version, init_parameters):
    if CAP_SOLVER_API_KEY:
        return await _solve_captcha(
            CAP_SOLVER_API_URL, CAP_SOLVER_API_KEY, TaskType.GEETEST,
            idx, url, proxy=proxy, proxy_one_line=True, challenge=challenge, captchaId=gt,
        )
    elif TWO_CAPTCHA_API_KEY:
        return await _solve_captcha(
            TWO_CAPTCHA_API_URL, TWO_CAPTCHA_API_KEY, TaskType.GEETEST,
            idx, url, proxy=proxy, userAgent=USER_AGENT, gt=gt, challenge=challenge,
            version=version, initParameters=init_parameters,
        )
    elif CAP_MONSTER_API_KEY:
        return await _solve_captcha(
            CAP_MONSTER_API_URL, CAP_MONSTER_API_KEY, TaskType.GEETEST,
            idx, url, proxy=proxy, userAgent=USER_AGENT, gt=gt, challenge=challenge,
            version=version, initParameters=init_parameters,
        )
    else:
        raise Exception('No captcha service API keys specified for geetest')


async def _solve_captcha(api_url, client_key,
                         task_type, idx, url, site_key='',
                         proxy=None, proxy_one_line=False,
                         **additional_task_properties):
    create_task_req = {
        'clientKey': client_key,
        'task': {
            'type': task_type.value,
            'websiteURL': url,
            **additional_task_properties,
        },
    }

    ref_name, ref_value = None, None
    if api_url == CAP_SOLVER_API_URL:
        ref_name, ref_value = 'appId', '373E3CAC-2E7E-4748-B107-908AC039873D'
    elif api_url == TWO_CAPTCHA_API_URL:
        ref_name, ref_value = 'softId', 4669
    if ref_name is not None:
        create_task_req[ref_name] = ref_value

    if site_key:
        create_task_req['task']['websiteKey'] = site_key
    proxy = get_proxy_url(proxy)
    if proxy and 'Proxyless' not in task_type.value:
        if proxy_one_line:
            create_task_req['task'].update({
                'proxy': proxy,
            })
        else:
            parsed_proxy = urlparse(proxy)
            create_task_req['task'].update({
                'proxyType': parsed_proxy.scheme,
                'proxyAddress': parsed_proxy.hostname,
                'proxyPort': parsed_proxy.port,
                'proxyLogin': parsed_proxy.username,
                'proxyPassword': parsed_proxy.password,
            })

    req_kwargs = {}
    if DISABLE_SSL:
        req_kwargs['ssl'] = False

    @async_retry
    async def create_task():
        async with aiohttp.ClientSession() as sess:
            async with sess.post(f'{api_url}/createTask', json=create_task_req, **req_kwargs) as resp:
                result = json.loads(await resp.text())
                if result['errorId'] != 0:
                    raise Exception(f'Create task error {result.get("errorCode")}: '
                                    f'{result.get("errorDescription")}')
                return result['taskId']

    async def get_task_result(tid):
        async with aiohttp.ClientSession() as sess:
            async with sess.post(f'{api_url}/getTaskResult', json={
                'clientKey': client_key,
                'taskId': tid,
            }, **req_kwargs) as resp:
                result = json.loads(await resp.text())
                if result['errorId'] != 0:
                    raise Exception(f'Get task result error {result.get("errorCode")}: '
                                    f'{result.get("errorDescription")}')
                return result.get('status'), result.get('solution')

    logger.info(f'{idx}) Creating captcha task')
    task_id = await create_task()
    logger.info(f'{idx}) Waiting for captcha solution: {task_id}')
    waited, response = 0, None
    while waited <= 180:
        await asyncio.sleep(10)
        waited += 10
        status, solution = await get_task_result(task_id)
        logger.info(f'{idx}) Captcha task status: {status}')
        if solution is None:
            continue
        if 'GeeTestTask' in task_type.value:
            response = solution
        elif 'TurnstileTask' in task_type.value:
            response = solution['token']
        else:
            response = solution['gRecaptchaResponse']
        break
    if response is None:
        raise Exception(f'Captcha solving takes too long')
    logger.success(f'{idx}) Captcha solution received')
    return response
