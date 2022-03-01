from os import system
import requests
import time
import os

GITHUB_URL = 'https://github.com/gigalala/trap-scripts.git'
LOG_URL = 'https://us-central1-cameraapp-49969.cloudfunctions.net/serverless/trap_log'
STATUS_URL = 'https://us-central1-cameraapp-49969.cloudfunctions.net/serverless/trap_status'
RUN_TIME_URL = 'https://us-central1-cameraapp-49969.cloudfunctions.net/serverless/trap_run_time'


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

def update(version='main'):
    branch = None
    if version:
        branch = version
    system('rm -rf trap-scripts')
    response_code = system('git clone --branch ' + branch + " " + GITHUB_URL)
    system('mv trap-scripts/* .')
    return response_code

def get_trap_status(token, trap_id):
    res = requests.get(STATUS_URL+"/"+trap_id,
                        headers={"Authorization": "Bearer " + token}, timeout=10)
    if res.status_code == 200:
        return res.json()

def send_run_time(token, trap_id, run_time):
    res = requests.post(RUN_TIME_URL, data={'trapId': trap_id, 'runTime': run_time},
                        headers={"Authorization": "Bearer " + token}, timeout=10)
    return res.status_code
