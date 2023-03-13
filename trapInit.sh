#!/bin/bash
# VERSION = 2.1

show_witty_stats(){
    if [ ! -f /home/pi/wittypi/wittyPi.sh ]; then
        return 
    fi
    printf "${red}*************************************************************************\n${nc}"
    echo -e "11\n"  | sudo sh /home/pi/wittypi/wittyPi.sh | while read line; do 
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

if (( $EUID == 0 )); then
    echo "Please do NOT run as root (no sudo)"
    exit
fi

yellow='\033[1;33m'
red='\033[0;31m'
lblue='\033[1;34m'
nc='\033[0m' # No Color

printf "${yellow}Hello, welcome to traps installer/config tool\n${nc}"
show_witty_stats
echo would you like to:
echo '1) install new trap'
if test -f "trap-daily.py"; then
    echo '2) activate production mode'
    echo '3) activate test mode'
    echo '4) clean schedulers'
    echo '5) new token'
    echo '6) revoke token'
    echo '7) focus camera'
fi
    echo 'any other key to exit'


read option

if [[ "$option" == 1 ]] ;then
    while true; do
        read -p "Is it a five mega pixel camera? (y/n) " yn
        if [[ "$yn" == 'y' ]]; then echo "true" > /home/pi/camera.db; break; fi
        if [[ "$yn" == 'n' ]]; then echo "false" > /home/pi/camera.db; break; fi
    done
    uid=$(cat /proc/cpuinfo | grep Serial | cut -d ' ' -f 2)
    password=$(openssl rand -hex 8)
    token=$(openssl rand  -hex 500)
    echo 'Setting timezone'
    sudo timedatectl set-timezone Asia/Jerusalem
    echo date
    echo 'Shutting Down HDMI for battery improvements'
    sudo /opt/vc/bin/tvservice -o
    echo 'Installing new trap'
    #Downloading files
    echo 'Downloading files'
    echo "Downloading schedules"
    echo 'Downloading image scripts'
    wget -4 'https://raw.githubusercontent.com/gigalala/trap-scripts/main/takePic.sh' -O takePic.sh
    wget -4 'https://raw.githubusercontent.com/gigalala/trap-scripts/main/trap-daily.py' -O trap-daily.py
    wget -4 'https://raw.githubusercontent.com/gigalala/trap-scripts/main/response_actions.py' -O response_actions.py

    #install pip and and python modules 
    echo 'Getting pip and python modules if needed'
    sudo apt-get update
    sudo apt install git
    echo "y\n" | sudo apt install python-pip
    echo "y\n" | sudo apt install python-opencv
    sudo pip install picamera
    sudo pip install requests
    

    #Enable camera
    echo 'Enabling camera'
    sudo raspi-config nonint do_camera 0

    #Downloading autofocus software
    echo 'Downloading autofocus software'
    git clone https://github.com/ArduCAM/RaspberryPi.git --branch legacy_version

    wget -4 'https://raw.githubusercontent.com/gigalala/trap-scripts/main/Autofocus.py' -O Autofocus.py

    #Disable auto-login
    echo 'Disable auto-login if exisits in system'
    sudo sed -i.backup '/autologin-user=/d' /etc/lightdm/lightdm.conf

    #Adding startup script to corntab
    echo 'Add startup script'
    crontab -l | { cat; echo "@reboot sudo sh /home/pi/takePic.sh"; } | crontab -

    #Change password
    echo 'Changing password'
    printf 'raspberry\n%s\n%s\n' "$password" "$password" | passwd

    #Download and install Witty Pi software
    echo 'Downloading Witty pi software'
    read -p "Install new witty pi 4? (y/n) " yn
    if [[ "$yn" == 'y' ]]; then
      wget http://www.uugear.com/repo/WittyPi4/install.sh
      echo "true" > /home/pi/new_witty.db
      echo 'Install new Witty pi 4 Software'
    EOF
    elif [[ "$yn" == 'n' ]]; then
      wget http://www.uugear.com/repo/WittyPi3/install.sh
      echo 'Install old Witty pi 3 software'
    EOF
    sudo sh install.sh
    echo 'adding GPIO-4 fix to wittyPi/daemon.sh'
    sudo sed -i '119d' wittypi/daemon.sh # dansker
    sed -i '119iwhile [ $counter -lt 20]; do' wittypi/daemon.sh #dansker

    printf "${red}*************************************************************************\n"
    printf "${red}***********************!!!IMPORTANT DEVICE DATA!!!***********************\n"
    printf "${red}*************************************************************************\n\n"

    printf "${yellow}PASSWORD\n${nc}$password\n\n"
    printf "${yellow}UID\n${nc}$uid\n\n"
    printf "${yellow}TOKEN\n${nc}$token\n\n"

    printf "${red}*************************************************************************\n\n${nc}"


    echo 'saving token'
    echo "${token}" > /home/pi/token.db
    echo 'Done.........';
    echo 'Rebooting'
    cd RaspberryPi/Motorized_Focus_Camera
    sudo chmod +x enable_i2c_vc.sh
    sudo ./enable_i2c_vc.sh &> /dev/null <<EOF
    y
EOF

elif [[ "$option" == 2 ]]; then
    echo 'Setting production mode'
    echo "false" > /home/pi/testMode.db
    sudo sh wittypi/wittyPi.sh &> /dev/null <<EOF
    5
    ?? 08:00:00
    1
    11
EOF
    read -p "Should set Dummy load? (y/n) " yn
    if [[ "$yn" == 'y' ]]; then set_dummy_load; break; fi
    show_witty_stats
    echo 'Done.........';

elif [[ "$option" == 3 ]]; then
    echo 'Setting test mode '
    echo "true" > /home/pi/testMode.db
    echo "Setting new witty pi 4 to test mode"
#    read -p "Is this the new witty pi 4? (y/n) " yn
#    if [[ "$yn" == 'y' ]]; then
    sudo sh wittypi/wittyPi.sh &> /dev/null  <<EOF
    6
    1
    13
EOF
#    if [[ "$yn" == 'n' ]]; then
#      startup=??
#      while true; do
#          read -p "daily startup? (y/n) " yn
#          if [[ "$yn" == 'y' ]]; then
#            startup=08
#            break;
#          fi
#          if [[ "$yn" == 'n' ]]; then
#            break;
#          fi
#      done
#      sudo sh wittypi/wittyPi.sh &> /dev/null  <<EOF
#      5
#      ?? $startup:00:00
#      1
#      11
read -p "Should set Dummy load? (y/n) " yn
if [[ "$yn" == 'y' ]]; then set_dummy_load; break; fi

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
    echo 'Focusing camera'
    cd RaspberryPi/Motorized_Focus_Camera/python
    sudo python Autofocus.py
    echo 'Done.........';
fi
echo 'Bye :)'
exit