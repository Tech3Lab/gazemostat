# Technical Plan — gazemostat

This document describes the current architecture, workflows, dependencies, and implementation details so the project can be rebuilt and operated from scratch.

## Overview

`gazemostat` is a gaze-tracking application (host-side Python) paired with an RP2040 co-processor firmware (Arduino sketch) used for:

- **NeoPixel control** (WS2812/SK6812 timing handled on RP2040; host sends high-level serial commands)
- **OLED UI rendering** on a 128×64 SSD1306 over I2C, plus **button/joystick input** read on RP2040 GPIO

The host app also connects to the **Gazepoint** eye tracker API over TCP and may run ML inference (XGBoost) depending on configuration.

## Repository layout (key files)

- **Firmware**
  - `firmware.ino`: RP2040 co-processor firmware (NeoPixels + OLED UI + serial protocol)
  - `ui/v4/generated_screens.h`: header-only OLED UI (v4); contains `UiScreen`, `UiDynamicVar`, `ui_get/ui_set`, and `draw_screen(...)`
  - `upload_firmware.py`: Windows helper to install Arduino CLI + compile + upload
- **Host application**
  - `main.py`: primary Python application (UI, simulation toggles, Gazepoint TCP client, serial I/O)
  - `config.yaml`: runtime configuration (GPIO, simulation, calibration, serial port, etc.)
- **Docs / testing**
  - `TESTING_UI.md`: manual serial commands + visual checklist for OLED UI

## Firmware architecture (RP2040)

### Hardware interfaces

- **NeoPixels**
  - Library: `Adafruit_NeoPixel`
  - Data pin: `NEOPIXEL_PIN` (default GP1)
  - Count: `NEOPIXEL_COUNT` (default 4)
  - Brightness: `global_brightness` (0–255, set by serial command)
- **OLED**
  - Library: `Adafruit_SSD1306` + `Adafruit_GFX` over `Wire` (I2C)
  - I2C pins: SDA `OLED_SDA_PIN` (default GP4), SCL `OLED_SCL_PIN` (default GP5)
  - Address: probed at `0x3C` then `0x3D`
- **Buttons / joystick**
  - Wired as switches to GND, read with `INPUT_PULLUP`
  - Pins default to GP6..GP12 (`BTN_*_PIN`)
  - `readButtons()` returns a **bitmask where bit=1 means pressed**

### OLED UI rendering (v4)

- The OLED UI drawing code is in `ui/v4/generated_screens.h`.
- **Important invariant**: `draw_*_screen()` / `draw_screen()` do **not** call `display.display()`.
  - Firmware must call `display.display()` once per frame after drawing.
- Dynamic UI variables are simple globals in `ui/v4/generated_screens.h`.
  - Auto-generated vars cover core strings/bools (boot, calibration, recording, results).
  - **Post-generation additions** (kept in-repo because the UI designer project source is not present):
    - **Calibration corner indicators**: `ui_led_up_left`, `ui_led_up_right`, `ui_led_bottom_left`, `ui_led_bottom_right` (bool)
    - **Monitoring eye state**: `ui_left_eye`, `ui_right_eye` (bool)
    - **Monitoring gaze dot**: `ui_gaze_x`, `ui_gaze_y` (u8 0..255)
    - **Inference progress**: `ui_inference_prog_bar` (u8; host uses 0..100)

**Note on v4 header edits**: the repo does not include the UI designer project source; `ui/v4/generated_screens.h` is edited in-place to add a few missing dynamic variables and drawing behaviors (calibration corner indicators, inference progress bar, monitoring eye/gaze inputs). These edits must be preserved when regenerating UI.

### Serial protocol (firmware)

Line-based commands, `:`-separated, newline terminated.

- **RP2040 liveness / reset detection**
  - `BOOT:<boot_id>:<uptime_s>` (RP2040 → host, 1 Hz until ACK)
  - `HB:<boot_id>:<uptime_s>` (RP2040 → host, 1 Hz after ACK)
  - `ACK:BOOT:<boot_id>` (host → RP2040, once host finished re-init/resync)

- **Ping**
  - `PING` / `HELLO` → replies `HELLO NEOPIXEL` and `HELLO OLED`
- **NeoPixels**
  - `INIT:<count>:<brightness>`
  - `PIXEL:<idx>:<r>:<g>:<b>`
  - `ALL:ON:<r>:<g>:<b>`
  - `ALL:OFF`
  - `BRIGHTNESS:<value>`
- **OLED**
  - `OLED:INIT`
  - `OLED:TEST`
  - `OLED:FEEDBACK:ON|OFF|STATUS`
  - `OLED:UI:STATE:<tracker>:<led>:<connection>:<calib>` (legacy/back-compat; `<calib>` ignored in v3)
  - `OLED:UI:SCREEN:<screen_name>`
    - Screen names (v3): `LOADING`, `BOOT`, `FIND_POSITION`, `MOVE_CLOSER`, `MOVE_FARTHER`, `IN_POSITION`, `CALIBRATION`, `RECORD_CONFIRMATION`, `RECORDING`, `STOP_RECORD`, `INFERENCE_LOADING`, `RESULTS`, `MONITORING`
  - `OLED:UI:SET:BOOL:<var_name>:<0|1>`
  - `OLED:UI:SET:U8:<var_name>:<0..255>`
  - `OLED:UI:SET:STR:<var_name>:<value...>`
    - Host should escape newlines as `\\n` (firmware unescapes to actual newline).
- **Buttons (RP2040 → CPU)**
  - `BTN:PRESS:<BTN_NAME>`
  - `BTN:RELEASE:<BTN_NAME>`
  - Button names: `BTN_UP`, `BTN_DOWN`, `BTN_LEFT`, `BTN_RIGHT`, `BTN_CENTER`, `BTN_A`, `BTN_B`

## Host application architecture (Python)

### Configuration

- `main.py` defines defaults and optionally loads overrides from `config.yaml` (requires `PyYAML`).
- Key configuration areas:
  - Simulation toggles (e.g., `sim_gaze`, fake model results)
  - Gazepoint host/port
  - Calibration timing and points
  - RP2040 serial port/baud and NeoPixel brightness
  - RP2040 boot/reset handling:
    - `rp2040_boot_reinit_app_state` (default true): full app reset on RP2040 reboot
    - `rp2040_heartbeat_timeout_s` (default 3.0): liveness timeout for BOOT/HB

### Runtime workflow (host-owned state machine)

The host owns the screen/state machine and drives both the OLED (via serial) and the Pygame window using the same pipeline screens:

- `BOOT` → `FIND_POSITION` → (`MOVE_CLOSER`/`MOVE_FARTHER`/`IN_POSITION`) → `CALIBRATION` → `RECORD_CONFIRMATION` → `RECORDING` → `STOP_RECORD` → `INFERENCE_LOADING` → `RESULTS`
- Modal: holding `BTN_B` enters `MONITORING` and releasing returns to previous screen.

**Head positioning behavior (important):**
- During the positioning step, the host **continuously re-evaluates** the user’s distance from eye data and updates the OLED hint screen at **200ms** intervals (`MOVE_CLOSER` / `MOVE_FARTHER` / `IN_POSITION`).
- The app **must not auto-advance** from positioning into calibration. Advancing to `CALIBRATION` requires an explicit **RIGHT** button press *while currently in a good position*.

**Reset behavior:**
- `BTN_CENTER` (from the RP2040 button edges) resets the entire host app state back to `BOOT` (clears session/calibration/recording/inference state).

Keyboard simulation mapping in `main.py`:
- `W/A/S/D/X` → joystick up/left/center/right/down
- `P` → `BTN_A` (event marker toggle while recording)
- `L` (hold) → `BTN_B` (monitoring modal)
 - `R` → reset app state (same behavior as `BTN_CENTER`)

### Pygame UI (debug dashboard)

The Pygame window is a **debugging dashboard** and no longer mirrors the OLED “screen-per-step” UI. It is designed to show, at the same time:

- live eye tracker values (gaze, validity, eye distance/pupil values when available)
- current pipeline step/state
- recent button edge events from the RP2040 (press/release log)

Window mode:
- The debug dashboard runs as a **borderless “windowed fullscreen”** window when `fullscreen: true` in `config.yaml` (not exclusive fullscreen).

### Dependencies

- Runtime (`requirements.txt`):
  - `pygame`, `numpy`, optional `PyYAML`
  - optional ML: `xgboost`, `joblib`
  - hardware comms: `pyserial` (serial), `gpiod` (Linux GPIO)
- Dev (`requirements-dev.txt`):
  - includes runtime + `scikit-learn` for model tooling

## Build / upload workflow (firmware)

On Windows, use `upload_firmware.py` which:

- installs `arduino-cli` if missing
- installs RP2040 core (Earle Philhower) and required libraries
- creates a temporary sketch directory named after the `.ino` file
- copies `firmware.ino` and the `ui/` folder into that sketch directory
- compiles and uploads (COM port or UF2 depending on device mode)

## Recent changes (this update)

- Firmware OLED UI now uses **v4 UI** from `ui/v4/generated_screens.h` and no longer contains a demo/navigation state machine.
- RP2040 now forwards button edge events to the host: `BTN:PRESS:*` / `BTN:RELEASE:*`.
- Host (`main.py`) now owns the FLOW pipeline state machine and drives OLED screens/vars via `OLED:UI:*` commands.
- Host terminology is now **events** (not tasks) and recording shows both **recording timer** and **event timer**.
- Model/inference outputs are now **4 values for global results followed by 4 values per event** (up to 10 event slots).
- Mock inference generates **4 values** per page (`val1..val4`) at **~3 seconds per value** and displays progress/ETA.
- Calibration quality is displayed as a **percentage** (derived from `average_error`).

## Rollback notes

To revert this update:

- Firmware: switch `firmware.ino` back to the prior v2 UI + `ui_state_machine` (and restore `BTN:<bitmask>` debug behavior if needed).
- Host: revert `main.py` to the prior `READY/CALIBRATING/COLLECTING/ANALYZING/RESULTS` flow and its older keyboard shortcuts.

