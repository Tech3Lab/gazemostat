# Testing the UI Integration

This guide explains how to test the integrated UI with real buttons.

## Prerequisites

1. **Hardware Setup:**
   - RP2040 (LattePanda Iota) connected via USB
   - OLED display (SSD1306) connected to I2C (SDA=GP4, SCL=GP5)
   - Buttons wired to GPIO pins (UP=GP6, DOWN=GP7, LEFT=GP8, RIGHT=GP9, CENTER=GP10, A=GP11, B=GP12)

2. **Software:**
   - Arduino CLI installed (or use `upload_firmware.py` script)
   - Required libraries:
     - Adafruit NeoPixel
     - Adafruit SSD1306
     - Adafruit GFX Library
     - Adafruit BusIO

## Step 1: Upload the Firmware

### Option A: Using the Upload Script (Windows)
```bash
python upload_firmware.py
```

### Option B: Using Arduino CLI (Linux/Mac/Windows)
```bash
# Compile
arduino-cli compile --fqbn rp2040:rp2040:rpipico firmware

# Upload (if in bootloader mode)
# Or upload via serial port
arduino-cli upload --fqbn rp2040:rp2040:rpipico --port /dev/ttyACM0 firmware
```

### Option C: Using Arduino IDE
1. Open `firmware.ino` in Arduino IDE
2. Select board: **Raspberry Pi Pico** (or RP2040)
3. Select port
4. Click Upload

## Step 2: Physical Button Testing

After uploading, the OLED should display the **BOOT** screen immediately.

### Test Button Navigation:

1. **RIGHT Button** - Advances through main flow (v2):
   - Press RIGHT: BOOT → IN_POSITION
   - Press RIGHT: IN_POSITION → MOVE_CLOSER
   - Press RIGHT: MOVE_CLOSER → MOVE_FARTHER
   - Press RIGHT: MOVE_FARTHER → CALIBRATION
   - Press RIGHT: CALIBRATION → CALIBRATION_WARNING
   - Press RIGHT: CALIBRATION_WARNING → RECORDING
   - Press RIGHT: RECORDING → STOP_CONFIRMATION
   - Press RIGHT: STOP_CONFIRMATION → MISSING_STOP_EVENT
   - Press RIGHT: MISSING_STOP_EVENT → INFERENCE_LOADING
   - Press RIGHT: INFERENCE_LOADING → GLOBAL_RESULTS
   - Press RIGHT: GLOBAL_RESULTS → EVENT_RESULTS
   - Press RIGHT: EVENT_RESULTS → QUIT_CONFIRMATION

2. **A Button** - Jump back to start of main flow:
   - Press A: Goes to IN_POSITION screen

3. **B Button** - Jump to gaze monitoring:
   - Press B: Goes to MONITOR_GAZE screen

4. **Other Buttons** (UP/DOWN/LEFT/CENTER):
   - Currently no functionality assigned (ready for future features)

### Expected Behavior:
- Screen should update immediately when button is pressed
- Button presses are edge-detected (only triggers on press, not hold)
- Display updates at 50 Hz (every 20ms)

## Step 3: Serial Command Testing

Connect to the serial port at **115200 baud** to test UI state updates.

### Test Commands:

#### Update UI State Variables:
```bash
# Set tracker detected
OLED:UI:STATE:1:0:0:0

# Set LED detected
OLED:UI:STATE:0:1:0:0

# Set connection
OLED:UI:STATE:0:0:1:0

# Set calibration OK
OLED:UI:STATE:0:0:0:1

# Set all states
OLED:UI:STATE:1:1:1:1
```

#### Change UI Screen:
```bash
OLED:UI:SCREEN:BOOT
OLED:UI:SCREEN:LOADING
OLED:UI:SCREEN:IN_POSITION
OLED:UI:SCREEN:MOVE_CLOSER
OLED:UI:SCREEN:MOVE_FARTHER
OLED:UI:SCREEN:CALIBRATION
OLED:UI:SCREEN:CALIBRATION_WARNING
OLED:UI:SCREEN:RECORDING
OLED:UI:SCREEN:STOP_CONFIRMATION
OLED:UI:SCREEN:MISSING_STOP_EVENT
OLED:UI:SCREEN:INFERENCE_LOADING
OLED:UI:SCREEN:GLOBAL_RESULTS
OLED:UI:SCREEN:EVENT_RESULTS
OLED:UI:SCREEN:QUIT_CONFIRMATION
OLED:UI:SCREEN:MONITOR_GAZE

# Backward-compatible aliases still accepted:
OLED:UI:SCREEN:POSITION
OLED:UI:SCREEN:RESULTS
OLED:UI:SCREEN:MONITOR_POS
```

### Using Serial Monitor:

**Arduino IDE:**
1. Tools → Serial Monitor
2. Set baud rate to 115200
3. Type commands and press Enter

**Linux/Mac (screen/minicom):**
```bash
screen /dev/ttyACM0 115200
# or
minicom -D /dev/ttyACM0 -b 115200
```

**Python:**
```python
import serial
ser = serial.Serial('/dev/ttyACM0', 115200)
ser.write(b'OLED:UI:STATE:1:1:1:1\n')
ser.write(b'OLED:UI:SCREEN:POSITION\n')
```

## Step 4: Visual Testing Checklist

### BOOT Screen:
- [ ] Shows "LOADING, PLEASE WAIT..."
- [ ] Shows checkboxes for tracker, LED, connection
- [ ] Checkboxes update when state variables change

### POSITION Screen:
- [ ] (v2: IN_POSITION) Shows head position UI and "Calib.>" hint

### CALIBRATION Screen:
- [ ] (v2) Shows "CALIBRATION" header
- [ ] Calibration status text updates when `OLED:UI:STATE:*:*:*:<calib>` changes (mapped to `ui_calibration_status`)

### RECORDING Screen:
- [ ] Shows "MARKER STATUS:"
- [ ] Shows "MARKERS :" with count
- [ ] Shows "START" button (filled)
- [ ] Shows "REC" indicator
- [ ] Shows "STOP RECORDING" button

### RESULTS Screen:
- [ ] (v2: GLOBAL_RESULTS / EVENT_RESULTS) Shows results headers and next/back hints

### MONITOR_POS Screen:
- [ ] (v2) Not present; use `IN_POSITION` or other v2 screens instead

### MONITOR_GAZE Screen:
- [ ] Shows "Monitoring gaze" text

## Step 5: Debugging

### Check Serial Output:
The firmware sends button state changes to serial:
```
BTN:0000001  (binary representation of button states)
```

### Common Issues:

1. **OLED not displaying:**
   - Check I2C connections (SDA/SCL)
   - Verify OLED address (0x3C or 0x3D)
   - Check serial output for "SSD1306 init failed"

2. **Buttons not working:**
   - Verify GPIO pin connections
   - Check that buttons are wired to GND when pressed
   - Verify pull-up resistors (INPUT_PULLUP mode)
   - Check serial output for button state changes

3. **Screen not updating:**
   - Verify `oled_available` is true
   - Check that `pollButtonsAndUpdateDisplay()` is being called
   - Look for compilation errors

### Enable Debug Output:
Add Serial.println statements in `pollButtonsAndUpdateDisplay()` to see button state changes:
```cpp
Serial.print("Button ");
Serial.print(i);
Serial.println(" pressed");
```

## Step 6: Integration with Python App

The Python app (`main.py`) can control the UI via serial commands:

```python
# Example: Update UI state when tracker connects
serial_port.write(b'OLED:UI:STATE:1:0:0:0\n')

# Example: Change to recording screen
serial_port.write(b'OLED:UI:SCREEN:RECORDING\n')
```

## Quick Test Script

Save this as `test_ui.py`:

```python
#!/usr/bin/env python3
import serial
import time

# Find your serial port (adjust as needed)
port = '/dev/ttyACM0'  # Linux/Mac
# port = 'COM3'  # Windows

ser = serial.Serial(port, 115200, timeout=1)
time.sleep(2)  # Wait for connection

print("Testing UI state updates...")

# Test state updates
commands = [
    'OLED:UI:STATE:1:0:0:0',  # Tracker detected
    'OLED:UI:STATE:1:1:0:0',  # Tracker + LED
    'OLED:UI:STATE:1:1:1:0',  # Tracker + LED + Connection
    'OLED:UI:STATE:1:1:1:1',  # All states
]

for cmd in commands:
    print(f"Sending: {cmd}")
    ser.write(f"{cmd}\n".encode())
    time.sleep(1)

# Test screen changes
screens = ['BOOT', 'POSITION', 'CALIBRATION', 'RECORDING', 'RESULTS']
for screen in screens:
    print(f"Changing to {screen} screen")
    ser.write(f'OLED:UI:SCREEN:{screen}\n'.encode())
    time.sleep(2)

ser.close()
print("Test complete!")
```

Run it:
```bash
python test_ui.py
```

## Expected Results

✅ **Success indicators:**
- OLED displays BOOT screen on power-up
- Pressing RIGHT button advances through screens
- Pressing A/B buttons jump to monitor screens
- Serial commands update UI state and screens
- Display updates smoothly without flickering

❌ **Failure indicators:**
- Blank OLED display
- Buttons don't change screens
- Serial commands don't work
- Compilation errors

## Next Steps

Once basic testing passes:
1. Integrate UI state updates into your Python application
2. Add more button functionality (UP/DOWN/LEFT/CENTER)
3. Customize screen content based on your application needs
4. Add navigation history/back button support if needed
