import requests
from time import sleep, time
import logging
import os
from typing import Tuple
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# API Configuration
API_BASE_URL = "https://beaconcha.in"


def get_headers(api_key: str) -> dict:
    """Return headers with Bearer token authentication."""
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }


def check_validator_status(api_key: str, validator_index: int) -> Tuple[bool, str]:
    """
    Check validator status using v2 API and return whether it requires attention.

    Args:
        api_key: Beaconcha.in API key for Bearer authentication
        validator_index: Validator index number

    Returns:
        Tuple of (is_healthy, status_message)
    """
    url = f"{API_BASE_URL}/api/v2/ethereum/validators"
    payload = {
        "validator": {
            "validator_identifiers": [validator_index]
        }
    }

    try:
        response = requests.post(
            url,
            json=payload,
            headers=get_headers(api_key),
            timeout=30
        )

        if response.status_code != 200:
            return False, f'HTTP error {response.status_code}: {response.text}'

        data = response.json()

        # v2 API returns data directly in "data" array
        if not data.get("data") or len(data["data"]) == 0:
            return False, 'API returned no validator data'

        validator = data["data"][0]

        status = validator.get("status", "unknown")
        online = validator.get("online")  # Can be True, False, or None
        slashed = validator.get("slashed", False)

        # Collect issues
        issues = []

        # Check for slashing (critical)
        if slashed:
            issues.append("SLASHED")

        # Check online status
        if online is False:
            issues.append("OFFLINE")

        # Check status (should be "active_ongoing" for healthy validator)
        problematic_statuses = {
            'active_exiting': 'Validator is exiting',
            'active_slashed': 'Validator has been slashed',
            'pending_initialized': 'Validator pending initialization',
            'pending_queued': 'Validator queued for activation',
            'exited_unslashed': 'Validator has exited',
            'exited_slashed': 'Validator exited due to slashing',
            'withdrawal_possible': 'Validator withdrawal available',
            'withdrawal_done': 'Validator withdrawal completed'
        }

        if status in problematic_statuses:
            issues.append(problematic_statuses[status])
        elif status != "active_ongoing":
            issues.append(f"Unknown status: {status}")

        if issues:
            return False, f'Validator issues: {", ".join(issues)}'

        # Include balance info in healthy message
        try:
            balance_wei = int(validator.get("balances", {}).get("current", 0))
            balance_eth = balance_wei / 1e18
            return True, f'Validator is healthy and online (Balance: {balance_eth:.4f} ETH)'
        except (ValueError, TypeError):
            return True, 'Validator is healthy and online'

    except requests.exceptions.Timeout:
        return False, 'API request timed out'
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
    # Load configuration from environment variables
    config = {
        'telegram_token': os.environ.get('BOT_TOKEN', ''),
        'chat_id': os.environ.get('CHAT_ID', ''),
        'api_key': os.environ.get('BEACONCHAIN_API_KEY', ''),
        'validator_index': os.environ.get('VALIDATOR_INDEX', ''),
        'normal_sleep': int(os.environ.get('NORMAL_SLEEP', 3600)),
        'fail_sleep': int(os.environ.get('FAIL_SLEEP', 600)),
        'hourly_reminder': int(os.environ.get('HOURLY_REMINDER', 3600))
    }

    # Validate required configuration
    required_vars = ['telegram_token', 'chat_id', 'api_key', 'validator_index']
    missing = [var for var in required_vars if not config[var]]

    if missing:
        logging.error(f'Missing required environment variables: {", ".join(missing)}')
        logging.error('Required: BOT_TOKEN, CHAT_ID, BEACONCHAIN_API_KEY, VALIDATOR_INDEX')
        return

    # Convert validator_index to integer
    try:
        config['validator_index'] = int(config['validator_index'])
    except ValueError:
        logging.error(f'VALIDATOR_INDEX must be an integer, got: {config["validator_index"]}')
        return

    logging.info(f'Starting Validator monitoring service for validator {config["validator_index"]}')
    logging.info(f'Using v2 API with {config["normal_sleep"]}s polling interval')

    send_telegram_message(
        config['telegram_token'],
        config['chat_id'],
        f'Validator monitoring started (v2 API) - Validator #{config["validator_index"]}'
    )

    previous_status = None
    last_reminder_time = 0

    while True:
        try:
            current_time = time()
            is_healthy, status_message = check_validator_status(
                config['api_key'],
                config['validator_index']
            )

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
