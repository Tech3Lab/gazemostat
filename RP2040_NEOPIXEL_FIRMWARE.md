# RP2040 NeoPixel Firmware Guide for LattePanda Iota

This guide explains how to program the onboard RP2040 on the LattePanda Iota to control NeoPixel LEDs for calibration.

## Prerequisites

- LattePanda Iota with onboard RP2040
- USB cable to connect LattePanda to your computer
- Windows computer (for automated script) OR Arduino IDE (for manual method)
- NeoPixel LEDs (WS2812/SK6812) - 4 LEDs chained in series
- Python 3.x (for automated script method)

## Upload Methods

There are two ways to upload the firmware:

1. **Automated Python Script (Recommended)** - Easiest method, handles everything automatically
2. **Manual Arduino IDE** - Traditional method using Arduino IDE GUI

Choose the method that works best for you.

---

## Method 1: Automated Python Script (Recommended for Windows)

This is the easiest method - the script handles everything automatically.

### Step 1: Run the Upload Script

1. **Open Command Prompt or PowerShell** on Windows

2. **Navigate to the project directory**:
   ```cmd
   cd path\to\thermostat
   ```

3. **Run the upload script**:
   ```cmd
   python upload_firmware.py
   ```

### What the Script Does

The script automatically:
- ✅ Checks if Arduino CLI is installed (downloads and installs if needed)
- ✅ Installs RP2040 board support
- ✅ Installs Adafruit NeoPixel library
- ✅ Compiles the firmware (`firmware.ino`)
- ✅ Detects RP2040 bootloader drive or COM port
- ✅ Uploads the firmware

### Step 2: Enter Bootloader Mode (if needed)

If the script can't find the RP2040 automatically:

1. **Locate the buttons** on your LattePanda Iota:
   - **BOOTSEL** button (bootloader select)
   - **RST** button (reset)

2. **Enter bootloader mode**:
   - Press and **hold** the **BOOTSEL** button
   - While holding BOOTSEL, press and release the **RST** button
   - Release the **BOOTSEL** button
   - Windows should detect a USB drive named `RPI-RP2`

3. **Run the script again**:
   ```cmd
   python upload_firmware.py
   ```

The script will detect the bootloader drive and upload the firmware automatically.

### Troubleshooting the Script

- **"Arduino CLI not found"** - The script will download it automatically on first run
- **"No RP2040 device found"** - Enter bootloader mode (see Step 2 above)
- **"Compilation failed"** - Check that `firmware.ino` exists (or check `firmware_path` in config.yaml)
- **"Upload failed"** - Try entering bootloader mode manually, or check USB cable

---

## Method 2: Manual Arduino IDE Upload

If you prefer using the Arduino IDE GUI, follow these steps:

### Step 1: Install Arduino IDE and RP2040 Support

1. **Download Arduino IDE** from https://www.arduino.cc/en/software
   - Version 2.x recommended, but 1.8.x also works

2. **Add RP2040 Board Support**:
   - Open Arduino IDE
   - Go to **File → Preferences**
   - In "Additional Boards Manager URLs", add:
     ```
     https://github.com/earlephilhower/arduino-pico/releases/download/global/package_rp2040_index.json
     ```
   - Click OK

3. **Install RP2040 Boards**:
   - Go to **Tools → Board → Boards Manager**
   - Search for "Raspberry Pi Pico / RP2040"
   - Install "Raspberry Pi Pico / RP2040" by Earle Philhower

4. **Install NeoPixel Library**:
   - Go to **Tools → Manage Libraries**
   - Search for "Adafruit NeoPixel"
   - Install "Adafruit NeoPixel" by Adafruit

### Step 2: Upload Firmware to RP2040

### Enter Bootloader Mode

1. **Locate the buttons** on your LattePanda Iota:
   - **BOOTSEL** button (bootloader select)
   - **RST** button (reset)

2. **Enter bootloader mode**:
   - Press and **hold** the **BOOTSEL** button
   - While holding BOOTSEL, press and release the **RST** button
   - Release the **BOOTSEL** button
   - Windows should detect a USB drive named `RPI-RP2`

### Configure Arduino IDE

1. **Select Board**:
   - Go to **Tools → Board → Raspberry Pi Pico / RP2040 → Raspberry Pi Pico**

2. **Select Port**:
   - Go to **Tools → Port**
   - Select the COM port (should appear after entering bootloader mode)
   - If no port appears, you may need to enter bootloader mode again

3. **Other Settings** (usually defaults are fine):
   - **CPU Speed**: 133 MHz (default)
   - **Flash Size**: 2MB (or whatever your board has)
   - **Debug Port**: Disabled
   - **USB Stack**: Pico SDK

### Upload the Firmware

1. Copy the firmware code (see `firmware.ino` below)
2. Paste it into Arduino IDE
3. Click **Upload** button
4. Wait for compilation and upload to complete
5. The RP2040 will automatically reboot after upload

**Note**: After the first upload, Arduino IDE can auto-reset the board, so you may not need to manually enter bootloader mode for subsequent uploads.

---

## Step 3: Wiring

Connect your NeoPixels to the RP2040:

```
NeoPixel Chain:
  Pixel 1 DIN  → RP2040 GPIO pin (e.g., GP1)
  Pixel 1 VCC  → 5V power (use LattePanda's 5V pin or external supply)
  Pixel 1 GND  → Ground (common ground with LattePanda)
  
  Pixel 1 DOUT → Pixel 2 DIN
  Pixel 2 DOUT → Pixel 3 DIN
  Pixel 3 DOUT → Pixel 4 DIN
```

**Important Notes**:
- RP2040 GPIO pins are **3.3V logic** - NeoPixels typically accept 3.3V data signals
- NeoPixels need **5V power** - use LattePanda's 5V pin or external 5V supply
- Ensure **common ground** between RP2040 and NeoPixel power supply
- For 4 pixels at 30% brightness: ~72mA total current needed

---

## Step 4: Test the Connection

1. After uploading firmware, the RP2040 should send "HELLO NEOPIXEL" over serial
2. Open Arduino IDE Serial Monitor (Tools → Serial Monitor)
3. Set baud rate to **115200**
4. You should see "HELLO NEOPIXEL" message
5. Try sending test commands:
   - `INIT:4:76` (initialize 4 pixels at 30% brightness = 76/255)
   - `PIXEL:0:255:255:255` (turn on first pixel white)
   - `ALL:OFF` (turn off all pixels)

---

## Firmware Code

The firmware code is in `firmware.ino` in the project directory (or as configured in `config.yaml`).

If using Arduino IDE manually, create a new Arduino sketch and paste this code:

```cpp
// NeoPixel Controller for LattePanda Iota RP2040
// Implements serial protocol for controlling WS2812/SK6812 NeoPixels

#include <Adafruit_NeoPixel.h>

// Configuration - CHANGE THESE TO MATCH YOUR SETUP
#define NEOPIXEL_PIN    1      // GPIO pin connected to NeoPixel DIN (GP1)
#define NEOPIXEL_COUNT  4      // Number of NeoPixels in chain
#define SERIAL_BAUD     115200  // Serial communication baud rate

// Create NeoPixel object
Adafruit_NeoPixel strip(NEOPIXEL_COUNT, NEOPIXEL_PIN, NEO_GRB + NEO_KHZ800);

// Global brightness (0-255)
uint8_t global_brightness = 76;  // Default: 30% (76/255)

void setup() {
  // Initialize serial communication
  Serial.begin(SERIAL_BAUD);
  
  // Wait for serial port to open (optional, for USB serial)
  // Uncomment if you want to wait for serial connection:
  // while (!Serial) {
  //   delay(10);
  // }
  
  // Initialize NeoPixel strip
  strip.begin();
  strip.setBrightness(global_brightness);
  strip.show(); // Initialize all pixels to 'off'
  
  // Send hello message for auto-detection
  Serial.println("HELLO NEOPIXEL");
  
  // Small delay to ensure message is sent
  delay(100);
}

void loop() {
  // Check for incoming serial commands
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    command.trim();  // Remove whitespace
    
    if (command.length() > 0) {
      processCommand(command);
    }
  }
}

void processCommand(String cmd) {
  // Parse command format: COMMAND:param1:param2:...
  int firstColon = cmd.indexOf(':');
  if (firstColon < 0) {
    // No parameters
    if (cmd == "ALL:OFF") {
      allOff();
      Serial.println("ACK");
      return;
    }
    Serial.println("ERROR:Invalid command");
    return;
  }
  
  String command = cmd.substring(0, firstColon);
  String params = cmd.substring(firstColon + 1);
  
  if (command == "INIT") {
    // INIT:<count>:<brightness>
    int count = getParam(params, 0).toInt();
    int brightness = getParam(params, 1).toInt();
    
    if (count > 0 && count <= 255 && brightness >= 0 && brightness <= 255) {
      // Note: We can't change pixel count at runtime, but we can set brightness
      global_brightness = brightness;
      strip.setBrightness(global_brightness);
      strip.show();
      Serial.println("ACK");
    } else {
      Serial.println("ERROR:Invalid parameters");
    }
    
  } else if (command == "PIXEL") {
    // PIXEL:<idx>:<r>:<g>:<b>
    int idx = getParam(params, 0).toInt();
    int r = getParam(params, 1).toInt();
    int g = getParam(params, 2).toInt();
    int b = getParam(params, 3).toInt();
    
    if (idx >= 0 && idx < NEOPIXEL_COUNT && 
        r >= 0 && r <= 255 && g >= 0 && g <= 255 && b >= 0 && b <= 255) {
      strip.setPixelColor(idx, strip.Color(r, g, b));
      strip.show();
      Serial.println("ACK");
    } else {
      Serial.println("ERROR:Invalid parameters");
    }
    
  } else if (command == "ALL") {
    // ALL:ON:<r>:<g>:<b> or ALL:OFF
    if (params.startsWith("ON:")) {
      String colorParams = params.substring(3);
      int r = getParam(colorParams, 0).toInt();
      int g = getParam(colorParams, 1).toInt();
      int b = getParam(colorParams, 2).toInt();
      
      if (r >= 0 && r <= 255 && g >= 0 && g <= 255 && b >= 0 && b <= 255) {
        uint32_t color = strip.Color(r, g, b);
        for (int i = 0; i < NEOPIXEL_COUNT; i++) {
          strip.setPixelColor(i, color);
        }
        strip.show();
        Serial.println("ACK");
      } else {
        Serial.println("ERROR:Invalid color values");
      }
    } else {
      Serial.println("ERROR:Invalid ALL command");
    }
    
  } else if (command == "BRIGHTNESS") {
    // BRIGHTNESS:<value>
    int brightness = params.toInt();
    
    if (brightness >= 0 && brightness <= 255) {
      global_brightness = brightness;
      strip.setBrightness(global_brightness);
      strip.show();
      Serial.println("ACK");
    } else {
      Serial.println("ERROR:Invalid brightness value");
    }
    
  } else {
    Serial.println("ERROR:Unknown command");
  }
}

// Helper function to extract parameter by index
String getParam(String params, int index) {
  int start = 0;
  int currentIndex = 0;
  
  for (int i = 0; i <= params.length(); i++) {
    if (i == params.length() || params.charAt(i) == ':') {
      if (currentIndex == index) {
        return params.substring(start, i);
      }
      start = i + 1;
      currentIndex++;
    }
  }
  return "";
}

// Turn off all pixels
void allOff() {
  for (int i = 0; i < NEOPIXEL_COUNT; i++) {
    strip.setPixelColor(i, 0);
  }
  strip.show();
}
```

## Customization

### Change GPIO Pin

If you want to use a different GPIO pin (not GP1), change this line:
```cpp
#define NEOPIXEL_PIN    1      // Change to your GPIO pin number
```

### Change Pixel Count

If you have more or fewer pixels:
```cpp
#define NEOPIXEL_COUNT  4      // Change to your pixel count
```

### Change Color Order

If your NeoPixels use a different color order (most use GRB):
```cpp
// In strip initialization, change NEO_GRB to:
// NEO_RGB  - for RGB order
// NEO_GRBW - for RGBW pixels
Adafruit_NeoPixel strip(NEOPIXEL_COUNT, NEOPIXEL_PIN, NEO_GRB + NEO_KHZ800);
```

## Troubleshooting

### RP2040 Not Detected

- Make sure you entered bootloader mode correctly (BOOTSEL + RST)
- Try a different USB cable
- Check Windows Device Manager for COM port

### NeoPixels Don't Light Up

- Verify wiring: DIN to correct GPIO pin, VCC to 5V, GND to ground
- Check that NeoPixels are getting 5V power (measure with multimeter)
- Try increasing brightness: send `BRIGHTNESS:255`
- Verify GPIO pin number matches your wiring

### Serial Communication Issues

- Check baud rate matches (115200)
- Make sure no other program is using the COM port
- Try closing and reopening Serial Monitor
- Check that firmware uploaded successfully

### Colors Are Wrong

- Your NeoPixels might use RGB order instead of GRB
- Change `NEO_GRB` to `NEO_RGB` in the code
- Or swap red/green values in your commands

---

## Quick Reference: Upload Methods Comparison

| Method | Pros | Cons | Best For |
|--------|------|------|----------|
| **Python Script** | ✅ Fully automated<br>✅ No GUI needed<br>✅ Handles all setup | ❌ Windows only<br>❌ Requires Python | Quick setup, automation |
| **Arduino IDE** | ✅ Visual interface<br>✅ Cross-platform<br>✅ Good for learning | ❌ Manual setup<br>❌ More steps | Learning, debugging, non-Windows |

---

## Next Steps

Once the firmware is uploaded and tested:

1. **Verify Serial Communication**:
   - Open Serial Monitor (115200 baud)
   - You should see "HELLO NEOPIXEL" message
   - Test commands work correctly

2. **Run the Main Application**:
   - The Python application will auto-detect the RP2040 via serial
   - Calibration will automatically control the NeoPixels
   - Use keyboard shortcuts (T, Q, W, E, U) to test LEDs from the application

3. **Troubleshooting**:
   - If the app can't find the RP2040, check the COM port in `config.yaml`
   - Make sure baud rate matches (115200)
   - Verify NeoPixels are wired correctly
