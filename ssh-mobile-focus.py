from ctypes import CDLL
from picamera import PiCamera
import time
import sys

def take_pic_with_focus(focus_value):
    try:
        camera_res = (3280, 2464)
        arducam_vcm = CDLL('./RaspberryPi/Motorized_Focus_Camera/python/lib/libarducam_vcm.so')  # Motorized 8mp line
        arducam_vcm.vcm_init()
        camera = PiCamera()
        camera.resolution = (camera_res[0], camera_res[1])
        arducam_vcm.vcm_write(focus_value)  # Motorized 8mp line
        time.sleep(2)  # Motorized 8mp line
        camera.capture("test.jpg")
        print("image_taken")
    except Exception as e:
        print(e)


take_pic_with_focus(sys.argv[1])