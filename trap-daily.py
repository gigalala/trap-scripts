import smbus
import requests
import base64
from datetime import datetime
from os import path
from os import system
import os
from response_actions import change_battery, stay_on, update, send_log, get_trap_status, send_run_time
import time
import logging
import subprocess
import json

# ============================================================
# IMX708 (12MP, Camera Module 3) / libcamera - Python 3, Bookworm.
# Derived from the new-witty-voltic-daily-10 branch; only the
# camera layer changed: picamera + Arducam VCM -> rpicam-still.
# The IMX708 has built-in autofocus, so Autofocus.py/camera.db
# are gone. Optional SHT30 temp/humidity sensor is read over I2C
# and logged (no server upload yet).
# ============================================================

CAMERA_CMD = 'rpicam-still'
CAMERA_RES = (4608, 2592)  # IMX708 full resolution
CAMERA_WAIT_MS = 5000      # preview time, lets AE/AWB/AF converge
CAMERA_TIMEOUT = 90        # seconds before giving up on the capture process
# Lens position is in dioptres (0 = infinity, ~2 = 50cm, ~10 = 10cm).
# Legacy VCM focus values (10-1000) stored in trap_focus.db are out of
# range and fall back to autofocus.
MAX_LENS_POSITION = 32

SHT30_I2C_ADDR = 0x44  # FS400-SHT30 default address (0x45 if ADDR pin high)

FAIL_REBOOT_ATTEMPTS = 1
REBOOT_TIME = 120  # 2 minutes
CONNECTIVITY_SLEEP_TIME = 10  # 10 sec
SLEEP_BEFORE_SHUTDOWN = 5  # 5 seconds
STAY_ON_SLEEP = 600  # 10 minutes
URL = 'https://us-central1-cameraapp-49969.cloudfunctions.net/serverless/trap_image'
BOOT_DATA_FILE_PATH = "trap.data"
STARTUP_TIMES = ['11:00:00', '13:00:00', '15:00:00', '17:00:00', '19:00:00', '21:00:00', '23:00:00']

EVERY_2_HOUR_SCRIPT = 'BEGIN  2016-08-05 00:00:00 \nEND    2030-07-31 23:59:59 \nON    M1 WAIT\nOFF   H1 M59'
EVERY_DAY_SCRIPT = 'BEGIN 2015-08-01 10:00:00 \nEND   2030-07-31 23:59:59 \nON     H23 M59 WAIT\nOFF   M1'


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


def get_lens_position():
    """Manual lens position (dioptres) from trap_focus.db, or None for
    the IMX708's built-in autofocus."""
    if not path.exists('trap_focus.db'):
        return None
    with open('trap_focus.db', 'r') as file:
        raw = file.read().strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        logging.warning("Invalid trap_focus.db value: " + raw)
        return None
    if value < 0 or value > MAX_LENS_POSITION:
        logging.warning("trap_focus.db value " + str(value) +
                        " out of lens-position range (legacy VCM value?), using autofocus")
        return None
    return value


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
    return "imx708-voltic-daily"


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


def read_sht30():
    """Single-shot SHT30 measurement. Returns (temp_c, humidity) or None.
    The sensor is optional - any error is logged and swallowed."""
    bus = None
    try:
        bus = smbus.SMBus(1)
        # Single-shot, high repeatability, clock stretching disabled (0x24 0x00)
        bus.write_i2c_block_data(SHT30_I2C_ADDR, 0x24, [0x00])
        time.sleep(0.05)
        data = bus.read_i2c_block_data(SHT30_I2C_ADDR, 0x00, 6)
        raw_temp = (data[0] << 8) | data[1]
        raw_hum = (data[3] << 8) | data[4]
        temp_c = -45 + (175 * raw_temp / 65535.0)
        humidity = 100 * raw_hum / 65535.0
        return round(temp_c, 2), round(humidity, 2)
    except Exception as e:
        logging.info("SHT30 sensor not available (" + str(e) + ")")
        return None
    finally:
        if bus:
            bus.close()


def log_environment():
    reading = read_sht30()
    if reading:
        logging.info("SHT30 reading - temperature=" + str(reading[0]) +
                     "C humidity=" + str(reading[1]) + "%")


def take_pic(trap_status):
    lens_position = None if trap_status.get("auto_focus") else get_lens_position()
    cmd = [CAMERA_CMD, '-n', '-t', str(CAMERA_WAIT_MS),
           '--width', str(CAMERA_RES[0]), '--height', str(CAMERA_RES[1]),
           '-o', 'latest.jpg']
    if lens_position is None:
        cmd += ['--autofocus-on-capture']
        logging.info("Starting 12MP camera capture with autofocus")
    else:
        cmd += ['--autofocus-mode', 'manual', '--lens-position', str(lens_position)]
        logging.info("Starting 12MP camera capture with lens position: " + str(lens_position))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=CAMERA_TIMEOUT)
        if result.returncode != 0:
            logging.error('Failed to take a picture: ' + str(result.stderr))
        else:
            logging.info("Image taken and saved")
    except Exception:
        logging.exception('Failed to take a picture')


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
    logging.info('Attmpting to set witty script \n')
    with open('wittypi/schedule.wpi', 'w') as file:
        file.write(startup_script)
    os.chdir("wittypi")
    p = subprocess.Popen(['bash', 'runScript.sh'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    stdout, stderr = p.communicate()
    os.chdir("/home/pi")
    logging.info(stdout)


def set_startup_time(is_test, start_index):
    # if is_test:
    #     return
    is_new_witty = get_witty_type()
    if is_new_witty:
        if start_index == 0:
            set_and_run_new_witty_startup(EVERY_DAY_SCRIPT)
        else:
            set_and_run_new_witty_startup(EVERY_2_HOUR_SCRIPT)
    else:
        p = subprocess.Popen(['sh', 'wittypi/wittyPi.sh'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        start = STARTUP_TIMES[start_index]
        command = "5\n?? " + start + "\n11\n"
        stdout, stderr = p.communicate(input=command)
        logging.info("Next startup time set to: " + str(start))


def set_dummy_load(remove_dummy_load):
    if remove_dummy_load is None:
        logging.warning("Should update dummy load, but no dummy load in request")
        return
    dummy_load = 0 if remove_dummy_load else 25
    logging.info("Attempting to update dummy load to: " + str(dummy_load))
    try:
        p = subprocess.Popen(['sh', 'wittypi/wittyPi.sh'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
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
        shutdown_witty_pi()
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
    logging.info("Writing to :" + db + ". with value: " + str(data))
    my_file.write(str(data))
    my_file.close()


def send_image(token, trap_id, test_mode, startup_index, boot_count, config):
    with open('latest.jpg', "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    image_name = datetime.now().strftime("%d-%m-%Y-%H_%M") + ".jpg"
    run_time = get_trap_boot_data("run_time", config)
    number_of_boots = startup_index * FAIL_REBOOT_ATTEMPTS + boot_count
    body = {'image': encoded_string, 'trapId': trap_id, 'imageName': image_name, 'testMode': test_mode,
            'runTime': run_time, 'numberOfBoots': number_of_boots}
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
        # NOTE: focus is now a libcamera lens position in dioptres
        # (0 = infinity, ~2 = 50cm, ~10 = 10cm). Legacy VCM values
        # (10-1000) are ignored by get_lens_position() -> autofocus.
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
            update_trap_data('release_version.db', 'imx708-voltic-daily')
            logging.info("Trap updated to default version 'imx708-voltic-daily'")


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
    p = subprocess.Popen(['sh', 'wittypi/wittyPi.sh'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    command = "5\n?? ??:15 \n11\n"
    p.communicate(input=command)


def set_pre_run_data(pre_config):
    pre_run_test_mode = get_test_mode()
    start_up_index = get_trap_boot_data("startup_time", pre_config)
    logging.info('Setting pre-run data for trap with start_up_time ' + str(STARTUP_TIMES[start_up_index]))
    set_startup_time(pre_run_test_mode, start_up_index)
    if not get_witty_type():
        set_emergency_shutdown()


def update_time_by_network():
    is_new_witty = get_witty_type()
    if is_new_witty:
        logging.info("New witty pi, updating RTC clock by network")
        p = subprocess.Popen(['sh', 'wittypi/wittyPi.sh'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        command = "3\n " + "\n13\n"
        stdout, stderr = p.communicate(input=command)
        lines = stdout.splitlines()
        for line in lines[len(lines) // 2:]:
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
        logging.info('TRAP-ID:' + str(serial))
        logging.info('TRAP-VERSION: ' + str(get_trap_version()))
        log_environment()
        if not validate_trap_base_data(token, serial):
            return
        pre_config = get_trap_boot_data_config()
        set_pre_run_data(pre_config)
        internet_connection = wait_for_connectivity(start_of_run, pre_config)
        if internet_connection:
            update_time_by_network()
            trap_status = attempt_get_trap_status(token, serial)
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
        config['boot_count'] = 0
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
    finally:
        time.sleep(SLEEP_BEFORE_SHUTDOWN)
        shutdown_witty_pi()

def shutdown_witty_pi():
    """Set shutdown alarm to current RTC time (triggers immediately)"""
    bus = smbus.SMBus(1)

    try:
        # Copy current RTC time (registers 58-61) to ALARM2 (registers 32-35)
        for i in range(4):
            current_value = bus.read_byte_data(0x08, 58 + i)
            bus.write_byte_data(0x08, 32 + i, current_value)

        print("Witty Pi shutdown triggered!")
    finally:
        bus.close()


if __name__ == "__main__":
    main()
