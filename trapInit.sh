#!/bin/bash

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
echo '1) intall new trap'
echo '2) activate production mode'
echo '3) activate test mode'
echo '4) clean schdeulers'
echo '5) new token'
echo '6) revoke token' 
echo '7) focus camera'
echo 'any other key to exit'


read option

if [[ "$option" == 1 ]] ;then

    uid=$(cat /proc/cpuinfo | grep Serial | cut -d ' ' -f 2)
    password=$(openssl rand -hex 8)
    token=$(openssl rand  -hex 500)
    echo 'Setting timezone'
    sudo timedatectl set-timezone Asia/Jerusalem
    echo date
    echo 'Installing new trap'
    #Downloading files
    echo 'Downloading files'
    echo "Downloading schedules"
    echo 'Downloading image scripts'
    wget -4 'https://firebasestorage.googleapis.com/v0/b/cameraapp-49969.appspot.com/o/traps%2FtakePic.sh?alt=media&token=fdf0bd3c-f73d-4b85-9b7e-6d7b36a05f9a' -O takePic.sh
    wget -4 'https://firebasestorage.googleapis.com/v0/b/cameraapp-49969.appspot.com/o/traps%2Ftrap-daily.py?alt=media&token=bf051865-0d95-444f-ba77-9e1f64bdb53d' -O trap-daily.py
    wget -4 'https://firebasestorage.googleapis.com/v0/b/cameraapp-49969.appspot.com/o/traps%2Fresponse_actions.py?alt=media&token=fb2a3e84-564e-4389-9921-d59363dcf542' -O response_actions.py

    #install pip and and python modules 
    echo 'Getting pip and python modules if needed'
    sudo apt-get update
    echo "y\n" | sudo apt install python-pip
    echo "y\n" | sudo apt install python-opencv
    sudo pip install picamera
    sudo pip install requests
    

    #Enable camera
    echo 'Enabling camera'
    sudo raspi-config nonint do_camera 0

    #Downloading autofocus software
    echo 'Downloading autofocus software'
    git clone https://github.com/ArduCAM/RaspberryPi.git
    wget -4 'https://firebasestorage.googleapis.com/v0/b/cameraapp-49969.appspot.com/o/traps%2FAutofocus.py?alt=media&token=cfda1a21-5e67-4167-bab4-dabbe26aab07' -O RaspberryPi/Motorized_Focus_Camera/python/Autofocus.py


    #Disable autologin
    echo 'Disable autologin if exisits in system'
    sudo sed -i.backup '/autologin-user=/d' /etc/lightdm/lightdm.conf

    #Adding startup script to corntab
    echo 'Add startup script'
    crontab -l | { cat; echo "@reboot sudo sh /home/pi/takePic.sh"; } | crontab -

    #Change password
    echo 'Changing password'
    printf 'raspberry\n%s\n%s\n' "$password" "$password" | passwd

    #Download and install Witty Pi software
    echo 'Downloading Witty pi software'
    wget http://www.uugear.com/repo/WittyPi3/install.sh
    echo 'Install Witty pi software'
    sudo sh install.sh


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
    4
    ?? 08:20
    5
    ?? 08:00:00
    1
    11
EOF
    set_dummy_load
    show_witty_stats
    sudo shutdown -h 2
    echo 'Done.........';

elif [[ "$option" == 3 ]]; then
    echo 'Setting test mode '
    echo "true" > /home/pi/testMode.db
    sudo sh wittypi/wittyPi.sh &> /dev/null  <<EOF
    4
    ?? ??:20
    5
    ?? ??:00:00
    1
    11
EOF
set_dummy_load
show_witty_stats
sudo shutdown -h 2
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