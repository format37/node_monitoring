import requests
from time import sleep, time
import logging
import os
from typing import Tuple


logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')


def check_validator_status(link: str) -> Tuple[bool, str]:
    """
    Check validator status and return whether it requires attention.
    
    Args:
        link: API endpoint URL
        
    Returns:
        Tuple of (is_healthy, status_message)
    """
    try:
        r = requests.get(link)
        if r.status_code != 200:
            return False, f'HTTP error {r.status_code}: {r.text}'
            
        data = r.json()
        if data['status'] != 'OK':
            return False, f'API error: {data["status"]}'
            
        validator_data = data['data']
        if isinstance(validator_data, list):
            status = validator_data[0]['status']
        else:
            status = validator_data['status']
            
        # Define problematic statuses
        problematic_statuses = {
            'active_offline': 'Validator is active but offline',
            'slashed': 'Validator has been slashed',
            'exited_slashed': 'Validator has exited due to slashing',
            'exited': 'Validator has exited',
            'pending': 'Validator is pending activation'
        }
        
        if status in problematic_statuses:
            return False, f'Validator issue: {problematic_statuses[status]}'
        elif status != 'active_online':
            return False, f'Unknown validator status: {status}'
            
        return True, 'Validator is healthy and online'
        
    except requests.exceptions.RequestException as e:
        return False, f'Network error: {str(e)}'
    except Exception as e:
        return False, f'Unexpected error: {str(e)}'


def send_telegram_message(token: str, chat_id: str, message: str) -> None:
    """Send message via Telegram bot."""
    try:
        requests.get(
            f'https://api.telegram.org/bot{token}/sendMessage',
            params={'chat_id': chat_id, 'text': message},
            timeout=10
        )
    except Exception as e:
        logging.error(f'Failed to send Telegram message: {e}')


def main():
    # Load environment variables with defaults
    config = {
        'telegram_token': os.environ.get('BOT_TOKEN', ''),
        'chat_id': os.environ.get('CHAT_ID', ''),
        'link': os.environ.get('LINK', ''),
        'normal_sleep': int(os.environ.get('NORMAL_SLEEP', 600)),
        'fail_sleep': int(os.environ.get('FAIL_SLEEP', 3600)),
        'hourly_reminder': int(os.environ.get('HOURLY_REMINDER', 3600))  # 1 hour in seconds
    }
    
    if not all([config['telegram_token'], config['chat_id'], config['link']]):
        logging.error('Missing required environment variables')
        return
        
    logging.info('Starting the Validator monitoring service')
    send_telegram_message(
        config['telegram_token'],
        config['chat_id'],
        'Validator monitoring started'
    )
    
    previous_status = None
    last_reminder_time = 0
    
    while True:
        try:
            current_time = time()
            is_healthy, status_message = check_validator_status(config['link'])
            
            # Send message if status changes
            if status_message != previous_status:
                send_telegram_message(
                    config['telegram_token'],
                    config['chat_id'],
                    status_message
                )
                previous_status = status_message
                last_reminder_time = current_time
            
            # If not healthy and it's been an hour since last reminder, send status again
            elif not is_healthy and (current_time - last_reminder_time) >= config['hourly_reminder']:
                send_telegram_message(
                    config['telegram_token'],
                    config['chat_id'],
                    f"Reminder: {status_message}"
                )
                last_reminder_time = current_time
                
            sleep_time = config['normal_sleep'] if is_healthy else config['fail_sleep']
            logging.info(f'{status_message}. Sleeping for {sleep_time} seconds')
            sleep(sleep_time)
            
        except Exception as e:
            logging.error(f'Main loop error: {e}')
            sleep(config['fail_sleep'])


if __name__ == '__main__':
    main()