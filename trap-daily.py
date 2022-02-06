# VERSION = 2.1
import requests
import base64
from datetime import datetime
from os import path
from os import system
from response_actions import change_battery, stay_on, update, send_log, get_trap_status
from picamera import PiCamera
from ctypes import * # Motorized 8mp line
import time
import logging
import subprocess
import json

FOCUS_VAL = 202 # Motorized 8mp line

FAIL_REBOOT_ATTEMPTS = 2
REBOOT_TIME = 300  # 5 minutes
CONNECTIVITY_SLEEP_TIME = 10  # 10 sec
SLEEP_BEFORE_SHUTDOWN = 5  # 5 seconds
STAY_ON_SLEEP = 600  # 10 minutes
URL = 'https://us-central1-cameraapp-49969.cloudfunctions.net/serverless/trap_image'
BOOT_DATA_FILE_PATH = "trap.data"
STARTUP_TIMES = ['11:00:00', '13:00:00', '15:00:00', '17:00:00', '19:00:00', '21:00:00', '23:00:00']

# is_test = False

# Boot data
# boot_count = None
# startup_time = None
# run_time = None
# image_taken_today = None
# should_stay_on = False
# start_time = time.time()

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
        logging.error("Couldn't return trap's serial")
        return None
    return cpu_serial

def get_camera_type():
    camera_five = None
    if path.exists('camera.db'):
        file = open('camera.db', "r")
        camera_five = file.read().strip()
        file.close()
        if not camera_five:
            return None
    return camera_five == "true"

def get_focus_value():
    focus = FOCUS_VAL
    if path.exists('trap_focus.db'):
        file = open('trap_focus.db', "r")
        focus = file.read().strip()
        file.close()
        if not focus:
            return None
    return focus

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
    # global is_test
    if path.exists('testMode.db'):
        file = open('testMode.db', "r")
        test_mode = file.read().strip()
        file.close()
        if not test_mode:
            return None
        if test_mode == "true":
            # is_test = True
            return True
        elif test_mode == "false":
            # is_test = False
            return False
    return None

def get_trap_boot_data_config():
    if path.isfile(BOOT_DATA_FILE_PATH):
        with open(BOOT_DATA_FILE_PATH) as file:
            config = json.load(file)
        return config
    else:
        logging.info("no boot data file")

# def read_trap_boot_data():
#     global boot_count, startup_time, run_time, image_taken_today
#     if path.isfile(BOOT_DATA_FILE_PATH):
#         with open(BOOT_DATA_FILE_PATH) as file:
#             config = json.load(file)
#         logging.info('trap data: ' + str(config))
#         boot_count = config['boot_count']
#         startup_time = config['startup_time']
#         run_time = config['run_time']
#         image_taken_today = config['image_taken_today']
#         file.close()
#     else:
#         logging.info("no boot data file")
#         boot_count = 0
#         startup_time = 1
#         run_time = 0
#         image_taken_today = False

def write_trap_boot_data(boot_count, startup_time, image_taken_today):
    logging.info("Boot count is " + str(boot_count))
    logging.info("Startup time is " + str(startup_time))
    file = open(BOOT_DATA_FILE_PATH, "w")
    json.dump(
        {'boot_count': boot_count, 'startup_time': startup_time,
         'run_time': run_time, 'image_taken_today': image_taken_today}, file)
    file.close()

def take_pic():
    is_five_mega = get_camera_type()
    focus_value = get_focus_value()
    logging.info("Starting camera process with - " + (
        "5 mega pixel." if is_five_mega else "8 mega pixel.") + " with focus value:" + str(focus_value))
    camera_res = (2592, 1944)
    if not is_five_mega:
        camera_res = (3280, 2464)  # Motorized 8mp line
        arducam_vcm = CDLL('./RaspberryPi/Motorized_Focus_Camera/python/lib/libarducam_vcm.so')  # Motorized 8mp line
        arducam_vcm.vcm_init()  # Motorized 8mp line
    camera = PiCamera()
    try:
        camera.resolution = (camera_res[0], camera_res[1])
        if not is_five_mega:
            arducam_vcm.vcm_write(focus_value)  # Motorized 8mp line
            time.sleep(2)  # Motorized 8mp line
        camera.capture("latest.jpg")
    except Exception:
        camera.close()
        logging.exception('Failed to take a picture')
    else:
        camera.close()
        global image_taken_today
        image_taken_today = True
        logging.info("Image taken and saved")


# def send_pic():
#     body, headers = get_body_and_headers()
#     if not body or not headers:
#         return
#     old_time = time.time()
#     result = wait_for_connectivity(old_time)
#     if not result:
#         return True
#     logging.info('Connected to internet')
#     result = send_request(old_time, body, headers)
#     if not result:
#         return True
#
#     if result.status_code == 200:
#         data = result.json()
#         logging.info('Image sent! response data: ' + str(data))
#         for action in data:
#             check_response_for_actions(action)
#     else:
#         logging.error("Image was not sent - " + result.text)

# def check_response_for_actions(data):
#     # global should_stay_on, run_time
#     try:
#         if data['action'] == "none":
#             logging.info("No response action was received")
#         # elif data['action'] == "stayOn":
#         #     logging.info("Stay on response action was received")
#         #     should_stay_on = stay_on()
#         elif data['action'] == "changeBattery":
#             logging.info("Change battery response action was received")
#             run_time = change_battery()
#         elif data['action'] == "versionUpdate":
#             logging.info("Update response action was received")
#             if 'value' in data:
#                 update(data['value'])
#             else:
#                 update()
#         # elif data['action'] == 'log_update':
#         #     logging.info("Log response action was received")
#         #     send_log(get_token(), get_serial())
#     except Exception as e:
#         logging.exception(str(e))

#
# def get_body_and_headers():
#     trap_id = get_serial()
#     if not trap_id:
#         logging.error("Fatal error no serial for pi")
#         return
#     logging.info('Trap serial id:' + str(trap_id))
#     token = get_token()
#     if not token:
#         logging.error("Fatal error no token for pi")
#         return
#     test_mode = get_test_mode()
#     if test_mode is None:
#         logging.error("Trap is off, no test or production set")
#         return
#     logging.info("Mode is : " + ("production" if not test_mode else "test"))
#     with open('latest.jpg', "rb") as image_file:
#         encoded_string = base64.b64encode(image_file.read())
#     image_name = datetime.now().strftime("%d-%m-%Y-%H_%M") + ".jpg"
#     number_of_boots = startup_time * FAIL_REBOOT_ATTEMPTS + boot_count
#     body = {'image': encoded_string, 'trapId': trap_id, 'imageName': image_name, 'testMode': test_mode,
#             'runTime': run_time + calc_run_time(), 'numberOfBoots': number_of_boots}
#     headers = {"Authorization": "Bearer " + token}
#     return body, headers

def wait_for_connectivity(start_of_run):
    time.sleep(CONNECTIVITY_SLEEP_TIME)
    while not connected_to_internet():
        logging.info("Sleeping for: " + CONNECTIVITY_SLEEP_TIME)
        time.sleep(CONNECTIVITY_SLEEP_TIME)
        if time.time() - start_of_run > REBOOT_TIME:
            return run_reboot()
    logging.info('Connected to internet')
    return True

def send_request(old_time, body, headers):
    while True:
        try:
            logging.info('Attempting to send request')
            res = requests.post(URL, data=body, headers=headers, timeout=120)
        except Exception as e:
            time.sleep(CONNECTIVITY_SLEEP_TIME)
            if time.time() - old_time > REBOOT_TIME:
                logging.error(str(e) + " reached max retries. shutting off")
                return False
            logging.error(str(e) + " failed attempt at sending request")
        else:
            return res

def set_startup_time(is_test, start_index):
    if is_test:
        return
    p = subprocess.Popen(['sh', 'wittypi/wittyPi.sh'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    start = STARTUP_TIMES[start_index]
    command = "5\n?? " + start + "\n11\n"
    stdout, stderr = p.communicate(input=command)
    for line in stdout.splitlines()[len(stdout.splitlines()) / 2:]:
        if line.startswith(">>>"):
            logging.info(line[4:])
        elif line.strip().startswith("4.") or line.strip().startswith("5."):
            logging.info(line[14:])
    logging.info("Next startup time set to: " + str(start))

def run_reboot():
    logging.info('Run reboot')
    # global boot_count, startup_time, image_taken_today, run_time
    run_time += calc_run_time()
    if boot_count == FAIL_REBOOT_ATTEMPTS:
        logging.info("Max reboots reached")
        startup_time += 1
        if startup_time == len(STARTUP_TIMES):
            logging.info("No new startup time for today, setting time for tomorrow")
            startup_time = 1
            image_taken_today = False
            set_startup_time(0)
        boot_count = 0
        write_trap_boot_data()
        system("shutdown now -h")

    else:
        boot_count += 1
        write_trap_boot_data()
        time.sleep(5)
        logging.info("Rebooting")
        system('reboot')

def calc_run_time():
    now = time.time()
    return (now - start_time) / 60


def configure_logging(logging):
    logger_format = '%(asctime)s.%(msecs)03d %(levelname)s : %(message)s'
    logging.basicConfig(filename="trap.log", level=logging.DEBUG, datefmt='%d-%m-%Y %H:%M:%S', format=logger_format)

def update_trap_data(db, data):
    my_file = open(db, "w")
    logging.info("writing to :" + db +". with value: " + data)
    my_file.write(data)
    my_file.close()

def send_image(token, trap_id, test_mode, startup_time):
    with open('latest.jpg', "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read())
    image_name = datetime.now().strftime("%d-%m-%Y-%H_%M") + ".jpg"
    number_of_boots = startup_time * FAIL_REBOOT_ATTEMPTS + boot_count
    body = {'image': encoded_string, 'trapId': trap_id, 'imageName': image_name, 'testMode': test_mode,
            'runTime': run_time + calc_run_time(), 'numberOfBoots': number_of_boots}
    headers = {"Authorization": "Bearer " + token}
    logging.info('Attempting to send request')
    return requests.post(URL, data=body, headers=headers, timeout=120)

def send_detection(token, trap_id, test_mode, start_of_run, start_up_time):
    send_attempt = True
    while send_attempt:
        try:
            result = send_image(token, trap_id, test_mode, start_up_time)
        except Exception as e:
            time.sleep(CONNECTIVITY_SLEEP_TIME)
            if time.time() - start_of_run > REBOOT_TIME:
                logging.error(str(e) + " reached max retries. shutting off")
                run_reboot()
                return
            logging.error(str(e) + " failed attempt at sending request")
            logging.exception(str(e))
        else:
            if result.status_code == 200:
                data = result.json()
                logging.info('Image sent! response data: ' + str(data))
                # for action in data:
                #     check_response_for_actions(action)
                send_attempt = False
            else:
                logging.error("Image was not sent - " + result.text)


def update_trap_db_status(trap_status):
    if trap_status["dev_mode"]:
        update_trap_data("testMode.db", trap_status["dev_mode"])
    if trap_status["focus"]:
        update_trap_data("trap_focus.db", trap_status["focus"])


def validate_trap_base_data(token, serial):
    if not token:
        logging.error("Fatal error no token for pi")
        return False
    if not serial:
        logging.error("Fatal error no serial for pi")
        return False
    return True

def get_trap_base_data():
    return get_token(), get_serial()

def get_trap_boot_data(data):
    if path.isfile(BOOT_DATA_FILE_PATH):
        with open(BOOT_DATA_FILE_PATH) as file:
            config = json.load(file)
        logging.info('trap data: ' + str(config))
        boot_data = config[data]
        logging.info('trap boot data for: ' + str(data) + "is: " + str(boot_data))
        return boot_data

def send_log_data(token, serial, weekday, trap_status, delete_log = False):
    if trap_status["send_log"] or weekday == 6:
        logging.info('Sending weekend log')
        send_log(token, serial, delete_log)


def main():
    should_stay_on = False
    start_of_run = time.time()
    configure_logging(logging)
    logging.info("========================STARTING NEW WAKEUP LOG========================")
    try:
        token, serial = get_trap_base_data()
        logging.info('Trap-id:' + str(serial))
        if not validate_trap_base_data(token, serial):
            return
        wait_for_connectivity(start_of_run)
        trap_status = get_trap_status(token, serial)
        update_trap_db_status(trap_status)
        if not get_trap_boot_data("image_taken_today"):
            take_pic()

        test_mode = get_test_mode()
        if test_mode is None:
            return
        start_up_time = get_trap_boot_data("startup_time")
        logging.info("Stratup time is: " + str(start_up_time))
        if get_trap_boot_data("boot_count") == 0:
            start_up_time = get_trap_boot_data("startup_time")
            set_startup_time(test_mode, start_up_time)
        logging.info("Mode is : " + ("production" if not test_mode else "test"))
        send_detection(token, serial, test_mode, start_of_run, start_up_time)
        send_log_data(token, serial, datetime.today().weekday(), delete_log, trap_status)
        should_stay_on = trap_status["stay_on"]
        logging.info(should_stay_on)


    except Exception as e:
        logging.exception(str(e))
#    if should_stay_on:
#        time.sleep(STAY_ON_SLEEP)
#    else:
#        time.sleep(SLEEP_BEFORE_SHUTDOWN)
#    system("shutdown now -h")








#TODO
    # this enables a flag is_test so it doesn't change wake time on test mode
    # trap_status = get_trap_status(get_token(), get_serial())

    # if get_test_mode() is None:
    #     return
    # logging.info("========================STARTING NEW WAKEUP LOG========================")
    # try:
    #     read_trap_boot_data()
    #     # only first boot needs to set next the startup
    #     if boot_count == 0:
    #         set_startup_time(startup_time)
    #     if not image_taken_today:
    #         take_pic()
    #     reboot = send_pic()
    #     if reboot:
    #         run_reboot()
    #         return
    #     # in case everything works
    #     startup_time = 1
    #     image_taken_today = False
    #     boot_count = 0
    #     set_startup_time(0)
    #     # check for battery change command
    #     if run_time < 0:
    #         run_time = 0
    #     else:
    #         run_time += calc_run_time()
    #     write_trap_boot_data()
    #     # run response actions here
    #     if datetime.today().weekday() == 6:
    #         logging.info('Sending and deleting log')
    #         send_log(get_token(), get_serial(), True)
    #     # system('chmod +x RaspberryPi/Motorized_Focus_Camera/enable_i2c_vc.sh')
    #     # 'y' | system('sh RaspberryPi/Motorized_Focus_Camera/enable_i2c_vc.sh')
    # except Exception as e:
    #     logging.exception(str(e))
    #
    # # check for should stay on command
    # if should_stay_on:
    #     time.sleep(STAY_ON_SLEEP)
    # else:
    #     time.sleep(SLEEP_BEFORE_SHUTDOWN)
    # system("shutdown now -h")


if __name__ == "__main__":
    main()
