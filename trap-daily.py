
import requests
import base64
from datetime import datetime
from os import path
from os import system
from response_actions import change_battery, stay_on, update, send_log, get_trap_status, send_run_time
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
    if path.exists('testMode.db'):
        file = open('testMode.db', "r")
        test_mode = file.read().strip()
        file.close()
        if not test_mode:
            return None
        if test_mode.lower() == "true":
            return True
        elif test_mode.lower() == "false":
            return False
    return None

def get_trap_version():
    if path.exists('release_version.db'):
        file = open('release_version.db', "r")
        version = file.read().strip()
        if version:
            return version
    return "main"

def get_trap_boot_data_config():
    if path.isfile(BOOT_DATA_FILE_PATH):
        with open(BOOT_DATA_FILE_PATH) as file:
            config = json.load(file)
            logging.info('trap config data: ' + str(config))
        return config
    else:
        logging.info("no boot data file")


def update_config_file(config):
    file = open(BOOT_DATA_FILE_PATH, "w")
    json.dump(config, file)
    file.close()


def write_trap_boot_data(boot_count, run_time, startup_time, image_taken_today):
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
        logging.info("Image taken and saved")


def wait_for_connectivity(start_of_run, pre_config):
    time.sleep(CONNECTIVITY_SLEEP_TIME)
    while not connected_to_internet():
        logging.info("Sleeping for: " + str(CONNECTIVITY_SLEEP_TIME))
        time.sleep(CONNECTIVITY_SLEEP_TIME)
        if time.time() - start_of_run > REBOOT_TIME:
            return run_reboot(pre_config)
    logging.info('Connected to internet')
    return True

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

def run_reboot(config, start_of_run):
    logging.info('Run reboot')
    run_time = config["run_time"]
    boot_count = config["boot_count"]
    startup_time = config["startup_time"]
    image_taken_today = config["image_taken_today"]
    run_time += calc_run_time(start_of_run)
    if boot_count == FAIL_REBOOT_ATTEMPTS:
        logging.info("Max reboots reached")
        startup_time += 1
        if startup_time == len(STARTUP_TIMES):
            logging.info("No new startup time for today, setting time for tomorrow")
            startup_time = 1
            image_taken_today = False
            set_startup_time(False, 0)
        boot_count = 0
        write_trap_boot_data(boot_count, run_time, startup_time, image_taken_today)
        system("shutdown now -h")

    else:
        boot_count += 1
        write_trap_boot_data(boot_count, run_time, startup_time, image_taken_today)
        time.sleep(5)
        logging.info("Rebooting")
        system('reboot')

def calc_run_time(start_of_run):
    return round(time.time() - start_of_run, 3) / 60

def configure_logging(logging):
    logger_format = '%(asctime)s.%(msecs)03d %(levelname)s : %(message)s'
    logging.basicConfig(filename="trap.log", level=logging.DEBUG, datefmt='%d-%m-%Y %H:%M:%S', format=logger_format)

def update_trap_data(db, data):
    my_file = open(db, "w")
    logging.info("Writing to :" + db +". with value: " + str(data))
    my_file.write(str(data))
    my_file.close()

def send_image(token, trap_id, test_mode, startup_index, boot_count, config):
    with open('latest.jpg', "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read())
    image_name = datetime.now().strftime("%d-%m-%Y-%H_%M") + ".jpg"
    run_time = get_trap_boot_data("run_time", config)
    logging.info("run time is - : " + str(run_time))
    number_of_boots = startup_index * FAIL_REBOOT_ATTEMPTS + boot_count
    body = {'image': encoded_string, 'trapId': trap_id, 'imageName': image_name, 'testMode': test_mode,
            'runTime': run_time , 'numberOfBoots': number_of_boots}
    headers = {"Authorization": "Bearer " + token}
    logging.info('Attempting to send Image')
    return requests.post(URL, data=body, headers=headers, timeout=120)

def send_detection(token, trap_id, test_mode, start_of_run, start_up_index, boot_count, config):
    send_attempt = True
    logging.info('Attempting to send request')
    while send_attempt:
        try:
            result = send_image(token, trap_id, test_mode, start_up_index, boot_count, config)
        except Exception as e:
            time.sleep(CONNECTIVITY_SLEEP_TIME)
            if time.time() - start_of_run > REBOOT_TIME:
                logging.error(str(e) + " reached max retries. shutting off")
                run_reboot(config, start_of_run)
                return
            logging.error(str(e) + " failed attempt at sending request")
            logging.exception(str(e))
        else:
            if result.status_code == 200:
                data = result.json()
                logging.info('Image sent! response data: ' + str(data))
                send_attempt = False
            else:
                logging.error("Image was not sent - " + result.text)

def update_trap_db_status(trap_status):
    if trap_status.get("test_mode") is not None:
        update_trap_data("testMode.db", trap_status.get("test_mode"))
    if trap_status.get("focus"):
        update_trap_data("trap_focus.db", trap_status.get("focus"))

def validate_trap_base_data(token, serial):
    if not token:
        logging.error("Fatal error no token for pi")
        return False
    if not serial:
        logging.error("Fatal error no serial for pi")
        return False
    if not path.exists(BOOT_DATA_FILE_PATH):
        file = open(BOOT_DATA_FILE_PATH, "w")
        json.dump(
            {'boot_count': 0, 'startup_time': 0,
             'run_time': 0, 'image_taken_today': False}, file)
        file.close()
    return True

def get_trap_base_data():
    return get_token(), get_serial()

def get_trap_boot_data(data, config):
        boot_data = config[data]
        logging.info('Trap boot data for: ' + str(data) + '. is: ' + str(boot_data))
        return boot_data

def send_log_data(token, serial, weekday, trap_status, delete_log = False):
    if trap_status["send_log"] or weekday == 6:
        send_log(token, serial, delete_log)

def update_trap_version(trap_status):
    version_update = trap_status.get("version_update")
    logging.info('Should update version - ' + str(version_update))
    if version_update:
        requested_version = trap_status.get('requested_version')
        if requested_version:
            if update(requested_version) == 0:
                update_trap_data('release_version.db', requested_version)
                logging.info("Trap updated to version - " + str(requested_version))
            else:
                logging.error('Failed to update version: ' + requested_version)
        else:
            update()
            update_trap_data('release_version.db', 'main')
            logging.info("Trap updated to default version 'main'")

def update_trap_run_time(start_of_run, config,token=None, serial=None, should_send_runtime=False):
    total_current_run_time = calc_run_time(start_of_run)
    previous_run_time = config["run_time"]
    over_all_run_time = round(total_current_run_time, 3) + previous_run_time
    config["run_time"] = over_all_run_time
    update_config_file(config)
    logging.info("Sending run time of total - " + str(round(over_all_run_time, 3)) + " minutes")
    if should_send_runtime:
        send_run_time(token, serial, round(over_all_run_time, 3))

def main():
    start_of_run = time.time()
    configure_logging(logging)
    logging.info("========================STARTING NEW WAKEUP LOG========================")
    try:
        token, serial = get_trap_base_data()
        logging.info('Trap-id:' + str(serial))
        logging.info('Trap version is: ' + str(get_trap_version()))
        if not validate_trap_base_data(token, serial):
            return
        pre_config = get_trap_boot_data_config()
        wait_for_connectivity(start_of_run, pre_config)
        trap_status = get_trap_status(token, serial)
        logging.info("Trap status Response - " + str(trap_status))
        update_trap_db_status(trap_status)
        config = get_trap_boot_data_config()
        if trap_status.get("change_battery"):
            config["run_time"] = 0
            update_config_file(config)
        test_mode = get_test_mode()
        if test_mode is None:
            return
        if not get_trap_boot_data("image_taken_today", config):
            take_pic()
            config['image_taken_today'] = True
            update_config_file(config)
        start_up_index = get_trap_boot_data("startup_time", config)
        logging.info("Startup index is: " + str(start_up_index))
        boot_count = get_trap_boot_data("boot_count", config)
        if boot_count == 0:
            set_startup_time(test_mode, start_up_index)
        logging.info("Mode is : " + ("production" if not test_mode else "test"))
        send_detection(token, serial, test_mode, start_of_run, start_up_index, boot_count, config)
        config['image_taken_today'] = False
        update_config_file(config)
        should_stay_on = trap_status["stay_on"]
        while should_stay_on and (time.time() - start_of_run) < STAY_ON_SLEEP:
            logging.info("-----------TRAP IS STAYING ON CHECKING DATA AND PERFORMING TASKS-----------")
            # logging.info("now - " + str(time.time()) + " start of run - " + str(start_of_run) + " stay on for - " + str(
            #     STAY_ON_SLEEP) + "start an now diff is = " + str(time.time() - start_of_run))
            time.sleep(CONNECTIVITY_SLEEP_TIME)
            changed_trap_status = get_trap_status(token, serial)
            logging.info("New changed status: " + str(changed_trap_status))
            update_trap_db_status(changed_trap_status)
            is_test_mode = changed_trap_status.get('test_mode')
            if changed_trap_status.get("take_pic"):
                take_pic()
                send_detection(token, serial, is_test_mode, start_of_run, start_up_index, boot_count, config)
            send_log_data(token, serial, datetime.today().weekday(), changed_trap_status, False)
            if changed_trap_status.get("turn_off"):
                logging.info("Turn off request - shutting down trap.")
                should_stay_on = False
        update_trap_version(trap_status)
        update_trap_run_time(start_of_run, config, token, serial, True)
        send_log_data(token, serial, datetime.today().weekday(), trap_status, False)
    except Exception as e:
        config = get_trap_boot_data_config()
        if config:
            update_trap_run_time(start_of_run, config, False)
        logging.exception(str(e))
    time.sleep(SLEEP_BEFORE_SHUTDOWN)
    system("shutdown now -h")

if __name__ == "__main__":
    main()
