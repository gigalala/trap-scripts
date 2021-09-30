# VERSION = 1.1f
import requests
import base64
from datetime import datetime
from os import path
from os import system
from response_actions import change_battery, stay_on, update
# from picamera import PiCamera
import time
import logging
import subprocess
import json

FAIL_REBOOT_ATTEMPTS = 3
REBOOT_TIME = 600  # 10 min
CONNECTIVITY_SLEEP_TIME = 10  # 10 sec
SLEEP_BEFORE_SHUTDOWN = 180  # 3 min
URL = 'https://us-central1-cameraapp-49969.cloudfunctions.net/serverless/trap_image'
BOOT_DATA_FILE_PATH = "trap.data"
STARTUP_TIMES = ['8', '9', '10', '11', '12', '13', '14', '15', '16']

# Boot data
boot_count = None
startup_time = None
run_time = None
image_taken_today = None
should_stay_on = False
start_time = time.time()


# camera = PiCamera()


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
            if line[0:6] == 'Serial':
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


def read_trap_boot_data():
    global boot_count, startup_time, run_time, image_taken_today
    if path.isfile(BOOT_DATA_FILE_PATH):
        with open(BOOT_DATA_FILE_PATH) as file:
            config = json.load(file)
        boot_count = config['boot_count']
        startup_time = config['startup_time']
        run_time = config['run_time']
        image_taken_today = config['image_taken_today']
        file.close()
    else:
        boot_count = 0
        startup_time = 0
        run_time = 0
        image_taken_today = False


def write_trap_boot_data():
    file = open(BOOT_DATA_FILE_PATH, "w")
    json.dump(
        {'boot_count': boot_count, 'startup_time': int(startup_time),
         'run_time': run_time, 'image_taken_today': image_taken_today}, file)
    file.close()


def take_pic():
    logging.info("taking image")
    # camera.resolution = (2592, 1944)
    # camera.capture("latest.jpg")
    global image_taken_today
    image_taken_today = True
    logging.info("image taken and saved")


def send_pic():
    body, headers = get_body_and_headers()
    if not body or not headers:
        return
    old_time = time.time()
    result = wait_for_connectivity(old_time)
    if not result:
        return True
    logging.info('connected to internet')
    result = send_request(old_time, body, headers)
    if not result:
        return True

    if result.status_code == 200:
        logging.info("image sent")
        data = result.json()
    else:
        logging.error("error, image did not sent - " + result.text)


def check_response_for_actions(data):
    global should_stay_on, run_time
    if data['action'] == "none":
        logging.info("no response action was received")
    elif data['action'] == "stayOn":
        logging.info("stay on response action was received")
        should_stay_on = stay_on()
    elif data['action'] == "changeBattery":
        logging.info("change battery response action was received")
        run_time = change_battery()
    elif data['action'] == "update":
        logging.info("update response action was received")
        update(data['value'])


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
    if test_mode is None:
        logging.error("Trap is off, no test or production set")
        return
    logging.info('before open image')
    with open('latest.jpg', "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read())
    logging.info('get time')
    image_name = datetime.now().strftime("%d-%m-%Y-%H_%M") + ".jpg"
    number_of_boots = startup_time * FAIL_REBOOT_ATTEMPTS + boot_count
    body = {'image': encoded_string, 'trapId': trap_id, 'imageName': image_name, 'testMode': test_mode,
            'runTime': run_time + calc_run_time(), 'numberOfBoots': number_of_boots}
    headers = {"Authorization": "Bearer " + token}
    return body, headers


def wait_for_connectivity(old_time):
    time.sleep(CONNECTIVITY_SLEEP_TIME)
    while not connected_to_internet():
        time.sleep(CONNECTIVITY_SLEEP_TIME)
        if time.time() - old_time > REBOOT_TIME:
            return False
    return True


def send_request(old_time, body, headers):
    while True:
        try:
            logging.info('trying to send')
            res = requests.post(URL, data=body, headers=headers, timeout=120)
        except Exception as e:
            logging.error(str(e))
            time.sleep(CONNECTIVITY_SLEEP_TIME)
            if time.time() - old_time > REBOOT_TIME:
                return False
        else:
            logging.info('request made')
            return res


def set_startup_time():
    p = subprocess.Popen(['sh', 'wittypi/wittyPi.sh'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    start = STARTUP_TIMES[startup_time]
    stdout, stderr = p.communicate(input="5\n?? " + start + ":00:00\n11\n")
    logging.info("new startup time " + start + " set on witty")
    logging.info(stdout)


def run_reboot():
    logging.info('rebooting')
    global boot_count, startup_time, image_taken_today
    boot_count = boot_count + 1
    run_time += run_time + calc_run_time()
    if boot_count == FAIL_REBOOT_ATTEMPTS:
        startup_time == startup_time + 1
        if startup_time == len(STARTUP_TIMES):
            startup_time = STARTUP_TIMES[0]
            image_taken_today = False
        boot_count = 0
        set_startup_time()
        write_trap_boot_data()
        system("shutdown now -h")
    else:
        write_trap_boot_data()
        system('reboot')


def calc_run_time():
    now = time.time()
    return (now - start_time) / 60


def main():
    read_trap_boot_data()
    logger_format = '%(asctime)s.%(msecs)03d %(levelname)s : %(message)s'
    logging.basicConfig(filename="trap.log", level=logging.DEBUG, datefmt='%d-%m-%Y %H:%M:%S', format=logger_format)
    try:
        if not image_taken_today:
            take_pic()
        reboot = send_pic()
        if reboot:
            run_reboot()
    except Exception as e:
        logging.error(str(e))

    # in case everything works
    global startup_time, image_taken_today, boot_count, run_time
    if startup_time != 0:
        startup_time == 0
        image_taken_today = False
        boot_count = 0
    # check for battery change command
    if run_time < 0:
        run_time = 0
    else:
        run_time = run_time + calc_run_time()
    write_trap_boot_data()
    if not should_stay_on:
        time.sleep(SLEEP_BEFORE_SHUTDOWN)
        system("shutdown now -h")


if __name__ == "__main__":
    main()
