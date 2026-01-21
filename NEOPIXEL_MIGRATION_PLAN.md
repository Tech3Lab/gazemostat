# NeoPixel Migration Plan

## Overview
This plan outlines the migration from 4 individual GPIO-controlled LEDs to 4 Adafruit Breadboard-friendly RGB Smart NeoPixel LEDs chained in series for calibration.

## Hardware Changes

### Current Setup
- 4 individual LEDs (LED+ to GPIO pins GP1-GP4, LED- through resistor to GND)
- Each LED controlled independently via separate GPIO lines
- Simple on/off control (binary: HIGH/LOW)

### New Setup
- 4 NeoPixel LEDs chained in series (data line daisy-chained)
- Single data pin connection (typically SPI or bit-banged protocol)
- RGB color control (24-bit color per pixel)
- Addressable: each pixel can be set independently with any color

### Hardware Wiring
- **Data Pin**: Connect to a single GPIO pin (e.g., GP1)
- **Power**: 5V power supply (NeoPixels require 5V, not 3.3V)
- **Ground**: Common ground connection
- **Chain**: DOUT of first pixel → DIN of second pixel → ... → DIN of fourth pixel
- **Note**: May need a level shifter if GPIO pin is 3.3V (NeoPixels expect 5V data signal)

## Software Changes Required

### 1. Configuration File (`config.yaml`)

#### Remove:
- `gpio_led_calibration_led1_pin`
- `gpio_led_calibration_led2_pin`
- `gpio_led_calibration_led3_pin`
- `gpio_led_calibration_led4_pin`

#### Add:
- `neopixel_data_pin`: GPIO pin number for NeoPixel data line (default: 1)
- `neopixel_count`: Number of NeoPixels in chain (default: 4)
- `neopixel_brightness`: Brightness level 0.0-1.0 (default: 0.3 for calibration visibility)
- `neopixel_color_order`: Color order string "RGB", "GRB", "RGBW", etc. (default: "GRB" for WS2812)
- `neopixel_frequency`: PWM frequency in Hz (default: 800000 for WS2812)
- `neopixel_dma_channel`: DMA channel for hardware timing (default: 5, Linux-specific)
- `neopixel_invert`: Invert signal (default: false)
- `neopixel_pixel_type`: Pixel type string (default: "WS2812" or "SK6812")

#### Update Documentation:
- Update comments explaining NeoPixel wiring instead of individual LED wiring
- Document power requirements (5V, adequate current capacity)
- Note about level shifter if needed

### 2. Dependencies (`requirements.txt`)

#### Add:
- `rpi-ws281x>=5.0.0` - NeoPixel library for Raspberry Pi/Linux SBCs (supports WS2812/SK6812)
  - Alternative: `adafruit-circuitpython-neopixel` if using CircuitPython
  - Note: `rpi-ws281x` requires root/sudo on some systems, or proper permissions

#### Consider:
- Platform detection: `rpi-ws281x` works on Linux SBCs, may need alternatives for Windows/other platforms
- Fallback: Pure Python bit-banging implementation for cross-platform support

### 3. Main Program (`main.py`)

#### Replace `GPIOLEDController` Class:

**Current Class Signature:**
```python
class GPIOLEDController:
    def __init__(self, gpio_chip="/dev/gpiochip0", led_pins=None)
    def start(self)
    def stop(self)
    def set_led(self, led_index)  # Turns on LED at index, others off
    def all_off(self)
    def all_on(self)
    def test_led(self, led_index, duration=2.0)
```

**New Class Signature:**
```python
class NeoPixelController:
    def __init__(self, data_pin=1, num_pixels=4, brightness=0.3, 
                 pixel_type="WS2812", color_order="GRB", frequency=800000,
                 dma_channel=5, invert=False)
    def start(self)  # Initialize NeoPixel strip
    def stop(self)  # Cleanup and turn off all pixels
    def set_led(self, led_index, color=(255, 255, 255))  # Set pixel at index to color
    def all_off(self)  # Turn off all pixels
    def all_on(self, color=(255, 255, 255))  # Turn on all pixels with color
    def set_color(self, led_index, r, g, b)  # Set specific RGB color
    def test_led(self, led_index, duration=2.0, color=(255, 255, 255))  # Test with color
    def set_brightness(self, brightness)  # Adjust brightness (0.0-1.0)
    def show(self)  # Update strip (if library requires explicit update)
```

**Implementation Details:**
- Use `rpi_ws281x` library: `from rpi_ws281x import PixelStrip, Color`
- Initialize `PixelStrip` with configuration parameters
- Map `set_led(led_index)` to set pixel at index to white (255, 255, 255) and others to (0, 0, 0)
- **REQUIRED**: Library must be available - raise error if import fails or initialization fails
- Support color customization per calibration point (optional enhancement)

#### Update Global Constants:
- Remove: `GPIO_LED_CALIBRATION_LED1_PIN`, `LED2_PIN`, `LED3_PIN`, `LED4_PIN`
- Add: `NEOPIXEL_DATA_PIN`, `NEOPIXEL_COUNT`, `NEOPIXEL_BRIGHTNESS`, etc.

#### Update Configuration Loading:
- Load NeoPixel configuration from `config.yaml`
- Maintain backward compatibility: if old LED pin config exists, log warning and use defaults

#### Update Initialization:
- Replace `GPIOLEDController` instantiation with `NeoPixelController`
- Pass NeoPixel configuration parameters
- **REQUIRED**: Raise error if library import fails or initialization fails (no fallback)
- Application should exit with clear error message if NeoPixel hardware cannot be initialized

#### Update Calibration Code:
- No changes needed to calibration sequence logic
- `set_led(led_index)` calls will work the same way
- Consider using different colors for each corner (optional enhancement):
  - LED 0 (top-left): Red (255, 0, 0)
  - LED 1 (top-right): Green (0, 255, 0)
  - LED 2 (bottom-right): Blue (0, 0, 255)
  - LED 3 (bottom-left): Yellow (255, 255, 0)

#### Update LED Testing Shortcuts:
- Keep Q/W/E/U keys for testing individual LEDs
- Keep T key for testing all LEDs
- Update to show colors in simulation mode

### 4. Simulation/Display Updates

#### On-Screen LED Display:
- Current: Green circle when active, gray when inactive
- Update: Show RGB colors matching NeoPixel colors
  - Use actual pixel colors if color customization is implemented
  - Or use white for active, black for inactive (simpler)

#### Visual Feedback:
- Consider adding color preview in simulation mode
- Show brightness level in debug messages

### 5. Error Handling

#### Add Checks For:
- NeoPixel library availability (`rpi_ws281x` import) - **REQUIRED, raise error if missing**
- Root/sudo permissions (some systems require this) - **REQUIRED, raise error if insufficient**
- GPIO pin availability and permissions - **REQUIRED, raise error if unavailable**
- Power supply adequacy (warn if brightness too high)
- Library initialization failures - **REQUIRED, raise error and exit**

#### Error Behavior:
- If NeoPixel library cannot be imported:
  - Raise `ImportError` with clear message: "rpi-ws281x library is required but not installed. Install with: pip install rpi-ws281x"
  - Application should exit immediately
- If NeoPixel initialization fails:
  - Raise `RuntimeError` with clear message describing the failure (permissions, pin unavailable, etc.)
  - Application should exit immediately
- **NO FALLBACK**: Application requires NeoPixel hardware to function

### 6. Documentation Updates

#### Update `plan.md`:
- Update hardware section to describe NeoPixel setup
- Update wiring diagrams
- Update GPIO pin usage (single pin instead of 4)

#### Update `INSTALL_WINDOWS.md` (if applicable):
- Note that NeoPixels may require different setup on Windows
- May need alternative library or USB-to-serial bridge

#### Create/Update Hardware Setup Guide:
- NeoPixel wiring instructions
- Power supply requirements (5V, current capacity)
- Level shifter requirements (if GPIO is 3.3V)
- Chain connection diagram

## Implementation Steps

### Phase 1: Dependencies and Configuration
1. Add `rpi-ws281x` to `requirements.txt`
2. Update `config.yaml` with NeoPixel settings
3. Remove old LED pin configuration from `config.yaml`
4. Update configuration loading code in `main.py`

### Phase 2: Core Controller Implementation
1. Create new `NeoPixelController` class
2. Implement initialization (`start()` method)
3. Implement basic control methods (`set_led()`, `all_off()`, `all_on()`)
4. Implement cleanup (`stop()` method)
5. Add error handling - raise errors on failure (no fallback)

### Phase 3: Integration
1. Replace `GPIOLEDController` instantiation with `NeoPixelController`
2. Update all `led_controller` method calls (should be compatible)
3. Test calibration sequence with NeoPixels
4. Update LED testing keyboard shortcuts

### Phase 4: Simulation Updates
1. Update on-screen LED display to show colors
2. Update debug messages
3. Test simulation mode

### Phase 5: Testing and Validation
1. Test on hardware with real NeoPixels
2. Verify calibration sequence works correctly
3. Test all LED control methods
4. Verify power consumption and brightness
5. Test error handling - verify application exits with clear errors when library missing or initialization fails

### Phase 6: Documentation
1. Update `config.yaml` comments
2. Update `plan.md`
3. Create/update hardware setup guide
4. Update any installation instructions

## Optional Enhancements

### Color Customization
- Allow different colors for each calibration point
- Configurable colors in `config.yaml`
- Visual distinction between calibration points

### Brightness Control
- Dynamic brightness adjustment
- Auto-brightness based on ambient light (if sensor available)
- Brightness fade-in/fade-out effects

### Animation Effects
- Smooth color transitions
- Pulsing effect during calibration
- Success animation after calibration

### Power Management
- Auto-reduce brightness if power issues detected
- Power consumption monitoring
- Low-power mode when not in use

## Compatibility Considerations

### Backward Compatibility
- Remove old `GPIOLEDController` class entirely
- No fallback to old hardware - NeoPixels are required
- Configuration should not support old LED pin settings

### Cross-Platform Support
- `rpi-ws281x` is Linux-specific
- Application requires Linux platform with NeoPixel hardware
- No cross-platform fallback - application will exit with error on unsupported platforms

### Permission Requirements
- Some NeoPixel libraries require root/sudo
- Document permission setup
- Consider udev rules for non-root access

## Testing Checklist

- [ ] NeoPixel library installs correctly
- [ ] Configuration loads from `config.yaml`
- [ ] Controller initializes successfully
- [ ] Individual pixel control works (`set_led()`)
- [ ] All pixels can be turned off (`all_off()`)
- [ ] All pixels can be turned on (`all_on()`)
- [ ] Calibration sequence activates correct pixels
- [ ] Simulation mode displays LEDs correctly
- [ ] Error handling works (application exits with clear error when library missing, permissions insufficient, etc.)
- [ ] Cleanup works correctly (`stop()` method)
- [ ] Power consumption is acceptable
- [ ] Brightness is appropriate for calibration
- [ ] Documentation is updated

## Risk Assessment

### Low Risk
- Configuration file updates
- Simulation display updates
- Documentation updates

### Medium Risk
- NeoPixel library integration
- Hardware initialization
- Permission/access issues

### High Risk
- Power supply adequacy (NeoPixels can draw significant current)
- Timing-sensitive protocol (may need hardware PWM/SPI)
- Level shifting requirements (3.3V GPIO to 5V NeoPixel data)

## Notes

- NeoPixels require precise timing for the data protocol
- Hardware PWM or SPI is preferred over bit-banging for reliability
- Power supply must provide adequate current (each pixel can draw up to 60mA at full brightness)
- Consider adding a capacitor (1000µF) near the NeoPixel power connection for stability
- For 4 pixels at 30% brightness: ~72mA total current (4 × 60mA × 0.3)
- Level shifter may be needed if GPIO pin outputs 3.3V (NeoPixels expect 5V data signal, though many work with 3.3V)
