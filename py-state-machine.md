# Python State Machine & Firmware Refactoring Plan

## 1. Architectural Overview

The goal of this refactoring is to transition the system to a **"Dumb View / Smart Controller"** architecture. 

- **Firmware (C++):** Acts strictly as a view layer. It draws pixels, displays text, and reports raw hardware events (button presses) over Serial. It makes zero decisions about what screen comes next or what a button does.
- **Python Script:** Acts as the central controller and state machine. It tracks the current application state, communicates with external services (Gazepoint server), and commands the firmware on exactly what to display.

---

## 2. Phase 1: Firmware Modifications (The "Dumb" View)

### 2.1. Gutting `ui_state_machine.cpp`

- **Remove Navigation Logic:** Delete the `next_in_main_flow()` function.
- **Remove Button Logic:** In `ui_sm_on_button(Button btn)`, remove all `switch` statements that change `g_screen`.
- **New Button Behavior:** `ui_sm_on_button` should now format a message and send it over Serial. 
  - *Example:* `Serial.println("EVENT:BTN:RIGHT");`

### 2.2. Expanding the Serial Command Parser

The firmware needs to accept explicit commands from Python to update the display.

- **Screen Commands:** Accept commands to switch the active screen.
  - *Example format:* `CMD:SCREEN:CALIBRATION` -> calls `ui_sm_set_screen(UiScreen::CALIBRATION)`
- **Dynamic UI Element Commands:** Accept commands to update text labels or visibility of UI elements (like button prompts) on the current screen.
  - *Example format:* `CMD:LABEL:BTN_RIGHT:Next` or `CMD:LABEL:BTN_A:Redo`
  - The drawing routines in `ui/main.cpp` or `generated_screens.h` will need to read these dynamic labels instead of using hardcoded strings.

---

## 3. Phase 2: Python Controller Implementation

### 3.1. Core Components

- **Serial Communicator:** A thread or async loop dedicated to reading from and writing to the serial port connected to the Arduino/ESP.
- **State Machine Manager:** A class that holds the current state (e.g., `State.BOOT`, `State.FIND_POSITION`, etc.) and defines valid transitions.
- **Event Router:** Takes incoming `EVENT:BTN:`* messages from the Serial Communicator and routes them to the State Machine Manager based on the *current state*.

### 3.2. State Handlers

Each state should have an `on_enter()`, `on_button(btn)`, and `on_exit()` method.

- `on_enter()`: Sends the `CMD:SCREEN:...` command to the firmware. Performs any setup (like checking the server).
- `on_button(btn)`: Contains the logic for what happens when a button is pressed *in this specific state*.

---

## 4. Phase 3: The CALIBRATION Flow (Implementation Example)

Here is exactly how the Python controller will handle the specific Calibration requirement:

### Step 4.1: Entering the State

1. Python transitions its internal state to `CALIBRATION`.
2. Python's `CalibrationState.on_enter()` is triggered.
3. Python sends `CMD:SCREEN:CALIBRATION` to the firmware.
4. Python makes an HTTP/API request to the Gazepoint server to check for a valid calibration.

### Step 4.2: Handling the Server Response

- **Scenario A: Valid Calibration Exists**
  1. Python sends `CMD:LABEL:BTN_RIGHT:Next` to the firmware.
  2. Python sends `CMD:LABEL:BTN_A:Redo` to the firmware.
- **Scenario B: No Valid Calibration**
  1. Python sends `CMD:LABEL:BTN_CENTER:Start` (or similar default) to the firmware.
  2. Python clears the labels for BTN_RIGHT and BTN_A.

### Step 4.3: Handling Button Presses

While in the `CALIBRATION` state, the Python `on_button(btn)` handler receives an event:

- **If `btn == BTN_RIGHT` (Next):**
  1. Python verifies a valid calibration exists (internal check).
  2. Python transitions state to `RECORD_CONFIRMATION`.
  3. Python sends `CMD:SCREEN:RECORD_CONFIRMATION` to the firmware.
- **If `btn == BTN_A` (Redo) OR `btn == BTN_CENTER` (Start):**
  1. Python initiates the actual calibration sequence with the Gazepoint server.
  2. Python sends `CMD:LABEL:STATUS:Calibrating...` to the firmware to update the UI.
  3. Upon completion, Python re-evaluates the state (back to Step 4.1).

---

## 5. Proposed Serial Protocol Draft

To keep things simple and readable, a text-based protocol separated by colons is recommended, though JSON is a viable alternative if payload complexity increases.

**Python -> Firmware (Commands)**

- `CMD:SCREEN:<SCREEN_NAME>` (e.g., `CMD:SCREEN:CALIBRATION`)
- `CMD:LABEL:<ELEMENT_ID>:<TEXT>` (e.g., `CMD:LABEL:BTN_A:Redo`)
- `CMD:VAR:<VAR_NAME>:<VALUE>` (For passing dynamic data like temperatures or progress bars)

**Firmware -> Python (Events)**

- `EVENT:BTN:<BUTTON_NAME>` (e.g., `EVENT:BTN:RIGHT`)
- `EVENT:SYS:READY` (Sent on boot to tell Python it can start sending commands)

