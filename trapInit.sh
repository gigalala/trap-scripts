#!/bin/bash
# VERSION = imx708-3.0
# Field config tool for IMX708 (12MP) traps on Bookworm.
# Installation is handled by the golden image + installer-imx708.py
# (auto install-candidate on first boot), so there is no "install
# new trap" option here - only mode/token/camera utilities.

show_witty_stats(){
    if [ ! -f /home/pi/wittypi/wittyPi.sh ]; then
        return
    fi
    printf "${red}*************************************************************************\n${nc}"
    echo -e "13\n"  | sudo sh /home/pi/wittypi/wittyPi.sh | while read line; do
        if [[ $line == '>>>'* ]]; then
            subline="${line:3}"
            echo $subline
        elif [[ $line == '4.'* || $line == '5.'* ]]; then
            subline="${line:2}"
            echo $subline
        elif [[ $line == '6.'* ]]; then
            subline="${line:25}"
            echo $subline
        fi
     done
    printf "${red}*************************************************************************\n\n${nc}"
}

set_dummy_load(){
    echo 'Setting dummy load'
    sudo sh wittypi/wittyPi.sh &> /dev/null  <<EOF
    9
    5
    25
    11
EOF
}

test_camera(){
    echo 'Testing 12MP IMX708 camera (rpicam-still)...'
    if rpicam-still -n -t 2000 -o /home/pi/camera-test.jpg; then
        echo 'Camera OK - test image saved to /home/pi/camera-test.jpg'
        return 0
    else
        echo '!!! Camera test FAILED !!!'
        echo 'Check the ribbon cable (Pi Zero needs the small-connector end),'
        echo 'then try adding "dtoverlay=imx708" under [all] in /boot/firmware/config.txt and reboot.'
        return 1
    fi
}

test_sht30(){
    echo 'Probing SHT30 temp/humidity sensor on I2C (addr 0x44)...'
    if sudo i2cdetect -y 1 | grep -q "44"; then
        echo 'SHT30 detected'
    else
        echo 'SHT30 not detected (sensor is optional - check wiring if one is attached)'
    fi
}

if (( $EUID == 0 )); then
    echo "Please do NOT run as root (no sudo)"
    exit
fi

yellow='\033[1;33m'
red='\033[0;31m'
lblue='\033[1;34m'
nc='\033[0m' # No Color

printf "${yellow}Hello, welcome to traps config tool (IMX708 12MP)\n${nc}"
show_witty_stats
echo would you like to:
echo '2) activate production mode'
echo '3) activate test mode'
echo '4) clean schedulers'
echo '5) new token'
echo '6) revoke token'
echo '7) test camera'
echo '8) test temp/humidity sensor'
echo 'any other key to exit'


read option

if [[ "$option" == 2 ]]; then
    echo 'Setting production mode'
    echo "false" > /home/pi/testMode.db
    sudo sh wittypi/wittyPi.sh &> /dev/null <<EOF
    5
    ?? 08:00:00
    1
    11
EOF
    read -p "Should set Dummy load? (y/n) " yn
    if [[ "$yn" == 'y' ]]; then set_dummy_load; fi
    show_witty_stats
    echo 'Done.........';

elif [[ "$option" == 3 ]]; then
    echo 'Setting test mode '
    echo "true" > /home/pi/testMode.db
    echo "Setting new witty pi 4 to test mode"
    sudo sh wittypi/wittyPi.sh &> /dev/null  <<EOF
    6
    1
    13
EOF
    read -p "Should set Dummy load? (y/n) " yn
    if [[ "$yn" == 'y' ]]; then set_dummy_load; fi
    show_witty_stats
    echo 'Done.........';

elif [[ "$option" == 4 ]]; then
    echo 'Cleaning schdeulers'
    echo  > /home/pi/testMode.db
    cd wittypi
    sudo sh wittyPi.sh &> /dev/null <<EOF
    10
    6
    11
EOF
    echo 'All schdeulers clean'
    show_witty_stats
    echo 'Done.........';

elif [[ "$option" == 5 ]]; then
    echo 'Generating new token'
    token=$(openssl rand -hex 500)
    echo "${token}"  > /home/pi/token.db
    printf "${red}*************************************************************************\n"
    printf "${red}***********************!!!IMPORTANT DEVICE DATA!!!***********************\n"
    printf "${red}*************************************************************************\n\n"
    printf "${yellow}TOKEN\n${nc}$token\n\n"
    printf "${red}*************************************************************************\n\n${nc}"
    echo 'Done.........';

elif [[ "$option" == 6 ]]; then
    echo 'Revoking token'
    echo  > /home/pi/token.db
    echo 'Token revoked'
    echo 'Done.........';

elif [[ "$option" == 7 ]]; then
    test_camera
    echo 'Done.........';

elif [[ "$option" == 8 ]]; then
    test_sht30
    echo 'Done.........';
fi
echo 'Bye :)'
exit
