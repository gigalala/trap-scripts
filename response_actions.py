from os import system
import requests
import time
import os

GITHUB_URL = 'https://github.com/gigalala/trap-scripts.git'
LOG_URL = 'https://us-central1-cameraapp-49969.cloudfunctions.net/serverless/trap_log'


def change_battery():
    return -1


def stay_on():
    return True


def send_log(token, trap_id, delete=False):
    my_files = {'file': open('trap.log', 'rb')}
    res = requests.post(LOG_URL, data={'trapId': trap_id, 'time': time.time()},
                        headers={"Authorization": "Bearer " + token}, files=my_files, timeout=10)
    if res.code == 200 and delete:
        os.remove('trap.log')


def update(version='main'):
    branch = None
    if version:
        branch = version
    system('rm -rf trap-scripts')
    system('git clone --branch '+branch + " " + GITHUB_URL)
    system('mv trap-scripts/* .')
