#!/bin/bash
# build-golden.sh - macOS: build the IMX708 trap golden image on the master Pi
# over SSH. Two stages, with a manual test window in between:
#
#   ./build-golden.sh setup pi@<pi-host>      # install everything on the Pi
#   ... test a full cycle (see BUILD.md) ...
#   ./build-golden.sh finalize pi@<pi-host>   # clean per-device state + shut down
#
# After 'finalize' the Pi powers off; pull the card and run capture-image.sh.
#
# The script installs an SSH key on the Pi first (one password prompt), so the
# rest runs unattended.

set -euo pipefail

STAGE="${1:-}"
PI="${2:-}"
BUILD_PASSWORD="${BUILD_PASSWORD:-raspberry}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

RUNTIME_FILES=(trap-daily.py response_actions.py takePic.sh trapInit.sh installer-imx708.py)

if [[ -z "$STAGE" || -z "$PI" ]]; then
    echo "Usage: $0 <setup|finalize> pi@<pi-host>"
    exit 1
fi

ensure_key(){
    if [[ ! -f "$HOME/.ssh/id_ed25519" && ! -f "$HOME/.ssh/id_rsa" ]]; then
        echo ">>> Generating an SSH key"
        ssh-keygen -t ed25519 -N "" -f "$HOME/.ssh/id_ed25519"
    fi
    echo ">>> Installing SSH key on the Pi (enter the Pi password once if asked)"
    ssh-copy-id -o StrictHostKeyChecking=accept-new "$PI" >/dev/null
}

if [[ "$STAGE" == "setup" ]]; then
    ensure_key

    echo ">>> Copying runtime files"
    for f in "${RUNTIME_FILES[@]}"; do
        if [[ ! -f "$REPO_DIR/$f" ]]; then
            echo "ERROR: missing $REPO_DIR/$f (run from the imx708-voltic-daily branch checkout)"
            exit 1
        fi
    done
    scp "${RUNTIME_FILES[@]/#/$REPO_DIR/}" "$PI:/home/pi/"

    echo ">>> Running golden-image setup on the Pi (this installs packages - takes a while)"
    ssh "$PI" 'bash -s' <<'REMOTE'
set -e
cd /home/pi

echo '--- Timezone'
sudo timedatectl set-timezone Asia/Jerusalem

echo '--- Camera self-test (must pass before anything else)'
if ! rpicam-still -n -t 2000 -o /home/pi/camera-test.jpg; then
    echo '!!! Camera test FAILED - check ribbon cable / dtoverlay=imx708 in /boot/firmware/config.txt !!!'
    exit 1
fi

echo '--- Installing packages'
sudo apt-get update
sudo apt-get install -y git python3-requests python3-smbus i2c-tools wireless-tools

echo '--- Enabling I2C'
sudo raspi-config nonint do_i2c 0

echo '--- Probing SHT30 (optional sensor, warn-only)'
if sudo i2cdetect -y 1 | grep -q '44'; then
    echo 'SHT30 detected at 0x44'
else
    echo 'SHT30 not detected (ok - sensor is optional)'
fi

echo '--- Marking Witty Pi type'
echo "true" > /home/pi/new_witty.db

echo '--- Installing Witty Pi 4 software'
if [ ! -d /home/pi/wittypi ]; then
    wget -q https://www.uugear.com/repo/WittyPi4/install.sh -O wittypi4-install.sh
    sudo sh wittypi4-install.sh
else
    echo 'Witty Pi software already present, skipping'
fi

echo '--- Setting phase-1 installer crontab'
crontab -r 2>/dev/null || true
echo "@reboot python3 /home/pi/installer-imx708.py" | crontab -

echo '--- Setup done'
REMOTE

    echo
    echo "Setup complete. Now TEST before finalizing (see provisioning/BUILD.md):"
    echo "  1. Temporary identity:  ssh $PI 'openssl rand -hex 500 > /home/pi/token.db; echo true > /home/pi/testMode.db'"
    echo "     (register the token in the admin, or use an existing test trap token)"
    echo "  2. Full cycle:          ssh $PI 'cd /home/pi && sudo python3 trap-daily.py' and watch trap.log"
    echo "  3. Verify: image reaches the app, Witty Pi schedule is set, ALARM2 shutdown works, SHT30 line in trap.log."
    echo "When satisfied:           ./build-golden.sh finalize $PI"

elif [[ "$STAGE" == "finalize" ]]; then
    echo ">>> Cleaning per-device state and shutting the Pi down"
    ssh "$PI" 'bash -s' <<REMOTE
set -e
cd /home/pi
echo '--- Removing per-device state'
rm -f token.db trap.data trap.log install.log install.done latest.jpg camera-test.jpg trap_focus.db release_version.db
> testMode.db
echo '--- Restoring installer crontab'
crontab -r 2>/dev/null || true
echo "@reboot python3 /home/pi/installer-imx708.py" | crontab -
echo '--- Restoring build password and clearing history'
echo "pi:$BUILD_PASSWORD" | sudo chpasswd
history -c 2>/dev/null || true
rm -f /home/pi/.bash_history
echo '--- Removing SSH authorized key (clones must not trust this Mac)'
rm -f /home/pi/.ssh/authorized_keys
echo '--- Shutting down'
sudo shutdown -h now
REMOTE
    echo
    echo "The Pi is shutting down. When its LED stops blinking:"
    echo "  1. Pull the SD card and put it in this Mac."
    echo "  2. Run ./capture-image.sh to create the golden image."

else
    echo "Unknown stage '$STAGE' (use setup or finalize)"
    exit 1
fi
