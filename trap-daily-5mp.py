#VERSION = 1.0f
import requests
import base64
from datetime import datetime
from os import path
from os import system
from picamera import PiCamera
import sys
import time
import logging


REBOOT_TIME = 600 # 10 min 
CONNECTIVITY_SLEEP_TIME = 10 # 10 sec
SLEEP_BEFORE_SHUTDOWN = 180 # 3 min 
URL = 'https://us-central1-cameraapp-49969.cloudfunctions.net/serverless/trap_image'

camera = PiCamera()


def connected_to_internet(url='http://www.google.com/', timeout=10):
    try:
        _ = requests.head(url, timeout=timeout)
        return True
    except requests.ConnectionError:
        logging.info("No internet connection available.")
    return False


def get_serial():
    cpu_serial = None
    try:
        f = open('/proc/cpuinfo', 'r')
        for line in f:
            if line[0:6]=='Serial':
                cpu_serial = line[10:26]
        f.close()
    except:
        return None
    return cpu_serial


def get_token():
    token_trap = None
    if path.exists('token.db'):
        file = open('token.db', "r")
        token_trap = file.read().strip()
        file.close()
        if not token_trap:
            return None
    return token_trap


def get_test_mode():
    if path.exists('testMode.db'):
        file = open('testMode.db', "r")
        test_mode = file.read().strip()
        file.close()
        if not test_mode:
            return None
        if test_mode == "true":
            return True
        elif test_mode == "false":
            return False
    return None


def take_pic():
    logging.info("taking image")
    camera.resolution = (2592,1944)
    camera.capture("latest.jpg")
    logging.info("image taken and saved")


def send_pic():
    body_headers = get_body_and_headers()
    if not body_headers:
        return
    oldtime = time.time()
    result = wait_for_connectivity(oldtime)
    if not result:
        return true
    logging.info('connected to internet')
    result = send_request(oldtime,body_headers.body,body_headers.headers)
    if not result:
        return true

    if res.status_code == 200:
        logging.info("image sent")
    else:
        logging.error("error, image did not sent - " + res.text)



def get_body_and_headers():
    logging.info('get serial')
    trap_id = get_serial()
    logging.info('get token')
    token = get_token()
    logging.info('get test mode')
    test_mode = get_test_mode()
    if not trap_id:
        logging.error("fatal error no serial for pi")
        return
    if not token:
        logging.error("fatal error no token for pi")
        return
    if test_mode == None:
        logging.error("Trap is off, no test or production set")
        return
    logging.info('before open image')
    with open('latest.jpg', "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read())
    logging.info('get time')
    image_name = datetime.now().strftime("%d-%m-%Y-%H_%M") + ".jpg"
    body = {'image': encoded_string, 'trapId': trap_id, 'imageName': image_name, 'testMode': test_mode}
    headers = {"Authorization": "Bearer "+token}
    reutrn(body,headers)

def wait_for_connectivity(oldtime):
    time.sleep(CONNECTIVITY_SLEEP_TIME)
    while not connected_to_internet():
        time.sleep(CONNECTIVITY_SLEEP_TIME)
        if time.time() - oldtime > REBOOT_TIME:
            return false
    return true

def send_request(oldtim,body,headers):
    while True:
        try:
            logging.info('trying to send')
            res = requests.post(URL, data=body, headers=headers)
        except Exception as e:
            logging.error(str(e))
            time.sleep(CONNECTIVITY_SLEEP_TIME)
            if time.time() - oldtime > REBOOT_TIME:
                return false
        else:
            logging.info('request made')
            return res

def main():
    logger_format = '%(asctime)s.%(msecs)03d %(levelname)s : %(message)s'
    logging.basicConfig(filename="trap.log", level=logging.DEBUG,datefmt='%d-%m-%Y %H:%M:%S',format=logger_format)
    try:
        take_pic()
        reboot = send_pic()
        if reboot:
            logging.info('rebooting')
            system('reboot')
    except Exception as e:
        logging.error(str(e))
    time.sleep(SLEEP_BEFORE_SHUTDOWN)
    system("shutdown now -h") 

main()  