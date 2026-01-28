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

// Track if we've sent initial HELLO messages and when to stop
unsigned long boot_time;
bool serial_connected = false;
const unsigned long HELLO_PERIOD_MS = 5000;  // Send HELLO for 5 seconds after boot

void setup() {
  boot_time = millis();
  // Initialize serial communication
  Serial.begin(SERIAL_BAUD);
  
  // Initialize NeoPixel strip (don't wait for Serial on RP2040)
  strip.begin();
  strip.setBrightness(global_brightness);
  strip.show(); // Initialize all pixels to 'off'
  
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
    delay(100);
  }
}

void loop() {
  // Send HELLO messages periodically for first few seconds after boot
  // This helps with auto-detection even if serial wasn't ready during setup()
  unsigned long elapsed = millis() - boot_time;
  if (elapsed < HELLO_PERIOD_MS) {
    // Send HELLO every 500ms during the first 5 seconds
    static unsigned long last_hello = 0;
    if (millis() - last_hello >= 500) {
      Serial.println("HELLO NEOPIXEL");
      serial_connected = true;
      last_hello = millis();
    }
  } else if (!serial_connected) {
    // Send one more HELLO when serial first becomes available after boot period
    Serial.println("HELLO NEOPIXEL");
    serial_connected = true;
  }
  
  // Check for incoming serial commands
  if (Serial.available() > 0) {
    // Mark serial as connected when we receive data
    if (!serial_connected) {
      serial_connected = true;
      // Send HELLO when we first detect serial activity
      Serial.println("HELLO NEOPIXEL");
    }
    
    String command = Serial.readStringUntil('\n');
    command.trim();  // Remove whitespace
    
    if (command.length() > 0) {
      processCommand(command);
    }
  }
}

void processCommand(String cmd) {
  // Handle special commands first
  if (cmd == "PING" || cmd == "HELLO") {
    // Respond to ping/hello for connection testing
    Serial.println("HELLO NEOPIXEL");
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
