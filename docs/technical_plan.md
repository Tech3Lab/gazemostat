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
  - `ui/v2/generated_screens.h`: header-only, UI designer output (v2); contains `UiScreen` enum and `draw_screen(...)`
  - `ui/v2/ui_state_machine.h`, `ui/v2/ui_state_machine.cpp`: UI navigation state machine (button→screen transitions)
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

- The UI drawing code is generated in `ui/v2/generated_screens.h`.
- **Important invariant**: `draw_*_screen()` / `draw_screen()` do **not** call `display.display()`.
  - Firmware must call `display.display()` once per frame after drawing.
- Dynamic UI variables are simple globals in `ui/v2/generated_screens.h` (examples):
  - booleans: `ui_tracker_detected`, `ui_led_detected`, `ui_connection`
  - strings: `ui_loading_data`, `ui_calibration_status`, `ui_recording_timer`, `ui_event_name`, etc.
- Firmware updates those globals from its own state before each render.

### UI navigation state machine

- Implemented in `ui/v2/ui_state_machine.{h,cpp}`.
- Firmware-facing API:
  - `ui_sm_init()`
  - `ui_sm_on_button(Button btn)` (advances screen based on button presses)
  - `ui_sm_get_screen() -> UiScreen`
  - `ui_sm_set_screen(UiScreen)` (used by serial commands to force a screen)
- The firmware polls buttons at ~50Hz and sends press edges into the state machine.
- Main flow in v2 advances on `BTN_RIGHT`:
  - `BOOT → IN_POSITION → MOVE_CLOSER → MOVE_FARTHER → CALIBRATION → CALIBRATION_WARNING → RECORDING → STOP_CONFIRMATION → MISSING_STOP_EVENT → INFERENCE_LOADING → GLOBAL_RESULTS → EVENT_RESULTS → QUIT_CONFIRMATION`
- Shortcuts:
  - `BTN_A` forces `IN_POSITION`
  - `BTN_B` forces `MONITOR_GAZE`

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
    - Screen names (v2): `BOOT`, `LOADING`, `IN_POSITION`, `MOVE_CLOSER`, `MOVE_FARTHER`, `CALIBRATION`, `CALIBRATION_WARNING`, `RECORDING`, `STOP_CONFIRMATION`, `MISSING_STOP_EVENT`, `INFERENCE_LOADING`, `GLOBAL_RESULTS`, `EVENT_RESULTS`, `QUIT_CONFIRMATION`, `MONITOR_GAZE`
    - Backward-compatible aliases: `POSITION`→`IN_POSITION`, `RESULTS`→`GLOBAL_RESULTS`, `MONITOR_POS`→`IN_POSITION`
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

- Firmware OLED UI now uses the **v2 generated UI** and **v2 navigation state machine** from `ui/v2/`.
- Updated the firmware’s `OLED:UI:SCREEN:<name>` parsing to the new v2 `UiScreen` names (and kept a few legacy aliases).
- Updated dynamic UI binding: calibration is now represented as a **status string** (`ui_calibration_status`) rather than a boolean checkbox variable.

## Rollback notes

To revert this update:

- Switch `firmware.ino` includes back from `ui/v2/*` to the prior `ui/*` generated UI + state machine, and restore the old `OLED:UI:SCREEN` name mapping.

