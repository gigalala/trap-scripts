# AGENTS.md — traps-pi-installer

## What this repo is

Installer and runtime scripts for Scarecrow **Raspberry Pi Zero camera traps** (Pi-based traps only — ESP32 traps have a separate installer in `../scarecrow-traps-installer`). A trap is a Pi Zero + Arducam motorized-focus camera + **Witty Pi 4** power-management/RTC HAT, running on battery. The trap wakes up on a Witty Pi schedule, takes a picture, uploads it to the cloud, and cuts its own power.

Published as GitHub repo `gigalala/trap-scripts`. Branches are release versions — traps self-update by `git clone --branch <version>` (see `response_actions.py: update()`). The current working branch is `new-witty-voltic-daily-10`; `origin/main` is the default/fallback version.

## Provisioning flow (how a trap is born)

1. **SD image**: A golden image containing Raspberry Pi OS + these scripts + `installer4.py` (from `../trap-init-scripts`) is burned to an SD card. Golden images (`.img.gz`, captured with dd/Win32 Disk Imager and shrunk with PiShrink) live in `../trap-installer/images/` (`trap-base-image*.img.gz`, `wittypi3.img.gz`, `wittypi4.img.gz`). Build guides and flashing scripts for the newer IMX708/Bookworm fleet are in `../trap-installer/bash-installers/imx708/`.
2. **Phase 1 — first boot (no Witty Pi attached)**: Pi Zero + camera boot with the SD card on a known install Wi-Fi network. A crontab `@reboot` entry runs `installer4.py`, which:
   - waits for internet (max ~10 min, then shuts down),
   - detects camera type (8MP vs 5MP) and writes `/home/pi/camera.db`,
   - generates a random password + 1000-char token,
   - POSTs `{uid (CPU serial), password, token}` to the server endpoint `serverless/trap_install` with header `Authorization: Bearer fiddlesticks<wifi-ssid>` — the server matches the SSID against a pre-created `install_trap_devices/{id}` Firestore doc and writes an **install candidate** at `install_trap_devices/{id}/install_candidates/{uid}`,
   - on HTTP 200: saves `/home/pi/token.db`, changes the `pi` user password from `raspberry` to the generated one, runs the Witty Pi 4 installer, and shuts down.
3. **Admin approval** (manual, in the Angular admin at `../web`, route `admin/dashboard/install-traps`): the admin creates a trap from the candidate (prefilled uid/token/password), which writes `trap_devices/{uid}`, sets `test_mode=true` + `release_status=testing`, and deletes the candidate. Only after this does the token authenticate runtime endpoints.
4. **Phase 2 — Witty Pi attach**: The Witty Pi 4 board is attached following the Witty Pi manual's steps. On the next full power-on, `takePic.sh` (crontab `@reboot`) runs `trap-daily.py`, which sends the first image to **test or production** mode depending on server-side settings (`testMode.db` is driven by the `trap_status` response).

Alternative/legacy manual path: `trapInit.sh` option 1 in this repo installs everything interactively over SSH and prints UID/token/password for manual admin registration — it does **not** call `trap_install`.

## Daily runtime (`trap-daily.py`)

Entry point on every wakeup (`@reboot sudo sh /home/pi/takePic.sh` → `sudo python trap-daily.py` in `/home/pi`). Sequence:

1. Load token (`token.db`) + CPU serial; bail if missing.
2. Set next Witty Pi startup schedule (`wittypi/schedule.wpi` + `runScript.sh` for Witty Pi 4; interactive `wittyPi.sh` menu piping for old Witty Pi 3).
3. Wait for connectivity (reboot/retry logic via `trap.data` boot counters if it fails).
4. Sync the Witty Pi RTC from network time.
5. `GET serverless/trap_status/<serial>` — the server response drives behavior: test mode, focus value, auto-focus, dummy load, stay-on, take another pic, send log, version update, change battery.
6. Take picture with `PiCamera` + Arducam VCM focus driver (`RaspberryPi/Motorized_Focus_Camera`), resolution per `camera.db`.
7. `POST serverless/trap_image` (base64 image + runtime/boot stats, Bearer token auth).
8. Optionally stay on up to 10 min polling `trap_status` for admin commands.
9. Upload `trap.log` (`serverless/trap_log`), report runtime (`serverless/trap_run_time`).
10. **Always** (in `finally`) trigger immediate Witty Pi shutdown by writing the current RTC time into the ALARM2 register over I2C (`smbus`, address `0x08`).

Retry model: on failure it reboots up to `FAIL_REBOOT_ATTEMPTS` times, then advances to the next slot in `STARTUP_TIMES` (bi-hourly 11:00→23:00), tracked in `trap.data` (JSON: `boot_count`, `startup_time`, `run_time`, `image_taken_today`).

## Server

All endpoints are Firebase cloud functions under
`https://us-central1-cameraapp-49969.cloudfunctions.net/serverless/`:
`trap_install`, `trap_image`, `trap_status/<id>`, `trap_log`, `trap_run_time`.
Auth is `Bearer <token from token.db>`, validated against `trap_devices/{uid}.token` (except `trap_install`, which uses `Bearer fiddlesticks<ssid>`). Function code: `../web/agriculture-project-managment/functions/` (`index.js`, `util/trapInstaller.js`); admin UI is the Angular app in `../web`.

## Files in this repo

| File | Purpose |
|---|---|
| `trap-daily.py` | Main wakeup/runtime script (see above) |
| `response_actions.py` | Server API helpers: status, log upload, runtime report, self-update via git |
| `trapInit.sh` | Interactive install/config menu run manually over SSH (legacy/manual install, production/test mode switching via Witty Pi menus, token regen/revoke, camera focus) |
| `takePic.sh` | Crontab `@reboot` shim → runs `trap-daily.py` |
| `Autofocus.py` | Arducam autofocus sweep (used when server requests `auto_focus`) |
| `trap.py` | Unused `Trap` data class |

## State files on the Pi (`/home/pi/`)

| File | Meaning |
|---|---|
| `token.db` | Auth token for all server calls |
| `camera.db` | `true` = 5MP camera, `false` = 8MP |
| `testMode.db` | `true`/`false` — test vs production mode (server-controlled) |
| `new_witty.db` | `true` = Witty Pi 4 (schedule-script based), else Witty Pi 3 (menu based) |
| `trap_focus.db` | Persisted camera focus value (default 295) |
| `release_version.db` | Currently installed git branch/version |
| `trap.data` | JSON boot/run state for retry + scheduling logic |
| `trap.log` | Rolling log, uploaded to server weekly or on request |

## Gotchas for agents

- **Python 2/3 split**: `trap-daily.py` on-device runs with the legacy stack (`sudo python`); `installer4.py` runs with `python3`. Mind `subprocess.communicate` string handling.
- **The clock is untrustworthy on first boot.** There is no battery RTC until the Witty Pi is attached and synced; `fake-hwclock` restores the last saved time. A stale clock breaks TLS certificate validation, and `installer4.py` has **no** try/except around its HTTPS calls — an SSLError crashes it silently (cron discards output, no shutdown, no install candidate). Real incident: see git/admin history, July 2026.
- `shutdown_witty_pi()` talks raw I2C to the Witty Pi at address `0x08`; without the HAT attached it throws, so the Pi stays on (expected during phase 1 testing).
- Witty Pi interactions are done by piping menu choices into `wittyPi.sh` heredocs — menu option numbers differ between Witty Pi 3 and 4; changing Witty Pi software versions silently breaks these.
- Traps self-update from GitHub branches: pushing to a branch a deployed trap points at is a de-facto deploy.
- Wake cadence is keyed to the server's `test_mode` flag (IMX708 branch): test mode = ~8-minute cycles (`TEST_SCHEDULE_SCRIPT`), production = daily. No more branch-per-schedule.
- Default SSH credentials before phase 1 completes: `pi` / `raspberry`. After phase 1, the password is the generated one stored server-side with the install candidate.
- Neighboring repos: `../scarecrow-traps-installer` is the **ESP32** (cellular) trap flasher — unrelated to Pi traps. `../trap-installer` holds golden images plus the newer IMX708/Bookworm scripts (libcamera/`rpicam-still` instead of `picamera` + Arducam VCM). `../trap-init-scripts` holds the first-boot `installer4.py` baked into legacy images.
