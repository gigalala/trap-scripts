
import requests
import base64
from datetime import datetime
from os import path
from os import system
import os
from response_actions import change_battery, stay_on, update, send_log, get_trap_status, send_run_time
from Autofocus import get_focus
from picamera import PiCamera
from ctypes import * # Motorized 8mp line
import time
import logging
import subprocess
import json
# import trap

FOCUS_VAL = 202 # Motorized 8mp line

FAIL_REBOOT_ATTEMPTS = 1
REBOOT_TIME = 120  # 2 minutes
CONNECTIVITY_SLEEP_TIME = 10  # 10 sec
SLEEP_BEFORE_SHUTDOWN = 5  # 5 seconds
STAY_ON_SLEEP = 600  # 10 minutes
URL = 'https://us-central1-cameraapp-49969.cloudfunctions.net/serverless/trap_image'
BOOT_DATA_FILE_PATH = "trap.data"
STARTUP_TIMES = ['11:00:00', '13:00:00', '15:00:00', '17:00:00', '19:00:00', '21:00:00', '23:00:00']

EVERY_2_HOUR_SCRIPT = 'BEGIN  2016-08-05 00:00:00 \nEND    2025-07-31 23:59:59 \nON    M1 WAIT\nOFF   H1 M59'
EVERY_DAY_SCRIPT = 'BEGIN 2015-08-01 11:00:00 \nEND   2025-07-31 23:59:59 \nON    M1 WAIT \nOFF   H23 M59'


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


def get_focus_value(should_focus=False):
    focus = FOCUS_VAL
    if should_focus:
        focus = get_focus()
        logging.info("using auto-focus. value for auto is: " + str(focus))
        update_trap_data("trap_focus.db", focus)
        return focus
    if path.exists('trap_focus.db'):
        file = open('trap_focus.db', "r")
        focus = file.read().strip()
        file.close()
        if not focus:
            return None
    return int(focus)


def get_token():
    token_trap = None
    if path.exists('token.db'):
        file = open('token.db', "r")
        token_trap = file.read().strip()
        file.close()
        if not token_trap:
            return None
    return token_trap


def get_witty_type():
    if path.exists('new_witty.db'):
        file = open('new_witty.db', "r")
        is_new_witty = file.read().strip()
        file.close()
        if not is_new_witty:
            return False
        if is_new_witty.lower() == "true":
            return True
        elif is_new_witty.lower() == "false":
            return False
    return False


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


def take_pic(trap_status):
    is_five_mega = get_camera_type()
    focus_value = get_focus_value(trap_status.get("auto_focus"))
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
        now = time.time()
        if now - start_of_run > REBOOT_TIME:
            logging.error('Didnt connect to the internet, will reboot at end of run')
            return False
            # run_reboot(pre_config, start_of_run)
    logging.info('Connected to internet')
    return True


def set_and_run_new_witty_startup(startup_script):
    logging.info('Attmpting to set turn on with \n' + str(startup_script))
    with open('wittypi/schedule.wpi', 'w') as file:
        file.write(startup_script)
    os.chdir("wittypi")
    p = subprocess.Popen(['bash', 'runScript.sh'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    stdout, stderr = p.communicate()
    os.chdir("/home/pi")
    logging.info(stdout)
    # for line in stdout.splitlines()[len(stdout.splitlines()) / 2:]:
    #     if line.startswith(">>>"):
    #         logging.info(line[4:])
    #     elif line.strip().startswith("4.") or line.strip().startswith("5."):
    #         logging.info(line[14:])


def set_startup_time(is_test, start_index):
    if is_test:
        return
    is_new_witty = get_witty_type()
    if is_new_witty:
        if start_index == 0:
            set_and_run_new_witty_startup(EVERY_DAY_SCRIPT)
        else:
            set_and_run_new_witty_startup(EVERY_2_HOUR_SCRIPT)
    else:
        p = subprocess.Popen(['sh', 'wittypi/wittyPi.sh'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        start = STARTUP_TIMES[start_index]
        command = "5\n?? " + start + "\n11\n"
        stdout, stderr = p.communicate(input=command)
        # for line in stdout.splitlines()[len(stdout.splitlines()) / 2:]:
        #     if line.startswith(">>>"):
        #         logging.info(line[4:])
        #     elif line.strip().startswith("4.") or line.strip().startswith("5."):
        #         logging.info(line[14:])
        logging.info("Next startup time set to: " + str(start))


def set_dummy_load(remove_dummy_load):
    if remove_dummy_load is None:
        logging.warn("Should update dummy load, but no dummy load in request")
        return
    dummy_load = 0 if remove_dummy_load else 25
    logging.info("Attempting to update dummy load to: " + str(dummy_load))
    try:
        p = subprocess.Popen(['sh', 'wittypi/wittyPi.sh'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        command = "9\n 5\n" + str(dummy_load) + "\n11"
        stdout, stderr = p.communicate(input=command)
    except Exception as e:
        logging.error(str(e) + " failed to update dummy load")
        logging.exception(str(e))
    else:
        logging.info("updated dummy load to :" + str(dummy_load))


def run_reboot(config, start_of_run):
    logging.info('Run reboot')
    run_time = config["run_time"]
    boot_count = config["boot_count"]
    startup_time = config["startup_time"]
    image_taken_today = config["image_taken_today"]
    run_time += calc_run_time(start_of_run)
    if boot_count >= FAIL_REBOOT_ATTEMPTS:
        logging.info("Max reboots reached")
        set_startup_time(False, startup_time)
        startup_time += 1
        if startup_time == len(STARTUP_TIMES):
            logging.info("No new startup time for today, setting time for tomorrow")
            startup_time = 1
            image_taken_today = False
            set_startup_time(False, 0)
        boot_count = 0
        write_trap_boot_data(boot_count, run_time, startup_time, image_taken_today)
        logging.info("Shutting Down - next startup time is " + str(STARTUP_TIMES[startup_time]))
        system("shutdown now -h")
        exit()

    else:
        boot_count += 1
        write_trap_boot_data(boot_count, run_time, startup_time, image_taken_today)
        time.sleep(5)
        logging.info("Rebooting")
        system('reboot')
        exit()


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
                # run_reboot(config, start_of_run)
                return False
            logging.error(str(e) + " failed attempt at sending request")
            logging.exception(str(e))
        else:
            if result.status_code == 200:
                data = result.json()
                logging.info('Image sent! response data: ' + str(data))
                send_attempt = False
                return True
            else:
                logging.error("Image was not sent - " + result.text)
                return False


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


def safe_send_log_data(token, serial, delete_log = False):
    try:
        result = send_log(token, serial, delete_log)
    except Exception as e:
        logging.error('Failed to send log - exception thrown')
        logging.exception(str(e))
    else:
        if result == 200:
            logging.info("Sent log sent successfully!")
        else:
            logging.error("Failed to send log - error returned" + str(result))


def send_log_data(token, serial, weekday, send_log_request, delete_log = False):
    if send_log_request or weekday == 6:
        safe_send_log_data(token, serial, delete_log)


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


def safe_send_runtime(token, serial, overall_run_time):
    try:
      result = send_run_time(token, serial, round(overall_run_time, 3))
    except Exception as e:
        logging.error('failed to get trap status')
        logging.exception(str(e))
    else:
        if result == 200:
            logging.info("sent runtime sent successfully")
        else:
            logging.error("failed to send runtime - error returned" + str(result))


def update_trap_run_time(start_of_run, config, token=None, serial=None, should_send_runtime=False):
    total_current_run_time = calc_run_time(start_of_run)
    previous_run_time = config["run_time"]
    over_all_run_time = round(total_current_run_time, 3) + previous_run_time
    config["run_time"] = over_all_run_time
    update_config_file(config)
    logging.info("Sending run time of total - " + str(round(over_all_run_time, 3)) + " minutes")
    if should_send_runtime:
        safe_send_runtime(token, serial, round(over_all_run_time, 3))


def attempt_get_trap_status(token, serial):
    trap_status = {}
    logging.info('Attempting to get trap status')
    try:
        trap_status, status_code = get_trap_status(token, serial)
    except Exception as e:
        logging.error('failed to get trap status')
        logging.exception(str(e))
    else:
        if status_code == 200:
            logging.info("Trap status Response - " + str(trap_status))
        else:
            logging.error("Trap status returned error - " + str(status_code))
    return trap_status


def set_emergency_shutdown():
    logging.info('Setting pre-run emergency shutdown to - ??:15')
    p = subprocess.Popen(['sh', 'wittypi/wittyPi.sh'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    command = "5\n?? ??:15 \n11\n"
    p.communicate(input=command)


def set_pre_run_data(pre_config):
    # is_new_witty = get_witty_type()
    # if not is_new_witty:
    pre_run_test_mode = get_test_mode()
    start_up_index = get_trap_boot_data("startup_time", pre_config)
    logging.info('Setting pre-run data for trap with start_up_time ' + str(STARTUP_TIMES[start_up_index]))
    set_startup_time(pre_run_test_mode, start_up_index)
    if not get_witty_type():
        set_emergency_shutdown()


def update_time_by_network():
    is_new_witty = get_witty_type()
    logging.info("New witty pi, updating RTC clock by network")
    if is_new_witty:
        p = subprocess.Popen(['sh', 'wittypi/wittyPi.sh'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        command = "3\n " + "\n13\n"
        stdout, stderr = p.communicate(input=command)
        for line in stdout.splitlines()[len(stdout.splitlines()) / 2:]:
            if line.startswith(">>>"):
                logging.info(line[4:])
            elif line.strip().startswith("4.") or line.strip().startswith("5."):
                logging.info(line[14:])


def main():
    start_of_run = time.time()
    configure_logging(logging)
    internet_connection = False
    token, serial = None, None
    detection_sent = False
    config = None
    trap_status = {}
    logging.info("========================STARTING NEW WAKEUP LOG========================")
    try:
        token, serial = get_trap_base_data()
        # current_trap = trap(token, serial, start_of_run, FOCUS_VAL, get_trap_version())
        logging.info('TRAP-ID:' + str(serial))
        # logging.info('TRAP-ID: ' + current_trap.get_trap_id())
        logging.info('TRAP-VERSION: ' + str(get_trap_version()))
        # logging.info('TRAP-VERSION: ' + current_trap.get_trap_version())
        if not validate_trap_base_data(token, serial):
            return
        pre_config = get_trap_boot_data_config()
        set_pre_run_data(pre_config)
        internet_connection = wait_for_connectivity(start_of_run, pre_config)
        # current_trap.set_connectivity(internet_connection)
        if internet_connection:
            trap_status = attempt_get_trap_status(token, serial)
            update_time_by_network()
        # init_trap_from_returned_status(current_trap, trap_status)
            if trap_status.get("update_dummy_load"):
                set_dummy_load(trap_status.get("remove_dummy_load"))
            update_trap_db_status(trap_status)
        config = get_trap_boot_data_config()
        if trap_status.get("change_battery"):
            config["run_time"] = 0
            update_config_file(config)
        test_mode = get_test_mode()
        if test_mode is None:
            return
        logging.info("Mode is : " + ("production" if not test_mode else "test"))
        if not get_trap_boot_data("image_taken_today", config):
            take_pic(trap_status)
            config['image_taken_today'] = True
            update_config_file(config)
        if not internet_connection:
            run_reboot(config, start_of_run)

        start_up_index = get_trap_boot_data("startup_time", config)
        # logging.info("Startup index is: " + str(start_up_index))
        boot_count = get_trap_boot_data("boot_count", config)
        if boot_count == 0:
            set_startup_time(test_mode, start_up_index)
        if internet_connection:
            detection_sent = send_detection(token, serial, test_mode, start_of_run, start_up_index, boot_count, config)

        if not detection_sent:
            run_reboot(config, start_of_run)

        config['image_taken_today'] = False
        config['startup_time'] = 1
        set_startup_time(test_mode, 0)
        update_config_file(config)
        should_stay_on = trap_status.get("stay_on")
        while should_stay_on and (time.time() - start_of_run) < STAY_ON_SLEEP:
            logging.info("-----------TRAP IS STAYING ON CHECKING DATA AND PERFORMING TASKS-----------")
            time.sleep(CONNECTIVITY_SLEEP_TIME)
            changed_trap_status = attempt_get_trap_status(token, serial)
            logging.info("New changed status: " + str(changed_trap_status))
            update_trap_db_status(changed_trap_status)
            is_test_mode = changed_trap_status.get('test_mode')
            if changed_trap_status.get("take_pic"):
                take_pic(changed_trap_status)
                send_detection(token, serial, is_test_mode, start_of_run, start_up_index, boot_count, config)
            send_log_data(token, serial, datetime.today().weekday(), changed_trap_status.get("send_log"), False)
            if changed_trap_status.get("turn_off"):
                logging.info("Turn off request - shutting down trap.")
                should_stay_on = False
        if internet_connection:
            update_trap_version(trap_status)
            update_trap_run_time(start_of_run, config, token, serial, True)
            send_log_data(token, serial, datetime.today().weekday(), trap_status.get("send_log"), False)
    except Exception as e:
        try:
            if config:
                update_trap_run_time(start_of_run, config, False)
            logging.exception(str(e))
            if internet_connection and token and serial:
                send_log_data(token, serial, datetime.today().weekday(), True, False)
        except Exception as e:
            logging.exception(str(e))
    time.sleep(SLEEP_BEFORE_SHUTDOWN)
#    system("shutdown now -h")

if __name__ == "__main__":
    main()
