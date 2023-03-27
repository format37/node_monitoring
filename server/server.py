import requests
from time import sleep
import logging
import os


logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')


def check_availability(link):
    try:
        r = requests.get(link)
        if r.status_code == 200 and r.json()['data']['status'] == 'active_online':
            return True, r.json()['data']['status']
        else:
            return False, r.json()['data']['status']
    except Exception as e:
        logging.info(str(r.json()))
        return False, str(e)


def main():
    test_ok = False
    telegram_token = os.environ.get('BOT_TOKEN', '')
    chat_id = os.environ.get('CHAT_ID', '')
    link = os.environ.get('LINK', '')
    normal_sleep = int(os.environ.get('NORMAL_SLEEP', 600))
    fail_sleep = int(os.environ.get('FAIL_SLEEP', 3600))
    logging.info('Starting the Node monitoring server')
    requests.get('https://api.telegram.org/bot{}/sendMessage?chat_id={}&text=Node monitoring started'.format(telegram_token, chat_id))
    while True:
        availability, r = check_availability(link)
        if availability:
            if not test_ok:
                requests.get('https://api.telegram.org/bot{}/sendMessage?chat_id={}&text=Node is up'.format(telegram_token, chat_id))
                test_ok = True
            sleep(normal_sleep)
        else:
            logging.info('Server is down:')
            try:
                logging.info(r)
            except Exception as e:
                logging.info(e)
                r = str(e)

            test_ok = False
            
            requests.get('https://api.telegram.org/bot{}/sendMessage?chat_id={}&text=Server is down: {}. Sleeping {} seconds'.format(telegram_token, chat_id, r, fail_sleep))
            sleep(fail_sleep)


if __name__ == '__main__':
    main()
