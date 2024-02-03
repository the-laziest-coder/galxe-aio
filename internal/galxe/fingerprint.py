from asyncio import Lock
from loguru import logger
from playwright.async_api import async_playwright

from ..vars import GALXE_CAPTCHA_ID
from ..utils import get_query_param


class Fingerprints:

    def __init__(self):
        self.current_fingerprint = None
        self.lock = Lock()

    async def _generate_new_no_lock(self):
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=[
                '--lang=en-US,en',
                '--disable-blink-features=AutomationControlled',
            ])
            context = await browser.new_context()
            await context.add_init_script('() => {}')
            fingerprint = ''
            try:
                page = await context.new_page()
                await page.goto('https://galxe.com/protocol', wait_until='domcontentloaded', timeout=15000)
                await page.evaluate(f'''
                    window.initGeetest4({{captchaId: "{GALXE_CAPTCHA_ID}", product: "bind"}})
                ''')
                async with page.expect_response(lambda resp: resp.status == 200 and 'verify' in resp.url,
                                                timeout=15000) as r:
                    fingerprint = get_query_param((await r.value).url, 'w')
            except Exception as e:
                logger.error(f'Failed to get fingerprint: {str(e)}')
            await context.close()
            await browser.close()
            self.current_fingerprint = fingerprint
            if self.current_fingerprint != '':
                logger.success(f'Successfully fetched fingerprint for captcha')

    async def generate_new(self):
        async with self.lock:
            await self._generate_new_no_lock()

    async def get(self) -> str:
        async with self.lock:
            if self.current_fingerprint is None or self.current_fingerprint == '':
                await self._generate_new_no_lock()
            return self.current_fingerprint


fingerprints = Fingerprints()


def captcha_retry(async_func):
    async def wrapper(*args, **kwargs):
        try:
            return await async_func(*args, **kwargs)
        except Exception as e:
            if 'recaptcha' in str(e):
                logger.info('Recaptcha error. Trying to update fingerprint')
                await fingerprints.generate_new()
                return await async_func(*args, **kwargs)
            raise

    return wrapper
