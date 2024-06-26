import requests
from time import sleep
import logging
import os


logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')


def check_availability(link):
    r = None
    try:
        r = requests.get(link)
        status_ok = False
        if r.status_code == 200:
            if type(r.json()['data']) == type([]):
                status = r.json()['data'][0]['status']
            else:
                status = r.json()['data']['status']            
            if status == 'active_online':
                return True, status
        else:
            return False, 'check status: '+str(r.json())
    except Exception as e:
        logging.info(str("Unable to read r: "+str(r)))
        return False, str(e)+' Please, check status: '+str(r.json())


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
        r = None
        try:
            availability, r = check_availability(link)
            if availability:
                if not test_ok:
                    requests.get('https://api.telegram.org/bot{}/sendMessage?chat_id={}&text=Node is up'.format(telegram_token, chat_id))
                    test_ok = True
                sleep(normal_sleep)
                continue
            else:
                logging.info('Server is down:')
                logging.info(str(r))
                test_ok = False
        except Exception as e:
            logging.info('Exception:')
            logging.info(e)
            r = str(e)
            test_ok = False
        if test_ok == False:
            requests.get('https://api.telegram.org/bot{}/sendMessage?chat_id={}&text=Server is down: {}. Sleeping {} seconds'.format(telegram_token, chat_id, str(r), fail_sleep))
            sleep(fail_sleep)


if __name__ == '__main__':
    main()
