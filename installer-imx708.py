"""Phase-1 first-boot installer for IMX708 (12MP) traps - Bookworm / Python 3.

Runs once from the pi user's crontab (@reboot python3 /home/pi/installer-imx708.py)
on a Pi freshly flashed from the golden image. It:

  1. Waits for internet AND a sane clock (a stale clock makes TLS reject the
     server certificate as "not yet valid" - this crashed the legacy
     installer4.py silently).
  2. Self-tests the camera with rpicam-still.
  3. Generates a password + token and POSTs them to trap_install, creating
     an install candidate in the admin app. All HTTPS calls are retried.
  4. On success: saves token.db, changes the pi password, swaps the crontab
     to the daily runtime (takePic.sh), and shuts down.

The Pi ALWAYS shuts down at the end (success or failure) so a failed install
never leaves the trap running and draining the battery. Progress is written
to /home/pi/install.log. Run manually with --no-shutdown while debugging.
"""

import logging
import random
import string
import subprocess
import sys
import time
from datetime import datetime

import requests

INSTALL_URL = 'https://us-central1-cameraapp-49969.cloudfunctions.net/serverless/trap_install'
LOG_FILE = '/home/pi/install.log'
TOKEN_FILE = '/home/pi/token.db'
DONE_FILE = '/home/pi/install.done'

CONNECTIVITY_SLEEP = 6          # seconds between connectivity checks
CONNECTIVITY_ATTEMPTS = 100     # ~10 minutes
CLOCK_SYNC_TIMEOUT = 300        # max seconds to wait for NTP sync
SANE_YEAR = 2026                # clock is trusted from this year on
SEND_ATTEMPTS = 10
SEND_RETRY_SLEEP = 15


def configure_logging():
    logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                        format='%(asctime)s %(levelname)s : %(message)s',
                        datefmt='%d-%m-%Y %H:%M:%S')


def get_cpu_uid():
    try:
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if line[0:6] == 'Serial':
                    return line[10:26]
    except Exception:
        logging.exception("Couldn't read CPU serial")
    return None


def get_password():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))


def get_token():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=1000))


def get_wifi_name():
    # Bookworm uses NetworkManager; iwgetid is a fallback (wireless-tools).
    try:
        out = subprocess.check_output(
            ['nmcli', '-t', '-f', 'ACTIVE,SSID', 'dev', 'wifi'], text=True, timeout=15)
        for line in out.splitlines():
            if line.startswith('yes:'):
                return line.split(':', 1)[1].strip()
    except Exception:
        pass
    try:
        return subprocess.check_output(['/sbin/iwgetid', '-r'], text=True, timeout=15).strip()
    except Exception:
        logging.exception('Could not determine Wi-Fi SSID')
        return None


def connected_to_internet(url='http://www.google.com/', timeout=10):
    try:
        requests.head(url, timeout=timeout)
        return True
    except requests.RequestException:
        return False


def wait_for_internet():
    for attempt in range(CONNECTIVITY_ATTEMPTS):
        if connected_to_internet():
            logging.info('Internet connection established (attempt %d)', attempt + 1)
            return True
        time.sleep(CONNECTIVITY_SLEEP)
    logging.error('No internet after %d attempts', CONNECTIVITY_ATTEMPTS)
    return False


def clock_is_sane():
    if datetime.now().year >= SANE_YEAR:
        return True
    try:
        out = subprocess.check_output(
            ['timedatectl', 'show', '-p', 'NTPSynchronized', '--value'], text=True, timeout=15)
        return out.strip() == 'yes'
    except Exception:
        return False


def wait_for_sane_clock():
    """A clock stuck in the past makes TLS reject the server certificate
    ("not yet valid"). Wait for NTP; if it never syncs, continue anyway so
    the attempt (and its error) at least gets logged."""
    start = time.time()
    while time.time() - start < CLOCK_SYNC_TIMEOUT:
        if clock_is_sane():
            logging.info('Clock is sane: %s', datetime.now().isoformat())
            return True
        logging.info('Waiting for clock sync (now: %s)', datetime.now().isoformat())
        time.sleep(CONNECTIVITY_SLEEP)
    logging.error('Clock never synced, proceeding anyway')
    return False


def camera_ok():
    try:
        result = subprocess.run(
            ['rpicam-still', '-n', '-t', '2000', '-o', '/home/pi/camera-test.jpg'],
            capture_output=True, text=True, timeout=90)
        if result.returncode == 0:
            logging.info('Camera self-test OK')
            return True
        logging.error('Camera self-test failed: %s', result.stderr)
    except Exception:
        logging.exception('Camera self-test crashed')
    return False


def post_with_retries(body, ssid):
    headers = {'Authorization': 'Bearer ' + 'fiddlesticks' + ssid}
    for attempt in range(1, SEND_ATTEMPTS + 1):
        try:
            response = requests.post(INSTALL_URL, data=body, headers=headers, timeout=120)
        except Exception as e:
            logging.error('trap_install attempt %d/%d failed: %s', attempt, SEND_ATTEMPTS, e)
        else:
            if response.status_code == 200:
                logging.info('trap_install succeeded (attempt %d)', attempt)
                return True
            logging.error('trap_install attempt %d/%d returned %d: %s',
                          attempt, SEND_ATTEMPTS, response.status_code, response.text[:200])
        time.sleep(SEND_RETRY_SLEEP)
    return False


def send_trap_data(uid, password, token, ssid):
    return post_with_retries({'uid': uid, 'password': password, 'token': token}, ssid)


def send_camera_error(uid, ssid):
    return post_with_retries({'uid': uid, 'cameraError': True}, ssid)


def save_token(token):
    with open(TOKEN_FILE, 'w') as f:
        f.write(token)


def change_password(password):
    subprocess.run(['sudo', 'chpasswd'], input='pi:' + password, text=True, check=True)


def activate_runtime_crontab():
    """Replace the installer @reboot entry with the daily runtime."""
    subprocess.run('crontab -r 2>/dev/null; echo "@reboot sudo sh /home/pi/takePic.sh" | crontab -',
                   shell=True, check=True)


def mark_done(status):
    with open(DONE_FILE, 'w') as f:
        f.write(status + ' ' + datetime.now().isoformat())


def shutdown():
    logging.info('Shutting down')
    subprocess.run(['sudo', 'shutdown', '-h', 'now'])


def run_installer():
    logging.info('=================== PHASE-1 INSTALLER START ===================')
    if not wait_for_internet():
        mark_done('failed-no-internet')
        return
    wait_for_sane_clock()

    ssid = get_wifi_name()
    uid = get_cpu_uid()
    logging.info('UID: %s  SSID: %s', uid, ssid)
    if not uid or not ssid:
        logging.error('Missing UID or SSID, aborting')
        mark_done('failed-no-uid-or-ssid')
        return

    if not camera_ok():
        send_camera_error(uid, ssid)
        mark_done('failed-camera')
        return

    password = get_password()
    token = get_token()
    if not send_trap_data(uid, password, token, ssid):
        logging.error('Could not register install candidate, giving up')
        mark_done('failed-trap-install')
        return

    save_token(token)
    change_password(password)
    activate_runtime_crontab()
    mark_done('success')
    logging.info('Install complete - candidate registered, runtime activated')


if __name__ == '__main__':
    configure_logging()
    no_shutdown = '--no-shutdown' in sys.argv
    try:
        run_installer()
    except Exception:
        logging.exception('Installer crashed')
        try:
            mark_done('failed-crash')
        except Exception:
            pass
    finally:
        if no_shutdown:
            logging.info('--no-shutdown given, staying on')
        else:
            shutdown()
