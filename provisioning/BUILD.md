# IMX708 12MP Trap — Golden Image Build & Install Runbook

Hardware per trap: Raspberry Pi Zero W / Zero 2 W + Arducam IMX708 12MP
(Camera Module 3 clone, 15→22pin cable — the small connector goes into the
Zero) + Witty Pi 4 + optional FS400-SHT30 temp/humidity sensor.

OS: Raspberry Pi OS **Bookworm Lite 32-bit** (the IMX708 is libcamera-only;
the legacy Buster images cannot drive it). Scripts branch:
**`imx708-voltic-daily`** of `gigalala/trap-scripts` (derived from
`new-witty-voltic-daily-10`; only the camera layer changed).

All commands below run on the Mac from this `provisioning/` folder.

## Part A — Build the golden image (once)

Hardware for this part: one Pi + IMX708 camera. **No Witty Pi needed yet**
(attach it if you want to test the full shutdown in step A3).

### A1. Flash and boot the base OS

```bash
./flash-base.sh --ssid <YOUR_WIFI> --pass <WIFI_PASSWORD>
```

Downloads Bookworm Lite if needed, flashes the card (asks before erasing),
and pre-configures: user `pi`/`raspberry`, SSH, Wi-Fi, timezone
Asia/Jerusalem, `dtoverlay=imx708`, I2C on.

Then: card into the master Pi, power on, wait 2–4 minutes (first boot
expands the filesystem and reboots). Verify: `ssh pi@raspberrypi.local`.

### A2. Golden setup

```bash
./build-golden.sh setup pi@raspberrypi.local
```

Unattended: camera self-test, apt packages (`git python3-requests
python3-smbus i2c-tools wireless-tools`), I2C enable, SHT30 probe
(warn-only), Witty Pi 4 software, runtime files, and the phase-1 installer
crontab.

### A3. Test a full cycle (manual, with the real hardware)

The daily runtime needs an identity, so create a temporary one:

```bash
ssh pi@raspberrypi.local 'openssl rand -hex 500 > /home/pi/token.db; echo true > /home/pi/testMode.db'
```

Register that UID+token as a test trap in the admin (or copy an existing
test trap's token), then:

```bash
ssh pi@raspberrypi.local 'cd /home/pi && sudo python3 trap-daily.py'
```

Verify, in `trap.log` and the app:

1. SHT30 line appears (`SHT30 reading - temperature=... humidity=...`), or a
   single "not available" line if no sensor — either way the run continues.
2. Image captured at 4608x2592 and reaches the app (test mode).
3. Witty Pi schedule written (`wittypi/schedule.wpi` + runScript output).
4. ALARM2 shutdown fires at the end (Pi powers off — Witty Pi must be
   attached for this; without it the smbus write fails, which is expected).
5. **Critical before cloning cards: a scheduled Witty Pi wake actually boots
   the Pi again on Bookworm.**

### A4. Finalize and capture

```bash
./build-golden.sh finalize pi@raspberrypi.local   # cleans state, shuts down
# pull the card, insert into the Mac
./capture-image.sh                                # -> trap-installer/images/trap-imx708-golden.img.gz
```

`finalize` removes token/logs/test state, restores the `pi`/`raspberry`
build password, restores the installer crontab, and removes the Mac's SSH
key so clones don't trust this machine.

Optional shrink (needs Linux/WSL/Docker): PiShrink on the raw `.img`
before gzip. Not required — gzip already collapses the empty space.

## Part B — Installing each new trap (the two phases)

### Phase 1 — first boot (camera only, NO Witty Pi)

1. Flash a card from the golden image (`gzcat ... | dd`, or Pi Imager "Use
   custom" with no customization).
2. Make sure the admin has an **install trap device** whose `ssid` matches
   the install Wi-Fi (the installer authenticates with `fiddlesticks<ssid>`).
3. Pi + camera + card, power on. `installer-imx708.py` runs automatically:
   waits for internet **and a synced clock** (fixes the stale-clock TLS
   crash of the legacy installer), self-tests the camera, POSTs
   uid/password/token to `trap_install` (with retries), saves the token,
   changes the password, swaps the crontab to the daily runtime, and
   **shuts down** (also on failure — check `/home/pi/install.log` and
   `/home/pi/install.done` if no candidate appears).
4. The install candidate appears in the admin → approve it (creates the
   trap, test mode on).

### Phase 2 — Witty Pi attach

1. Attach the Witty Pi 4 following the Witty Pi manual's steps.
2. Full power-on: the trap runs a normal daily cycle and sends the image to
   test or production depending on the server settings for this trap.
3. Optional field tweaks over SSH (password = the generated one stored with
   the candidate): `bash trapInit.sh` — production/test mode, clean
   schedulers, new/revoke token, camera + sensor tests.

## SHT30 wiring (optional sensor)

FS400-SHT30, I2C address `0x44`:

| Wire (FS400) | Pi pin |
|---|---|
| Red (3.3V) | Pin 1 (3V3) |
| Black (GND) | Pin 6 (GND) |
| Yellow (SCL) | Pin 5 (GPIO3/SCL) |
| Green (SDA) | Pin 3 (GPIO2/SDA) |

Shares the I2C bus with the Witty Pi 4 (address `0x08`) — no conflict; the
Witty Pi passes all GPIO through its stacking header, so the sensor can sit
on top. Verify with `sudo i2cdetect -y 1` (expect `44`) or `trapInit.sh`
option 8. Readings are logged to `trap.log` each wakeup; server upload is a
future version.

## Focus notes (changed semantics)

The IMX708 has built-in autofocus — default behavior is
`--autofocus-on-capture`. A manual focus can be set via `trap_focus.db` or
the server `focus` field, now in **dioptres** (0 = infinity, ~2 = 50cm,
~10 = 10cm, max 32) — NOT the legacy VCM 0–1000 values; out-of-range values
fall back to autofocus. The admin focus UI is meaningless for these traps
until updated.
