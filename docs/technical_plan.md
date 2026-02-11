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
  - `ui/generated_screens.h`: header-only, UI designer output; contains `UiScreen` enum and `draw_screen(...)`
  - `ui/ui_state_machine.h`, `ui/ui_state_machine.cpp`: UI navigation state machine (button→screen transitions)
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

### OLED UI rendering

- The UI drawing code is generated in `ui/generated_screens.h`.
- **Important invariant**: `draw_*_screen()` / `draw_screen()` do **not** call `display.display()`.
  - Firmware must call `display.display()` once per frame after drawing.
- Dynamic UI variables are simple globals in `ui/generated_screens.h` (examples):
  - `ui_tracker_detected`, `ui_led_detected`, `ui_connection`, `ui_calibration_ok`
- Firmware updates those globals from its own state before each render.

### UI navigation state machine

- Implemented in `ui/ui_state_machine.{h,cpp}`.
- Firmware-facing API:
  - `ui_sm_init()`
  - `ui_sm_on_button(Button btn)` (advances screen based on button presses)
  - `ui_sm_get_screen() -> UiScreen`
  - `ui_sm_set_screen(UiScreen)` (used by serial commands to force a screen)
- The firmware polls buttons at ~50Hz and sends press edges into the state machine.

### Serial protocol (firmware)

Line-based commands, `:`-separated, newline terminated.

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
  - `OLED:UI:STATE:<tracker>:<led>:<connection>:<calib>`
    - Updates dynamic UI variables and re-renders
  - `OLED:UI:SCREEN:<screen_name>`
    - Screen names: `BOOT`, `POSITION`, `CALIBRATION`, `RECORDING`, `RESULTS`, `MONITOR_POS`, `MONITOR_GAZE`
    - Forces the UI screen via `ui_sm_set_screen(...)` and re-renders
- **Button debug**
  - On any button state change, firmware prints `BTN:<7 bits>` where `1` indicates pressed.

## Host application architecture (Python)

### Configuration

- `main.py` defines defaults and optionally loads overrides from `config.yaml` (requires `PyYAML`).
- Key configuration areas:
  - Simulation toggles (e.g., `sim_gaze`, fake model results)
  - Gazepoint host/port
  - Calibration timing and points
  - RP2040 serial port/baud and NeoPixel brightness

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

- Firmware UI navigation logic is now sourced from `ui/ui_state_machine.{h,cpp}` instead of a duplicate implementation in `firmware.ino`.
- Fixed button edge detection so UI transitions happen on **press** (0→1 in the internal bitmask), not on release.
- Centralized OLED rendering so each update performs:
  - dynamic variable sync → `draw_screen(display, ui_sm_get_screen())` → `display.display()`
- Added missing generated UI dynamic variable `ui_calibration_ok` and a small checkbox indicator on the CALIBRATION screen.

## Rollback notes

To revert this update:

- Restore the previous inlined UI navigation logic in `firmware.ino` and remove the `ui_sm_*` integration.
- Remove `ui_calibration_ok` additions from `ui/generated_screens.h` if your UI generator already provides a different calibration indicator.

