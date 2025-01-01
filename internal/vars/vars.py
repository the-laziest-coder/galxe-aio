import platform


USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
SEC_CH_UA = '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"'
SEC_CH_UA_PLATFORM = '"macOS"'


if platform.system() == 'Windows':
    USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    SEC_CH_UA = '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"'



GALXE_CAPTCHA_ID = '244bcb8b9846215df5af4c624a750db4'
