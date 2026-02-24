// RP2040 Co-Processor Firmware for LattePanda Iota
// - NeoPixel controller (WS2812/SK6812)
// - OLED controller/test for Adafruit SSD1327 (128x128 over I2C)
//   with legacy SSD1306 (128x64) integrity test support.
//
// Serial protocol (line-based):
//   - PING / HELLO -> replies with HELLO messages
//   - NeoPixels:
//       INIT:<count>:<brightness>
//       PIXEL:<idx>:<r>:<g>:<b>
//       ONE:<idx>:<r>:<g>:<b>   (atomic: clears others, sets one, single show)
//       ALL:ON:<r>:<g>:<b>
//       ALL:OFF
//       BRIGHTNESS:<value>
//   - OLED:
//       OLED:INIT
//       OLED:TEST

#include <Adafruit_NeoPixel.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1327.h>
#include <Adafruit_SSD1306.h>
#include "ui/v5/generated_screens.h"

// Configuration - CHANGE THESE TO MATCH YOUR SETUP
#define NEOPIXEL_PIN    1       // GPIO pin connected to NeoPixel DIN (GP1)
#define NEOPIXEL_COUNT  4       // Number of NeoPixels in chain
#define SERIAL_BAUD     230400  // Serial communication baud rate

// OLED over I2C (STEMMA QT / Qwiic)
// User wiring:
//   SDA = GP4 (blue)
//   SCL = GP5 (yellow)
#define OLED_SDA_PIN 4
#define OLED_SCL_PIN 5
#define OLED1327_WIDTH   128
#define OLED1327_HEIGHT  128
#define OLED1306_WIDTH   128
#define OLED1306_HEIGHT  64
#define OLED_ADDR_PRIMARY   0x3D
#define OLED_ADDR_FALLBACK  0x3C

// OLED Bonnet joystick + buttons (GPIO)
//
// IMPORTANT:
// - The Bonnet's joystick + A/B buttons are typically simple switches to GND.
// - To read them on RP2040, you must wire each button signal to an RP2040 GPIO.
// - These defaults assume you wired them to GP6..GP12. Adjust to match your wiring.
// - We use INPUT_PULLUP, so "pressed" reads LOW.
#define BTN_UP_PIN      6
#define BTN_DOWN_PIN    7
#define BTN_LEFT_PIN    8
#define BTN_RIGHT_PIN   9
#define BTN_CENTER_PIN  10
#define BTN_A_PIN       11
#define BTN_B_PIN       12

// Create NeoPixel object
Adafruit_NeoPixel strip(NEOPIXEL_COUNT, NEOPIXEL_PIN, NEO_GRB + NEO_KHZ800);

// OLED objects (I2C, no reset pin)
Adafruit_SSD1327 display1327(OLED1327_WIDTH, OLED1327_HEIGHT, &Wire, -1);
Adafruit_SSD1306 display1306(OLED1306_WIDTH, OLED1306_HEIGHT, &Wire, -1);

// Global brightness (0-255)
uint8_t global_brightness = 64;  // Default: ~25% (64/255)

// OLED state
bool oled_available = false;
uint8_t oled_addr = OLED_ADDR_PRIMARY;
bool oled_input_feedback_enabled = false;  // Disabled - using UI instead
enum class OledModel : uint8_t {
  NONE = 0,
  SSD1327_128X128 = 1,
  SSD1306_128X64 = 2,
};
OledModel oled_model = OledModel::NONE;

// Button state (bitmask)
// bit0..bit6 = UP,DOWN,LEFT,RIGHT,CENTER,A,B
uint8_t buttons_prev = 0;
unsigned long last_button_poll_ms = 0;
const unsigned long BUTTON_POLL_MS = 20;  // 50 Hz button polling
// OLED full-frame refresh is expensive over I2C. Keep it responsive but avoid starving serial RX/HB.
const unsigned long UI_REFRESH_MS = 100;  // 10 Hz UI refresh
unsigned long last_ui_refresh_ms = 0;

// UI screen state (CPU is the source of truth; firmware only renders).
UiScreen ui_current_screen = UiScreen::BOOT;
bool ui_dirty = true;

// Backward-compatible state variables (used only by OLED:UI:STATE).
bool ui_gp_connected_state = false;
bool ui_gp_gaze_data_state = false;
uint8_t ui_gaze_x_compat = 128;  // Host sends 0..255
uint8_t ui_gaze_y_compat = 128;  // Host sends 0..255

// Track if we've sent initial HELLO messages and when to stop
unsigned long boot_time;
bool serial_connected = false;
const unsigned long HELLO_PERIOD_MS = 5000;  // Send HELLO for 5 seconds after boot
const unsigned long HELLO_INTERVAL_MS = 1000;  // Lower chatter during boot window

// RP2040 boot/reset detection + heartbeat (every 3 seconds).
// BOOT:<boot_id>:<uptime_s> until host ACKs, then HB:<boot_id>:<uptime_s>.
static uint32_t boot_id = 0;
static bool boot_acked = false;
static unsigned long last_hb_ms = 0;
static const unsigned long HB_PERIOD_MS = 3000;

static uint32_t genBootId() {
  // Simple "random-ish" ID that should change across resets.
  return (uint32_t)(micros() ^ (millis() << 1) ^ 0xA5A5A5A5UL);
}

static uint8_t readButtons() {
  uint8_t s = 0;
  if (digitalRead(BTN_UP_PIN) == LOW) s |= (1 << 0);
  if (digitalRead(BTN_DOWN_PIN) == LOW) s |= (1 << 1);
  if (digitalRead(BTN_LEFT_PIN) == LOW) s |= (1 << 2);
  if (digitalRead(BTN_RIGHT_PIN) == LOW) s |= (1 << 3);
  if (digitalRead(BTN_CENTER_PIN) == LOW) s |= (1 << 4);
  if (digitalRead(BTN_A_PIN) == LOW) s |= (1 << 5);
  if (digitalRead(BTN_B_PIN) == LOW) s |= (1 << 6);
  return s;
}

static const char *buttonNameFromBit(uint8_t button_bit) {
  switch (button_bit) {
    case 0: return "BTN_UP";
    case 1: return "BTN_DOWN";
    case 2: return "BTN_LEFT";
    case 3: return "BTN_RIGHT";
    case 4: return "BTN_CENTER";
    case 5: return "BTN_A";
    case 6: return "BTN_B";
    default: return "BTN_CENTER";
  }
}

static void update_ui_dynamic_elements() {
  // Legacy no-op: modern host flow uses OLED:UI:SET:* for dynamic variables.
  // OLED:UI:STATE remains supported and updates variables in its command handler.
}

static void renderUi() {
  if (!oled_available || oled_model != OledModel::SSD1327_128X128) return;
  update_ui_dynamic_elements();
  draw_screen(display1327, ui_current_screen);
  display1327.display();
  ui_dirty = false;
}

static void renderButtonFeedback(uint8_t buttons) {
  // Legacy function - kept for compatibility but not used when UI is active
  if (!oled_available || !oled_input_feedback_enabled) return;
  // Implementation removed - UI handles display now
}

static void pollButtonsAndUpdateDisplay() {
  if (!oled_available) return;
  unsigned long now = millis();
  // 1) Poll buttons at 50 Hz (edges only).
  if (now - last_button_poll_ms >= BUTTON_POLL_MS) {
    last_button_poll_ms = now;

    uint8_t cur = readButtons();
    uint8_t changed = cur ^ buttons_prev;

    if (changed != 0) {
      // Emit press/release edges to the CPU (needed for BTN_B hold-to-monitor).
      for (uint8_t i = 0; i < 7; i++) {
        uint8_t mask = (1 << i);
        if (changed & mask) {
          bool prevPressed = (buttons_prev & mask) != 0;
          bool curPressed = (cur & mask) != 0;
          if (!prevPressed && curPressed) {
            Serial.print("BTN:PRESS:");
            Serial.println(buttonNameFromBit(i));
          } else if (prevPressed && !curPressed) {
            Serial.print("BTN:RELEASE:");
            Serial.println(buttonNameFromBit(i));
          }
        }
      }

      buttons_prev = cur;
    }
  }

  // 2) Refresh OLED UI at a throttled rate only when content changed.
  if (ui_dirty && (now - last_ui_refresh_ms >= UI_REFRESH_MS)) {
    last_ui_refresh_ms = now;
    renderUi();
  }
}

static bool parseBool01(const String &s, bool &out) {
  if (s.length() == 0) return false;
  String t = s;
  t.trim();
  t.toUpperCase();
  if (t == "1" || t == "ON" || t == "TRUE") { out = true; return true; }
  if (t == "0" || t == "OFF" || t == "FALSE") { out = false; return true; }
  return false;
}

static UiScreen screenFromString(String name, bool &ok) {
  ok = true;
  name.trim();
  name.toUpperCase();
  if (name == "LOADING") return UiScreen::LOADING;
  if (name == "BOOT") return UiScreen::BOOT;
  if (name == "FIND_POSITION") return UiScreen::FIND_POSITION;
  if (name == "MOVE_CLOSER") return UiScreen::MOVE_CLOSER;
  if (name == "MOVE_FARTHER") return UiScreen::MOVE_FARTHER;
  if (name == "IN_POSITION") return UiScreen::IN_POSITION;
  if (name == "CALIBRATION") return UiScreen::CALIBRATION;
  if (name == "RECORD_CONFIRMATION") return UiScreen::RECORD_CONFIRMATION;
  if (name == "RECORDING") return UiScreen::RECORDING;
  if (name == "STOP_RECORD") return UiScreen::STOP_RECORD;
  if (name == "INFERENCE_LOADING") return UiScreen::INFERENCE_LOADING;
  if (name == "RESULTS") return UiScreen::RESULTS;
  if (name == "MONITORING") return UiScreen::MONITORING;
  ok = false;
  return UiScreen::BOOT;
}

static bool dynamicVarFromString(String varName, UiDynamicVar &out) {
  varName.trim();
  varName.toLowerCase();
  // v3 generated vars
  if (varName == "ui_loading_data") { out = UiDynamicVar::UI_LOADING_DATA; return true; }
  if (varName == "ui_gp_connected" || varName == "ui_tracker_detected") {
    out = UiDynamicVar::UI_GP_CONNECTED;
    return true;
  }
  if (varName == "ui_gp_gaze_data" || varName == "ui_led_detected" || varName == "ui_connection") {
    out = UiDynamicVar::UI_GP_GAZE_DATA;
    return true;
  }
  if (varName == "ui_position_head") { out = UiDynamicVar::UI_POSITION_HEAD; return true; }
  if (varName == "ui_calib_next_btn") { out = UiDynamicVar::UI_CALIB_NEXT_BTN; return true; }
  if (varName == "ui_calib_redo_btn") { out = UiDynamicVar::UI_CALIB_REDO_BTN; return true; }
  if (varName == "ui_calib_result") { out = UiDynamicVar::UI_CALIB_RESULT; return true; }
  if (varName == "ui_led_up_left") { out = UiDynamicVar::UI_LED_UP_LEFT; return true; }
  if (varName == "ui_led_up_right") { out = UiDynamicVar::UI_LED_UP_RIGHT; return true; }
  if (varName == "ui_led_bottom_left") { out = UiDynamicVar::UI_LED_BOTTOM_LEFT; return true; }
  if (varName == "ui_led_bottom_right") { out = UiDynamicVar::UI_LED_BOTTOM_RIGHT; return true; }
  if (varName == "ui_recording_timer") { out = UiDynamicVar::UI_RECORDING_TIMER; return true; }
  if (varName == "ui_event_time") { out = UiDynamicVar::UI_EVENT_TIME; return true; }
  if (varName == "ui_event_name") { out = UiDynamicVar::UI_EVENT_NAME; return true; }
  if (varName == "ui_closed_event_warning" || varName == "ui_close_event_warning") { out = UiDynamicVar::UI_CLOSE_EVENT_WARNING; return true; }
  if (varName == "ui_inference_timer") { out = UiDynamicVar::UI_INFERENCE_TIMER; return true; }
  if (varName == "ui_inference_prog_bar") { out = UiDynamicVar::UI_INFERENCE_PROG_BAR; return true; }
  if (varName == "ui_results_title") { out = UiDynamicVar::UI_RESULTS_TITLE; return true; }
  if (varName == "ui_results_next_btn") { out = UiDynamicVar::UI_RESULTS_NEXT_BTN; return true; }
  if (varName == "ui_results_prev_btn") { out = UiDynamicVar::UI_RESULTS_PREV_BTN; return true; }
  if (varName == "ui_result_1") { out = UiDynamicVar::UI_RESULT_1; return true; }
  if (varName == "ui_result_2") { out = UiDynamicVar::UI_RESULT_2; return true; }
  if (varName == "ui_result_3") { out = UiDynamicVar::UI_RESULT_3; return true; }
  if (varName == "ui_result_4") { out = UiDynamicVar::UI_RESULT_4; return true; }
  if (varName == "ui_left_eye") { out = UiDynamicVar::UI_LEFT_EYE; return true; }
  if (varName == "ui_right_eye") { out = UiDynamicVar::UI_RIGHT_EYE; return true; }
  if (varName == "ui_gaze_point") { out = UiDynamicVar::UI_GAZE_POINT; return true; }
  if (varName == "ui_position_status" || varName == "ui_text_el_269") { out = UiDynamicVar::UI_TEXT_EL_269; return true; }
  return false;
}

static int16_t mapU8ToRange(uint8_t value, int16_t max_inclusive) {
  // Integer mapping: 0..255 -> 0..max_inclusive
  return (int16_t)((uint32_t(value) * uint32_t(max_inclusive)) / 255U);
}

static bool i2cProbe(uint8_t addr) {
  Wire.beginTransmission(addr);
  uint8_t err = Wire.endTransmission();
  return err == 0;
}

static void oledI2cInit() {
  Wire.setSDA(OLED_SDA_PIN);
  Wire.setSCL(OLED_SCL_PIN);
  Wire.begin();
}

static const char *oledModelName(OledModel model) {
  switch (model) {
    case OledModel::SSD1327_128X128: return "SSD1327";
    case OledModel::SSD1306_128X64: return "SSD1306";
    default: return "NONE";
  }
}

static bool findOledAddress(uint8_t &addr_out) {
  const uint8_t candidates[] = {OLED_ADDR_PRIMARY, OLED_ADDR_FALLBACK};
  for (uint8_t i = 0; i < (sizeof(candidates) / sizeof(candidates[0])); i++) {
    if (i2cProbe(candidates[i])) {
      addr_out = candidates[i];
      return true;
    }
  }
  return false;
}

static bool initSsd1327UiAt(uint8_t addr, bool showReadyScreen) {
  if (!display1327.begin(addr)) {
    return false;
  }

  if (showReadyScreen) {
    display1327.clearDisplay();
    display1327.setTextSize(1);
    display1327.setTextColor(SSD1327_WHITE);
    display1327.setCursor(0, 0);
    display1327.println("OLED READY");
    display1327.println("MODEL SSD1327");
    display1327.print("ADDR 0x");
    display1327.println(addr, HEX);
    display1327.display();
  }

  oled_addr = addr;
  oled_model = OledModel::SSD1327_128X128;
  oled_available = true;
  return true;
}

static bool initSsd1306At(uint8_t addr, bool showReadyScreen) {
  if (!display1306.begin(SSD1306_SWITCHCAPVCC, addr)) {
    return false;
  }

  if (showReadyScreen) {
    display1306.clearDisplay();
    display1306.setTextSize(1);
    display1306.setTextColor(SSD1306_WHITE);
    display1306.setCursor(0, 0);
    display1306.println("OLED READY");
    display1306.println("MODEL SSD1306");
    display1306.print("ADDR 0x");
    display1306.println(addr, HEX);
    display1306.display();
  }

  oled_addr = addr;
  oled_model = OledModel::SSD1306_128X64;
  oled_available = true;
  return true;
}

static bool oledInit() {
  oledI2cInit();

  oled_available = false;
  oled_model = OledModel::NONE;

  // Try addresses in priority order: 0x3D first, then 0x3C.
  const uint8_t candidates[] = {OLED_ADDR_PRIMARY, OLED_ADDR_FALLBACK};
  for (uint8_t i = 0; i < (sizeof(candidates) / sizeof(candidates[0])); i++) {
    const uint8_t addr = candidates[i];
    if (!i2cProbe(addr)) continue;

    // Primary runtime display/UI target.
    if (initSsd1327UiAt(addr, true)) {
      return true;
    }
    // Legacy fallback detection path.
    if (initSsd1306At(addr, true)) {
      return true;
    }
  }

  oled_available = false;
  oled_model = OledModel::NONE;
  return false;
}

static bool oledIntegrityTestSsd1327(String &failReason, uint8_t addr) {
  if (!display1327.begin(addr)) {
    failReason = "SSD1327 init failed";
    return false;
  }

  Serial.println("OLED:TEST:START:SSD1327:128x128");
  Serial.print("OLED:ADDR:0x");
  Serial.println(addr, HEX);

  // Frame 1: Border + text.
  display1327.clearDisplay();
  display1327.drawRect(0, 0, OLED1327_WIDTH, OLED1327_HEIGHT, SSD1327_WHITE);
  display1327.setTextSize(1);
  display1327.setTextColor(SSD1327_WHITE);
  display1327.setCursor(10, 16);
  display1327.println("SSD1327 INTEGRITY");
  display1327.setCursor(10, 30);
  display1327.println("TEST RUNNING...");
  display1327.setCursor(10, 44);
  display1327.print("SDA GP");
  display1327.print(OLED_SDA_PIN);
  display1327.print(" SCL GP");
  display1327.println(OLED_SCL_PIN);
  display1327.display();
  delay(700);

  // Frame 2: 4-bit grayscale checkerboard.
  display1327.clearDisplay();
  for (int y = 0; y < OLED1327_HEIGHT; y += 8) {
    for (int x = 0; x < OLED1327_WIDTH; x += 8) {
      const bool even = (((x + y) / 8) % 2) == 0;
      display1327.fillRect(x, y, 8, 8, even ? SSD1327_WHITE : 0x7);
    }
  }
  display1327.display();
  delay(600);

  // Frame 3: Invert toggle.
  display1327.invertDisplay(true);
  delay(250);
  display1327.invertDisplay(false);
  delay(250);

  // Frame 4: Clear and show OK.
  display1327.clearDisplay();
  display1327.setTextSize(2);
  display1327.setTextColor(SSD1327_WHITE);
  display1327.setCursor(18, 48);
  display1327.println("OLED OK");
  display1327.setTextSize(1);
  display1327.setCursor(0, 116);
  display1327.print("ADDR 0x");
  display1327.print(addr, HEX);
  display1327.display();

  if (!i2cProbe(addr)) {
    failReason = "Device stopped ACKing";
    Serial.println("OLED:TEST:FAIL:I2C_NACK");
    return false;
  }

  Serial.println("OLED:TEST:OK:SSD1327");
  return true;
}

static bool oledIntegrityTestSsd1306(String &failReason, uint8_t addr) {
  if (!display1306.begin(SSD1306_SWITCHCAPVCC, addr)) {
    failReason = "SSD1306 init failed";
    return false;
  }

  Serial.println("OLED:TEST:START:SSD1306:128x64");
  Serial.print("OLED:ADDR:0x");
  Serial.println(addr, HEX);

  // Frame 1: Border + text.
  display1306.clearDisplay();
  display1306.drawRect(0, 0, OLED1306_WIDTH, OLED1306_HEIGHT, SSD1306_WHITE);
  display1306.setCursor(8, 10);
  display1306.setTextSize(1);
  display1306.println("SSD1306 INTEGRITY");
  display1306.setCursor(8, 24);
  display1306.println("TEST RUNNING...");
  display1306.setCursor(8, 38);
  display1306.print("SDA GP");
  display1306.print(OLED_SDA_PIN);
  display1306.print(" SCL GP");
  display1306.println(OLED_SCL_PIN);
  display1306.display();
  delay(700);

  // Frame 2: Checkerboard.
  display1306.clearDisplay();
  for (int y = 0; y < OLED1306_HEIGHT; y += 8) {
    for (int x = 0; x < OLED1306_WIDTH; x += 8) {
      if ((((x + y) / 8) % 2) == 0) {
        display1306.fillRect(x, y, 8, 8, SSD1306_WHITE);
      }
    }
  }
  display1306.display();
  delay(600);

  // Frame 3: Invert toggle.
  display1306.invertDisplay(true);
  delay(250);
  display1306.invertDisplay(false);
  delay(250);

  // Frame 4: Clear and show OK.
  display1306.clearDisplay();
  display1306.setTextSize(2);
  display1306.setCursor(18, 18);
  display1306.println("OLED OK");
  display1306.setTextSize(1);
  display1306.setCursor(0, 52);
  display1306.print("ADDR 0x");
  display1306.print(addr, HEX);
  display1306.display();

  if (!i2cProbe(addr)) {
    failReason = "Device stopped ACKing";
    Serial.println("OLED:TEST:FAIL:I2C_NACK");
    return false;
  }

  Serial.println("OLED:TEST:OK:SSD1306");
  return true;
}

static bool oledIntegrityTestAuto(String &failReason) {
  if (!oled_available) {
    if (!oledInit()) {
      failReason = "I2C device not found / init failed";
      return false;
    }
  }

  if (oled_model == OledModel::SSD1327_128X128) {
    return oledIntegrityTestSsd1327(failReason, oled_addr);
  }
  if (oled_model == OledModel::SSD1306_128X64) {
    return oledIntegrityTestSsd1306(failReason, oled_addr);
  }

  failReason = "No OLED model active";
  return false;
}

static bool oledIntegrityTestForTarget(String target, String &failReason) {
  oledI2cInit();
  target.trim();
  target.toUpperCase();

  if (target.length() == 0 || target == "AUTO") {
    return oledIntegrityTestAuto(failReason);
  }

  uint8_t addr = 0;
  if (!findOledAddress(addr)) {
    failReason = "I2C device not found";
    return false;
  }

  if (target == "SSD1327" || target == "1327" || target == "128X128") {
    return oledIntegrityTestSsd1327(failReason, addr);
  }
  if (target == "SSD1306" || target == "1306" || target == "128X64") {
    return oledIntegrityTestSsd1306(failReason, addr);
  }

  failReason = "Unknown OLED test target";
  return false;
}

void setup() {
  boot_time = millis();
  boot_id = genBootId();
  boot_acked = false;
  last_hb_ms = 0;
  // Initialize serial communication
  Serial.begin(SERIAL_BAUD);

  // Configure button GPIOs
  pinMode(BTN_UP_PIN, INPUT_PULLUP);
  pinMode(BTN_DOWN_PIN, INPUT_PULLUP);
  pinMode(BTN_LEFT_PIN, INPUT_PULLUP);
  pinMode(BTN_RIGHT_PIN, INPUT_PULLUP);
  pinMode(BTN_CENTER_PIN, INPUT_PULLUP);
  pinMode(BTN_A_PIN, INPUT_PULLUP);
  pinMode(BTN_B_PIN, INPUT_PULLUP);
  
  // Initialize NeoPixel strip (don't wait for Serial on RP2040)
  strip.begin();
  strip.setBrightness(global_brightness);
  strip.show(); // Initialize all pixels to 'off'

  // Initialize OLED (non-fatal if missing)
  oledInit();
  if (oled_available) {
    // Initialize UI state (CPU will override screen shortly after boot)
    buttons_prev = readButtons();
    ui_current_screen = UiScreen::BOOT;
    renderUi();
  }
  
  // Wait a bit for serial to be ready, but don't block forever
  // On RP2040, Serial might not be available immediately
  unsigned long start = millis();
  while (!Serial && (millis() - start < 2000)) {
    delay(10);
  }
  
  // Additional delay to ensure serial is fully ready
  delay(200);
  
  // Send hello message for auto-detection (send multiple times for reliability)
  // IMPORTANT: don't guard on `if (Serial)` here; on some hosts the Serial "connected"
  // flag/DTR may stay false even though RX/TX works (you'll still get ACKs).
  for (int i = 0; i < 5; i++) {
    Serial.println("HELLO NEOPIXEL");
    Serial.println("HELLO OLED");
    delay(100);
  }
}

void loop() {
  // Poll buttons and update UI display
  pollButtonsAndUpdateDisplay();

  // BOOT announce until ACK, then HB, every 3 seconds.
  unsigned long now_ms = millis();
  if (now_ms - last_hb_ms >= HB_PERIOD_MS) {
    last_hb_ms = now_ms;
    uint32_t uptime_s = (uint32_t)(now_ms / 1000UL);
    if (!boot_acked) {
      Serial.print("BOOT:");
      Serial.print(boot_id);
      Serial.print(":");
      Serial.println(uptime_s);
    } else {
      Serial.print("HB:");
      Serial.print(boot_id);
      Serial.print(":");
      Serial.println(uptime_s);
    }
  }

  // Send HELLO messages periodically for first few seconds after boot
  // This helps with auto-detection even if serial wasn't ready during setup()
  unsigned long elapsed = millis() - boot_time;
  if (elapsed < HELLO_PERIOD_MS) {
    // Send HELLO periodically during the first seconds after boot.
    static unsigned long last_hello = 0;
    if (millis() - last_hello >= HELLO_INTERVAL_MS) {
      Serial.println("HELLO NEOPIXEL");
      Serial.println("HELLO OLED");
      serial_connected = true;
      last_hello = millis();
    }
  } else if (!serial_connected) {
    // Send one more HELLO when serial first becomes available after boot period
    Serial.println("HELLO NEOPIXEL");
    Serial.println("HELLO OLED");
    serial_connected = true;
  }
  
  // Check for incoming serial commands (non-blocking, drains all pending RX).
  // Avoids readStringUntil() blocking and reduces risk of serial backlog starving HB.
  static char rx_line[256];
  static size_t rx_len = 0;

  while (Serial.available() > 0) {
    // Mark serial as connected when we receive data
    if (!serial_connected) {
      serial_connected = true;
      // Send HELLO when we first detect serial activity
      Serial.println("HELLO NEOPIXEL");
    }

    int b = Serial.read();
    if (b < 0) break;
    char c = (char)b;

    if (c == '\r') continue;
    if (c == '\n') {
      rx_line[rx_len] = '\0';
      if (rx_len > 0) {
        String command = String(rx_line);
        command.trim();
        if (command.length() > 0) {
          processCommand(command);
        }
      }
      rx_len = 0;
      continue;
    }

    // Accumulate, but if a sender floods without newlines or sends a too-long line,
    // drop it to keep the firmware responsive.
    if (rx_len < (sizeof(rx_line) - 1)) {
      rx_line[rx_len++] = c;
    } else {
      rx_len = 0;  // overflow: drop current line
    }
  }
}

void processCommand(String cmd) {
  // BOOT ACK from host: ACK:BOOT:<boot_id>
  if (cmd.startsWith("ACK:BOOT:")) {
    String idStr = cmd.substring(String("ACK:BOOT:").length());
    idStr.trim();
    uint32_t id = (uint32_t)idStr.toInt();
    if (id != 0 && id == boot_id) {
      boot_acked = true;
    }
    return;
  }

  // Handle special commands first
  if (cmd == "PING" || cmd == "HELLO") {
    // Respond to ping/hello for connection testing
    Serial.println("HELLO NEOPIXEL");
    Serial.println("HELLO OLED");
    return;
  }
  
  // Parse command format: COMMAND:param1:param2:...
  int firstColon = cmd.indexOf(':');
  if (firstColon < 0) {
    // No parameters - no commands without colons currently supported
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
    
  } else if (command == "ONE") {
    // ONE:<idx>:<r>:<g>:<b>
    // Atomic single-LED update: clear all and light only one LED in one show().
    int idx = getParam(params, 0).toInt();
    int r = getParam(params, 1).toInt();
    int g = getParam(params, 2).toInt();
    int b = getParam(params, 3).toInt();

    if (idx >= 0 && idx < NEOPIXEL_COUNT &&
        r >= 0 && r <= 255 && g >= 0 && g <= 255 && b >= 0 && b <= 255) {
      for (int i = 0; i < NEOPIXEL_COUNT; i++) {
        strip.setPixelColor(i, 0);
      }
      strip.setPixelColor(idx, strip.Color(r, g, b));
      strip.show();
      Serial.println("ACK");
    } else {
      Serial.println("ERROR:Invalid parameters");
    }

  } else if (command == "ALL") {
    // ALL:ON:<r>:<g>:<b> or ALL:OFF
    if (params == "OFF") {
      allOff();
      Serial.println("ACK");
    } else if (params.startsWith("ON:")) {
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
    
  } else if (command == "OLED") {
    // OLED:INIT or OLED:TEST[:SSD1327|SSD1306|AUTO]
    String sub = getParam(params, 0);
    sub.toUpperCase();

    if (sub == "INIT") {
      if (oledInit()) {
        Serial.print("OLED:OK:ADDR:0x");
        Serial.println(oled_addr, HEX);
        Serial.print("OLED:MODEL:");
        Serial.println(oledModelName(oled_model));
      } else {
        Serial.println("OLED:FAIL:NOT_FOUND");
      }
      return;
    }

    if (sub == "TEST") {
      String target = getParam(params, 1);
      String reason = "";
      bool ok = oledIntegrityTestForTarget(target, reason);
      if (ok) {
        Serial.println("OLED:OK");
      } else {
        Serial.print("OLED:FAIL:");
        if (reason.length() > 0) {
          Serial.println(reason);
        } else {
          Serial.println("UNKNOWN");
        }
      }
      return;
    }

    if (sub == "FEEDBACK") {
      // OLED:FEEDBACK:ON|OFF|STATUS
      String arg = getParam(params, 1);
      arg.toUpperCase();
      if (arg == "ON" || arg == "1") {
        oled_input_feedback_enabled = true;
        Serial.println("OLED:FEEDBACK:ON");
        return;
      }
      if (arg == "OFF" || arg == "0") {
        oled_input_feedback_enabled = false;
        Serial.println("OLED:FEEDBACK:OFF");
        return;
      }
      if (arg == "STATUS" || arg.length() == 0) {
        Serial.print("OLED:FEEDBACK:");
        Serial.println(oled_input_feedback_enabled ? "ON" : "OFF");
        return;
      }
      Serial.println("ERROR:Invalid FEEDBACK arg");
      return;
    }

    if (sub == "UI") {
      // OLED:UI:STATE:<gp_connected>:<gp_gaze_data>[:legacy_connection[:legacy_calib]]
      // OLED:UI:SCREEN:<screen_name>
      // OLED:UI:SET:BOOL:<var_name>:<0|1>
      // OLED:UI:SET:U8:<var_name>:<0..255>
      // OLED:UI:SET:STR:<var_name>:<value...>  (value may contain ':'; we use remainder parsing)
      String arg = getParam(params, 1);
      arg.toUpperCase();
      if (arg == "STATE") {
        // Backward-compatible status bridge.
        String gpConnected = getParam(params, 2);
        String gpGazeData = getParam(params, 3);
        if (gpConnected.length() > 0) {
          ui_gp_connected_state = (gpConnected == "1" || gpConnected == "ON" || gpConnected == "TRUE");
          ui_set<bool>(UiDynamicVar::UI_GP_CONNECTED, ui_gp_connected_state);
        }
        if (gpGazeData.length() > 0) {
          ui_gp_gaze_data_state = (gpGazeData == "1" || gpGazeData == "ON" || gpGazeData == "TRUE");
          ui_set<bool>(UiDynamicVar::UI_GP_GAZE_DATA, ui_gp_gaze_data_state);
        }
        ui_dirty = true;
        Serial.println("OLED:UI:STATE:OK");
        return;
      }
      if (arg == "SCREEN") {
        // Change UI screen
        String screen_name = getParam(params, 2);
        bool ok = false;
        UiScreen s = screenFromString(screen_name, ok);
        if (!ok) {
          Serial.println("ERROR:Invalid screen name");
          return;
        }
        ui_current_screen = s;
        ui_dirty = true;
        Serial.println("OLED:UI:SCREEN:OK");
        return;
      }
      if (arg == "SET") {
        String type = getParam(params, 2);
        type.toUpperCase();
        String varName = getParam(params, 3);
        String varNameKey = varName;
        varNameKey.trim();
        varNameKey.toLowerCase();

        // Compatibility aliases for host app values that remained in main.py.
        if (type == "U8" && (varNameKey == "ui_gaze_x" || varNameKey == "ui_gaze_y")) {
          String raw = getParam(params, 4);
          int n = raw.toInt();
          if (n < 0) n = 0;
          if (n > 255) n = 255;
          if (varNameKey == "ui_gaze_x") {
            ui_gaze_x_compat = (uint8_t)n;
          } else {
            ui_gaze_y_compat = (uint8_t)n;
          }

          UiGazePoint gaze;
          gaze.x = mapU8ToRange(ui_gaze_x_compat, 119);
          gaze.y = mapU8ToRange(ui_gaze_y_compat, 71);
          ui_set<UiGazePoint>(UiDynamicVar::UI_GAZE_POINT, gaze);
          ui_dirty = true;
          return;
        }

        UiDynamicVar var;
        if (!dynamicVarFromString(varName, var)) {
          Serial.println("ERROR:Invalid var name");
          return;
        }

        if (type == "BOOL") {
          bool v = false;
          String raw = getParam(params, 4);
          if (!parseBool01(raw, v)) {
            Serial.println("ERROR:Invalid BOOL value");
            return;
          }
          if (var == UiDynamicVar::UI_GP_CONNECTED) {
            ui_gp_connected_state = v;
          } else if (var == UiDynamicVar::UI_GP_GAZE_DATA) {
            ui_gp_gaze_data_state = v;
          }
          ui_set<bool>(var, v);
          ui_dirty = true;
          return;
        }

        if (type == "U8") {
          String raw = getParam(params, 4);
          int n = raw.toInt();
          if (n < 0) n = 0;
          if (n > 255) n = 255;
          if (var == UiDynamicVar::UI_INFERENCE_PROG_BAR) {
            ui_set<int16_t>(var, (int16_t)n);
          } else {
            ui_set<uint8_t>(var, (uint8_t)n);
          }
          ui_dirty = true;
          return;
        }

        if (type == "STR") {
          // Parse remainder after the prefix: UI:SET:STR:<var_name>:
          // We intentionally allow ':' inside the value.
          String prefix = "UI:SET:STR:" + varName + ":";
          int idx = params.indexOf(prefix);
          String value = "";
          if (idx >= 0) {
            value = params.substring(idx + prefix.length());
          } else {
            // Fallback if varName casing differs; take 4th param only.
            value = getParam(params, 4);
          }
          // Unescape common sequences from host (so host can send multi-line strings safely).
          value.replace("\\r\\n", "\n");
          value.replace("\\n", "\n");
          value.replace("\\r", "\n");
          ui_set<String>(var, value);
          ui_dirty = true;
          return;
        }

        Serial.println("ERROR:Invalid SET type");
        return;
      }
      Serial.println("ERROR:Invalid UI command");
      return;
    }

    Serial.println("ERROR:Invalid OLED command");
    return;
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
