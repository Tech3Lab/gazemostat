# NeoPixel Troubleshooting Guide

If your NeoPixel LEDs are not lighting up, follow this troubleshooting guide to identify and fix the issue.

## Quick Diagnostic

Run the diagnostic script first:
```bash
python test_neopixels.py
```

This will test serial communication, send test commands, and help identify the problem.

## Common Issues and Solutions

### 1. Serial Communication Issues

#### Problem: Cannot find serial port / Port not detected

**Symptoms:**
- Error: "Could not auto-detect NeoPixel microcontroller"
- No COM ports listed
- Port not found error

**Solutions:**
1. **Check USB connection:**
   - Make sure RP2040 is connected via USB to your computer
   - Try a different USB cable
   - Try a different USB port
   - Unplug and replug the USB cable

2. **Check if port is in use:**
   - Close Arduino IDE Serial Monitor if open
   - Close any other programs using the serial port
   - On Linux: Check with `lsof /dev/ttyUSB0` (replace with your port)

3. **Manually specify port in config.yaml:**
   ```yaml
   neopixel_serial_port: "COM3"  # Windows
   # or
   neopixel_serial_port: "/dev/ttyUSB0"  # Linux
   ```

4. **Check Device Manager (Windows) or dmesg (Linux):**
   - Windows: Device Manager → Ports (COM & LPT)
   - Linux: `dmesg | tail` after plugging in USB

#### Problem: Permission denied / Access denied

**Symptoms:**
- Error: "Permission denied opening serial port"
- Error: "Access is denied"

**Solutions:**
1. **Close other programs using the port:**
   - Arduino IDE Serial Monitor
   - Other terminal programs
   - Previous instances of your application

2. **Check permissions (Linux):**
   ```bash
   # Add user to dialout group
   sudo usermod -a -G dialout $USER
   # Log out and log back in for changes to take effect
   ```

3. **Run with appropriate permissions:**
   - On Linux, you may need to run with `sudo` (not recommended, fix permissions instead)
   - On Windows, try running as Administrator

#### Problem: Wrong baud rate

**Symptoms:**
- Device doesn't respond
- Garbled messages
- No HELLO message received

**Solutions:**
1. **Check baud rate matches:**
   - Firmware uses: `115200` (defined in firmware.ino)
   - Config should match: `neopixel_serial_baud: 115200`
   - Both must be the same!

2. **Verify in firmware.ino:**
   ```cpp
   #define SERIAL_BAUD 115200
   ```

### 2. Firmware Issues

#### Problem: Firmware not uploaded

**Symptoms:**
- No HELLO message
- Device doesn't respond to commands
- Serial port opens but nothing happens

**Solutions:**
1. **Upload firmware to RP2040:**
   ```bash
   python upload_firmware.py
   ```
   Or use Arduino IDE (see RP2040_NEOPIXEL_FIRMWARE.md)

2. **Enter bootloader mode:**
   - Hold BOOTSEL button
   - Press and release RST button
   - Release BOOTSEL
   - Should see RPI-RP2 drive (Windows) or device in bootloader mode

3. **Verify firmware uploaded:**
   - Open Serial Monitor (115200 baud)
   - Should see "HELLO NEOPIXEL" messages on boot
   - If not, firmware didn't upload correctly

#### Problem: Wrong firmware configuration

**Symptoms:**
- Commands work but LEDs don't light up
- Wrong GPIO pin configured
- Wrong pixel count

**Solutions:**
1. **Check NEOPIXEL_PIN in firmware.ino:**
   ```cpp
   #define NEOPIXEL_PIN 1  // Should match your wiring (GP1)
   ```
   - Verify this matches where you connected NeoPixel DIN

2. **Check NEOPIXEL_COUNT:**
   ```cpp
   #define NEOPIXEL_COUNT 4  // Should match number of pixels
   ```
   - Must match actual number of NeoPixels in chain

3. **Re-upload firmware after changes:**
   - Any changes to firmware.ino require re-uploading

### 3. Hardware Wiring Issues

#### Problem: No power to NeoPixels

**Symptoms:**
- LEDs completely dark
- No response to any commands
- Serial communication works but LEDs don't light

**Solutions:**
1. **Check power connections:**
   - NeoPixel VCC → 5V power supply (NOT 3.3V!)
   - NeoPixel GND → Ground
   - Use multimeter to verify 5V at NeoPixel VCC pin

2. **Check power supply:**
   - NeoPixels need 5V power
   - Each pixel can draw up to 60mA at full brightness
   - 4 pixels at 30% brightness ≈ 72mA total
   - Make sure power supply can provide enough current

3. **Check for loose connections:**
   - Re-seat all connections
   - Check for cold solder joints
   - Verify wires are making good contact

#### Problem: Wrong data pin connection

**Symptoms:**
- Power is on but LEDs don't respond
- Serial commands work but no LED changes

**Solutions:**
1. **Verify data pin:**
   - NeoPixel DIN → RP2040 GPIO pin (e.g., GP1)
   - Check firmware.ino: `#define NEOPIXEL_PIN 1`
   - Must match your physical connection

2. **Check for loose data connection:**
   - Data wire must be securely connected
   - Try a different GPIO pin if current one doesn't work

3. **Check signal level:**
   - RP2040 GPIO is 3.3V
   - Most NeoPixels work with 3.3V data signals
   - If not working, may need level shifter (3.3V → 5V)

#### Problem: Ground not connected

**Symptoms:**
- Unpredictable behavior
- LEDs flicker or don't respond correctly
- Communication issues

**Solutions:**
1. **Verify common ground:**
   - RP2040 GND must connect to NeoPixel GND
   - Also connect to power supply ground
   - All grounds must be connected together

2. **Check ground connections:**
   - Use multimeter to verify continuity
   - Ensure good ground connection

#### Problem: Wrong pixel chain order

**Symptoms:**
- Only first pixel lights up
- Pixels light in wrong order
- Some pixels don't respond

**Solutions:**
1. **Verify chain connection:**
   - Pixel 1 DIN → RP2040 GPIO
   - Pixel 1 DOUT → Pixel 2 DIN
   - Pixel 2 DOUT → Pixel 3 DIN
   - Pixel 3 DOUT → Pixel 4 DIN
   - All VCC connected together
   - All GND connected together

2. **Check pixel orientation:**
   - DIN and DOUT are directional
   - Make sure data flows: RP2040 → Pixel 1 → Pixel 2 → Pixel 3 → Pixel 4

### 4. Software Configuration Issues

#### Problem: Brightness set to 0

**Symptoms:**
- LEDs appear off even when commands are sent
- Serial communication works

**Solutions:**
1. **Check brightness in config.yaml:**
   ```yaml
   neopixel_brightness: 0.3  # Should be > 0.0
   ```

2. **Test with higher brightness:**
   - Try setting to 1.0 (full brightness)
   - Or send command: `BRIGHTNESS:255`

3. **Check firmware brightness:**
   ```cpp
   uint8_t global_brightness = 76;  // 30% = 76/255
   ```

#### Problem: NeoPixel controller not initialized

**Symptoms:**
- Error: "NeoPixel controller not initialized"
- LEDs don't respond in application

**Solutions:**
1. **Check gpio_led_calibration_enable in config.yaml:**
   ```yaml
   gpio_led_calibration_enable: true
   ```

2. **Check application logs:**
   - Look for "NeoPixel controller initialized" message
   - Check for any error messages during startup

3. **Verify serial port detection:**
   - Application should find RP2040 automatically
   - Or specify port manually in config.yaml

### 5. Testing Steps

Follow these steps to systematically test your setup:

1. **Test Serial Communication:**
   ```bash
   python test_neopixels.py
   ```
   - Should detect port
   - Should receive HELLO message
   - Should be able to send commands

2. **Test Individual Commands:**
   - Open Serial Monitor (115200 baud)
   - Send: `INIT:4:76`
   - Send: `ALL:ON:255:255:255`
   - LEDs should turn white
   - Send: `ALL:OFF`
   - LEDs should turn off

3. **Test Individual Pixels:**
   - Send: `PIXEL:0:255:0:0` (red)
   - Send: `PIXEL:1:0:255:0` (green)
   - Send: `PIXEL:2:0:0:255` (blue)
   - Send: `PIXEL:3:255:255:0` (yellow)
   - Each pixel should light up in sequence

4. **Test Brightness:**
   - Send: `BRIGHTNESS:255`
   - Send: `ALL:ON:255:255:255`
   - LEDs should be very bright
   - Send: `BRIGHTNESS:50`
   - LEDs should be dimmer

### 6. Hardware Checklist

Before testing, verify:

- [ ] RP2040 is connected via USB
- [ ] RP2040 firmware is uploaded
- [ ] NeoPixel DIN connected to correct GPIO pin (GP1)
- [ ] NeoPixel VCC connected to 5V power
- [ ] NeoPixel GND connected to ground
- [ ] RP2040 GND connected to same ground
- [ ] Power supply provides 5V and enough current
- [ ] All pixels chained correctly (DIN → DOUT)
- [ ] All connections are secure
- [ ] No loose wires or cold solder joints

### 7. Still Not Working?

If none of the above solutions work:

1. **Check with multimeter:**
   - Measure voltage at NeoPixel VCC (should be ~5V)
   - Measure voltage at data pin (should be 0V or 3.3V when idle)
   - Check continuity of all connections

2. **Try different hardware:**
   - Try different NeoPixel LEDs
   - Try different GPIO pin
   - Try different power supply

3. **Check firmware code:**
   - Verify firmware.ino matches your hardware setup
   - Check for any compilation errors
   - Re-upload firmware

4. **Check application logs:**
   - Look for error messages in console output
   - Check if controller initializes successfully
   - Verify commands are being sent

5. **Test with Arduino IDE Serial Monitor:**
   - Open Serial Monitor (115200 baud)
   - Manually send commands
   - See if LEDs respond to direct commands

## Quick Reference: Command Format

Commands sent to RP2040 (newline-terminated):
- `INIT:<count>:<brightness>` - Initialize (e.g., `INIT:4:76`)
- `PIXEL:<idx>:<r>:<g>:<b>` - Set pixel color (e.g., `PIXEL:0:255:0:0`)
- `ALL:ON:<r>:<g>:<b>` - Turn all on (e.g., `ALL:ON:255:255:255`)
- `ALL:OFF` - Turn all off
- `BRIGHTNESS:<value>` - Set brightness 0-255 (e.g., `BRIGHTNESS:76`)

Responses from RP2040:
- `HELLO NEOPIXEL` - Boot message
- `ACK` - Command acknowledged
- `ERROR:<message>` - Error occurred

## Getting Help

If you're still having issues:
1. Run `python test_neopixels.py` and share the output
2. Check application console for error messages
3. Verify all hardware connections
4. Check firmware is uploaded correctly
5. Test with Serial Monitor manually
