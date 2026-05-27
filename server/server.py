import requests
from time import sleep, time
import logging
import os
from typing import Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Public community-run Beacon Node API (no signup, no API key).
# Standard Beacon Node REST spec, so we can swap in any other compliant
# endpoint by changing this URL.
API_BASE_URL = "https://ethereum-beacon-api.publicnode.com"


def check_validator_status(
    validator_index: int,
    previous_balance: Optional[int],
) -> Tuple[bool, str, Optional[int]]:
    """
    Query the public Beacon Node API for the validator's on-chain state.

    Returns (is_healthy, status_message, current_balance_gwei). The caller
    is expected to feed current_balance back in as previous_balance on the
    next iteration so we can detect inactivity penalties (balance going
    down between checks => validator is missing attestations).
    """
    url = f"{API_BASE_URL}/eth/v1/beacon/states/head/validators/{validator_index}"

    try:
        response = requests.get(url, timeout=30)

        if response.status_code != 200:
            return False, f'HTTP error {response.status_code}: {response.text}', None

        payload = response.json()
        data = payload.get("data")
        if not data:
            return False, 'API returned no validator data', None

        status = data.get("status", "unknown")
        validator = data.get("validator", {})
        slashed = validator.get("slashed", False)

        try:
            current_balance = int(data.get("balance", "0"))
        except (TypeError, ValueError):
            current_balance = None

        issues = []

        if slashed:
            issues.append("SLASHED")

        problematic_statuses = {
            'active_exiting': 'Validator is exiting',
            'active_slashed': 'Validator has been slashed',
            'pending_initialized': 'Validator pending initialization',
            'pending_queued': 'Validator queued for activation',
            'exited_unslashed': 'Validator has exited',
            'exited_slashed': 'Validator exited due to slashing',
            'withdrawal_possible': 'Validator withdrawal available',
            'withdrawal_done': 'Validator withdrawal completed',
        }

        if status in problematic_statuses:
            issues.append(problematic_statuses[status])
        elif status != "active_ongoing":
            issues.append(f"Unknown status: {status}")

        # Balance-trend check: a healthy active validator gains gwei every
        # epoch from attestation rewards (~9 epochs per hour on mainnet),
        # so balance between hourly checks should strictly increase. If it
        # dropped, the validator is missing attestations -> likely offline.
        # Skipped on the first iteration (previous_balance is None) to
        # establish a baseline.
        if (
            not issues
            and previous_balance is not None
            and current_balance is not None
            and current_balance < previous_balance
        ):
            delta_gwei = previous_balance - current_balance
            issues.append(
                f"OFFLINE (balance dropped {delta_gwei} gwei since last check)"
            )

        if issues:
            return False, f'Validator issues: {", ".join(issues)}', current_balance

        return True, 'Validator is healthy and online', current_balance

    except requests.exceptions.Timeout:
        return False, 'API request timed out', None
    except requests.exceptions.RequestException as e:
        return False, f'Network error: {str(e)}', None
    except Exception as e:
        return False, f'Unexpected error: {str(e)}', None


def send_telegram_message(token: str, chat_id: str, message: str) -> None:
    try:
        requests.get(
            f'https://api.telegram.org/bot{token}/sendMessage',
            params={'chat_id': chat_id, 'text': message},
            timeout=10
        )
    except Exception as e:
        logging.error(f'Failed to send Telegram message: {e}')


def main():
    config = {
        'telegram_token': os.environ.get('BOT_TOKEN', ''),
        'chat_id': os.environ.get('CHAT_ID', ''),
        'validator_index': os.environ.get('VALIDATOR_INDEX', ''),
        'normal_sleep': int(os.environ.get('NORMAL_SLEEP', 3600)),
        'fail_sleep': int(os.environ.get('FAIL_SLEEP', 600)),
        'hourly_reminder': int(os.environ.get('HOURLY_REMINDER', 3600))
    }

    required_vars = ['telegram_token', 'chat_id', 'validator_index']
    missing = [var for var in required_vars if not config[var]]

    if missing:
        logging.error(f'Missing required environment variables: {", ".join(missing)}')
        logging.error('Required: BOT_TOKEN, CHAT_ID, VALIDATOR_INDEX')
        return

    try:
        config['validator_index'] = int(config['validator_index'])
    except ValueError:
        logging.error(f'VALIDATOR_INDEX must be an integer, got: {config["validator_index"]}')
        return

    logging.info(f'Starting Validator monitoring service for validator {config["validator_index"]}')
    logging.info(f'Using public Beacon Node API at {API_BASE_URL} with {config["normal_sleep"]}s polling interval')

    send_telegram_message(
        config['telegram_token'],
        config['chat_id'],
        f'Validator monitoring started (public Beacon API) - Validator #{config["validator_index"]}'
    )

    previous_status = None
    previous_balance: Optional[int] = None
    last_reminder_time = 0

    while True:
        try:
            current_time = time()
            is_healthy, status_message, current_balance = check_validator_status(
                config['validator_index'],
                previous_balance,
            )

            if current_balance is not None:
                previous_balance = current_balance

            if status_message != previous_status:
                send_telegram_message(
                    config['telegram_token'],
                    config['chat_id'],
                    status_message
                )
                previous_status = status_message
                last_reminder_time = current_time

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
