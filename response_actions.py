from os import system
import requests
import time
import os

# New development home. The legacy fleet still clones gigalala/trap-scripts
# (kept as a frozen mirror of the legacy branches).
GITHUB_URL = 'https://github.com/avihai-aharon/trap-scripts.git'
LOG_URL = 'https://us-central1-cameraapp-49969.cloudfunctions.net/serverless/trap_log'
STATUS_URL = 'https://us-central1-cameraapp-49969.cloudfunctions.net/serverless/trap_status'
RUN_TIME_URL = 'https://us-central1-cameraapp-49969.cloudfunctions.net/serverless/trap_run_time'

# OTA self-update default: IMX708 (12MP) traps must pull the libcamera-based
# code, never 'main' (which is the legacy picamera stack).
DEFAULT_BRANCH = 'imx708-voltic-daily'


def change_battery():
    return -1

def stay_on():
    return True

def send_log(token, trap_id, delete=False):
    my_files = {'file': open('trap.log', 'rb')}
    res = requests.post(LOG_URL, data={'trapId': trap_id, 'time': time.time()},
                        headers={"Authorization": "Bearer " + token}, files=my_files, timeout=10)
    if res.status_code == 200 and delete:
        os.remove('trap.log')
    return res.status_code

def update(version=DEFAULT_BRANCH):
    branch = version if version else DEFAULT_BRANCH
    system('rm -rf trap-scripts')
    response_code = system('git clone --branch ' + branch + " " + GITHUB_URL)
    if response_code == 0:
        # Copy only the flat runtime files. The old `mv trap-scripts/* .`
        # breaks on repeat updates once the branch contains directories
        # (mv refuses to overwrite non-empty dirs like provisioning/).
        system('cp -f trap-scripts/*.py trap-scripts/*.sh .')
        system('rm -rf trap-scripts')
    return response_code

def get_trap_status(token, trap_id):
    res = requests.get(STATUS_URL+"/"+trap_id,
                        headers={"Authorization": "Bearer " + token}, timeout=10)
    return res.json(), res.status_code

def send_run_time(token, trap_id, run_time):
    res = requests.post(RUN_TIME_URL, data={'trapId': trap_id, 'runTime': run_time},
                        headers={"Authorization": "Bearer " + token}, timeout=10)
    return res.status_code
