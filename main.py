import os
import sys
import time
import math
import re
import threading
import queue
import socket
import csv
import random
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None
    print("Warning: PyYAML not installed. config.yaml will not be loaded.", file=sys.stderr)

# Simulation toggles (can be overridden by config later)
GPIO_BTN_MARKER_SIM = True       # Enable "N" keyboard shortcut for markers
GPIO_BTN_MARKER_ENABLE = False   # Enable hardware button for markers
GPIO_BTN_MARKER_PIN = 0          # GPIO pin for marker button (GP0)
GPIO_LED_CALIBRATION_DISPLAY = True  # Enable on-screen LED display
GPIO_LED_CALIBRATION_KEYBOARD = True  # Enable keyboard shortcuts for calibration
GP_CALIBRATION_METHOD = "LED"  # Calibration method: "LED", "OVERLAY", or "BOTH"
GPIO_LED_CALIBRATION_ENABLE = True  # Enable hardware NeoPixel LEDs for calibration
NEOPIXEL_SERIAL_PORT = ""  # Serial port (empty = auto-detect)
NEOPIXEL_SERIAL_BAUD = 115200  # Serial baud rate
NEOPIXEL_COUNT = 4  # Number of NeoPixels in chain
NEOPIXEL_BRIGHTNESS = 0.3  # Brightness level 0.0-1.0 (sent to microcontroller)
SIM_GAZE = True      # Keyboard + synthetic gaze stream
SIM_XGB  = True      # Fake XGBoost results
SHOW_KEYS = True     # Keep key history for debug panels (keyboard HUD is hidden)
# Windowed fullscreen (borderless), not exclusive fullscreen.
# If False, runs in a fixed-size frameless window (WIDTH x HEIGHT).
FULLSCREEN = True

WIDTH, HEIGHT = 480, 800
FPS = 60  # Increased from 30 to reduce display latency
UI_REFRESH_MS = 100
GP_HOST, GP_PORT = "127.0.0.1", 4242
MODEL_PATH = "models/model.xgb"
FEATURE_WINDOW_MS = 1500
CALIB_OK_THRESHOLD = 1.0  # Maximum average error for OK calibration
CALIB_LOW_THRESHOLD = 2.0  # Maximum average error for low quality calibration
CALIB_DELAY = 0.0  # Internal delay for LED timing (set to 0, use gp_calibrate_delay for Gazepoint API)
CALIB_DWELL = 6.0  # Duration to collect samples (seconds)
GP_CALIBRATE_DELAY = 4.5  # Gazepoint CALIBRATE_DELAY: animation/preparation time before data collection (seconds)
GP_CALIBRATE_TIMEOUT = 1.5  # Gazepoint CALIBRATE_TIMEOUT: duration of data collection per point (seconds)
# Gazepoint calibration point order (used with CALIBRATE_CLEAR + CALIBRATE_ADDPOINT to impose sequencing).
# Coordinate system per Gazepoint API: X/Y are fractions of screen width/height in [0..1].
# Requested order: bottom right, bottom left, top left, top right.
# "Bottom and Top LEDs are at complete extremities" -> use full edges (0.0 / 1.0).
GP_CALIBRATION_POINTS = [
    (1.0, 1.0),  # bottom right
    (0.0, 1.0),  # bottom left
    (0.0, 0.0),  # top left
    (1.0, 0.0),  # top right
]
GPIO_CHIP = "/dev/gpiochip0"  # GPIO chip device for LattePanda
GPIO_BTN_MARKER_DEBOUNCE = 0.2  # Marker button debounce time in seconds
GPIO_BTN_EYE_VIEW_SIM = True  # Enable keyboard shortcut for eye view
GPIO_BTN_EYE_VIEW_ENABLE = False  # Enable hardware button for eye view
GPIO_BTN_EYE_VIEW_PIN = 1  # GPIO pin for eye view button (GP1)
GPIO_BTN_EYE_VIEW_DEBOUNCE = 0.2  # Eye view button debounce time in seconds
GPIO_BTN_EYE_VIEW_KEY = "K_v"  # Keyboard shortcut key for eye view (V key)
EYE_VIEW_TIMEOUT = 0.8  # Timeout in seconds before clearing eye view data (reduced for faster response)
LED_ORDER = [0, 1, 2, 3]  # Physical LED layout mapping (corners only): [low_right, low_left, high_left, high_right] -> physical LED indices
LED_RANDOM_ORDER = False  # Randomize LED order during calibration
LED_REPETITIONS = 1  # Number of times each LED is displayed during calibration
# Blink behavior during Gazepoint delay phase (CALIBRATE_DELAY)
LED_BLINK_DURING_DELAY = True  # If True, blink the active calibration LED during gp_calibrate_delay phase
LED_BLINK_PERIOD_S = 0.6       # Blink period in seconds (higher = fewer serial commands)
LED_BLINK_DUTY = 0.5           # Duty cycle (0..1): fraction of period LEDs are ON
# Oscillation/blinking animation has been removed for reliability.

# RP2040 boot/reset handling
RP2040_BOOT_REINIT_APP_STATE = True
RP2040_HEARTBEAT_TIMEOUT_S = 3.0

# Eye tracker raw fields expected from Gazepoint REC frames.
EYE_TRACKER_RAW_FIELDS = [
    "BPOGX", "BPOGY", "BPOGV",
    "FPOGX", "FPOGY", "FPOGV",
    "LPOGX", "LPOGY", "LPOGV",
    "RPOGX", "RPOGY", "RPOGV",
    "LPD", "RPD",
    "LEYEZ", "REYEZ",
    "LPV", "RPV",
    "LPUPILV", "RPUPILV",
    "LPUPILD", "RPUPILD",
]

# Load config.yaml if it exists
def load_config():
    global GPIO_BTN_MARKER_SIM, GPIO_BTN_MARKER_ENABLE, GPIO_BTN_MARKER_PIN
    global GPIO_LED_CALIBRATION_DISPLAY, GPIO_LED_CALIBRATION_KEYBOARD
    global GP_CALIBRATION_METHOD
    global GPIO_LED_CALIBRATION_ENABLE
    global NEOPIXEL_SERIAL_PORT, NEOPIXEL_SERIAL_BAUD, NEOPIXEL_COUNT, NEOPIXEL_BRIGHTNESS
    global SIM_GAZE, SIM_XGB, SHOW_KEYS, FULLSCREEN, GP_HOST, GP_PORT, MODEL_PATH, FEATURE_WINDOW_MS, UI_REFRESH_MS
    global CALIB_OK_THRESHOLD, CALIB_LOW_THRESHOLD, CALIB_DELAY, CALIB_DWELL
    global GP_CALIBRATE_DELAY, GP_CALIBRATE_TIMEOUT
    global GPIO_CHIP, GPIO_BTN_MARKER_DEBOUNCE
    global GPIO_BTN_EYE_VIEW_SIM, GPIO_BTN_EYE_VIEW_ENABLE, GPIO_BTN_EYE_VIEW_PIN
    global GPIO_BTN_EYE_VIEW_DEBOUNCE, GPIO_BTN_EYE_VIEW_KEY, EYE_VIEW_TIMEOUT
    global LED_ORDER, LED_RANDOM_ORDER, LED_REPETITIONS
    global LED_BLINK_DURING_DELAY, LED_BLINK_PERIOD_S, LED_BLINK_DUTY
    global RP2040_BOOT_REINIT_APP_STATE, RP2040_HEARTBEAT_TIMEOUT_S
    # Oscillation/blinking animation has been removed for reliability.
    if yaml is None:
        return
    config_path = "config.yaml"
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                if config:
                    # GPIO marker button configuration
                    GPIO_BTN_MARKER_SIM = config.get('gpio_btn_marker_sim', GPIO_BTN_MARKER_SIM)
                    GPIO_BTN_MARKER_ENABLE = config.get('gpio_btn_marker_enable', GPIO_BTN_MARKER_ENABLE)
                    GPIO_BTN_MARKER_PIN = config.get('gpio_btn_marker_pin', GPIO_BTN_MARKER_PIN)
                    # GPIO calibration LED configuration
                    GPIO_LED_CALIBRATION_DISPLAY = config.get('gpio_led_calibration_display', GPIO_LED_CALIBRATION_DISPLAY)
                    GPIO_LED_CALIBRATION_KEYBOARD = config.get('gpio_led_calibration_keyboard', GPIO_LED_CALIBRATION_KEYBOARD)
                    # Load calibration method enum, validate it
                    calib_method = config.get('gp_calibration_method', GP_CALIBRATION_METHOD)
                    if calib_method.upper() in ("LED", "OVERLAY", "BOTH"):
                        GP_CALIBRATION_METHOD = calib_method.upper()
                    else:
                        print(f"Warning: Invalid gp_calibration_method '{calib_method}', using default 'LED'", file=sys.stderr)
                        GP_CALIBRATION_METHOD = "LED"
                    GPIO_LED_CALIBRATION_ENABLE = config.get('gpio_led_calibration_enable', GPIO_LED_CALIBRATION_ENABLE)
                    # NeoPixel serial configuration
                    NEOPIXEL_SERIAL_PORT = config.get('neopixel_serial_port', NEOPIXEL_SERIAL_PORT)
                    NEOPIXEL_SERIAL_BAUD = config.get('neopixel_serial_baud', NEOPIXEL_SERIAL_BAUD)
                    NEOPIXEL_COUNT = config.get('neopixel_count', NEOPIXEL_COUNT)
                    NEOPIXEL_BRIGHTNESS = config.get('neopixel_brightness', NEOPIXEL_BRIGHTNESS)
                    # Other configuration
                    SIM_GAZE = config.get('sim_gaze', SIM_GAZE)
                    SIM_XGB = config.get('developpement_xg_boost', SIM_XGB)
                    SHOW_KEYS = config.get('dev_show_keys', SHOW_KEYS)
                    FULLSCREEN = config.get('fullscreen', FULLSCREEN)
                    GP_HOST = config.get('gp_host', GP_HOST)
                    GP_PORT = config.get('gp_port', GP_PORT)
                    MODEL_PATH = config.get('model_path', MODEL_PATH)
                    FEATURE_WINDOW_MS = config.get('feature_window_ms', FEATURE_WINDOW_MS)
                    UI_REFRESH_MS = config.get('ui_refresh_ms', UI_REFRESH_MS)
                    CALIB_OK_THRESHOLD = config.get('calibration_ok_threshold', CALIB_OK_THRESHOLD)
                    CALIB_LOW_THRESHOLD = config.get('calibration_low_threshold', CALIB_LOW_THRESHOLD)
                    CALIB_DELAY = config.get('calib_delay', CALIB_DELAY)
                    CALIB_DWELL = config.get('calib_dwell', CALIB_DWELL)
                    GP_CALIBRATE_DELAY = config.get('gp_calibrate_delay', GP_CALIBRATE_DELAY)
                    GP_CALIBRATE_TIMEOUT = config.get('gp_calibrate_timeout', GP_CALIBRATE_TIMEOUT)
                    # Validate Gazepoint calibration parameters
                    if not isinstance(GP_CALIBRATE_DELAY, (int, float)) or GP_CALIBRATE_DELAY < 0:
                        print(f"Warning: Invalid gp_calibrate_delay '{GP_CALIBRATE_DELAY}', using default 4.5", file=sys.stderr)
                        GP_CALIBRATE_DELAY = 4.5
                    if not isinstance(GP_CALIBRATE_TIMEOUT, (int, float)) or GP_CALIBRATE_TIMEOUT <= 0:
                        print(f"Warning: Invalid gp_calibrate_timeout '{GP_CALIBRATE_TIMEOUT}', using default 1.5", file=sys.stderr)
                        GP_CALIBRATE_TIMEOUT = 1.5
                    GPIO_CHIP = config.get('gpio_chip', GPIO_CHIP)
                    GPIO_BTN_MARKER_DEBOUNCE = config.get('gpio_btn_marker_debounce', GPIO_BTN_MARKER_DEBOUNCE)
                    # Eye view button configuration
                    GPIO_BTN_EYE_VIEW_SIM = config.get('gpio_btn_eye_view_sim', GPIO_BTN_EYE_VIEW_SIM)
                    GPIO_BTN_EYE_VIEW_ENABLE = config.get('gpio_btn_eye_view_enable', GPIO_BTN_EYE_VIEW_ENABLE)
                    GPIO_BTN_EYE_VIEW_PIN = config.get('gpio_btn_eye_view_pin', GPIO_BTN_EYE_VIEW_PIN)
                    GPIO_BTN_EYE_VIEW_DEBOUNCE = config.get('gpio_btn_eye_view_debounce', GPIO_BTN_EYE_VIEW_DEBOUNCE)
                    GPIO_BTN_EYE_VIEW_KEY = config.get('gpio_btn_eye_view_key', GPIO_BTN_EYE_VIEW_KEY)
                    EYE_VIEW_TIMEOUT = config.get('eye_view_timeout', EYE_VIEW_TIMEOUT)
                    # LED calibration physical layout configuration (corners only)
                    LED_ORDER = config.get('led_order', LED_ORDER)
                    LED_RANDOM_ORDER = config.get('led_random_order', LED_RANDOM_ORDER)
                    LED_REPETITIONS = config.get('led_repetitions', LED_REPETITIONS)
                    LED_BLINK_DURING_DELAY = config.get('led_blink_during_delay', LED_BLINK_DURING_DELAY)
                    LED_BLINK_PERIOD_S = config.get('led_blink_period_s', LED_BLINK_PERIOD_S)
                    LED_BLINK_DUTY = config.get('led_blink_duty', LED_BLINK_DUTY)
                    # RP2040 boot/reset handling
                    RP2040_BOOT_REINIT_APP_STATE = config.get('rp2040_boot_reinit_app_state', RP2040_BOOT_REINIT_APP_STATE)
                    RP2040_HEARTBEAT_TIMEOUT_S = config.get('rp2040_heartbeat_timeout_s', RP2040_HEARTBEAT_TIMEOUT_S)
                    try:
                        RP2040_HEARTBEAT_TIMEOUT_S = float(RP2040_HEARTBEAT_TIMEOUT_S)
                    except Exception:
                        RP2040_HEARTBEAT_TIMEOUT_S = 3.0
                    # Oscillation/blinking animation has been removed for reliability.
                    # Validate LED_ORDER: must be exactly 4 integers (corners only).
                    # Center is NOT configured here; it is detected from Gazepoint CALX/CALY and lights all LEDs.
                    if not isinstance(LED_ORDER, list) or len(LED_ORDER) != 4 or any((not isinstance(x, int)) for x in LED_ORDER):
                        print(f"Warning: Invalid led_order '{LED_ORDER}', expected 4 integers; using default [0, 1, 2, 3]", file=sys.stderr)
                        LED_ORDER = [0, 1, 2, 3]
                    # Validate LED_REPETITIONS
                    if not isinstance(LED_REPETITIONS, int) or LED_REPETITIONS < 1:
                        print(f"Warning: Invalid led_repetitions '{LED_REPETITIONS}', using default 1", file=sys.stderr)
                        LED_REPETITIONS = 1
                    # Validate blink configuration (keep conservative defaults to avoid spamming serial)
                    if not isinstance(LED_BLINK_DURING_DELAY, bool):
                        print(f"Warning: Invalid led_blink_during_delay '{LED_BLINK_DURING_DELAY}', using default {LED_BLINK_DURING_DELAY}", file=sys.stderr)
                        LED_BLINK_DURING_DELAY = True
                    if not isinstance(LED_BLINK_PERIOD_S, (int, float)) or LED_BLINK_PERIOD_S < 0.2:
                        print(f"Warning: Invalid led_blink_period_s '{LED_BLINK_PERIOD_S}', using default 0.6", file=sys.stderr)
                        LED_BLINK_PERIOD_S = 0.6
                    if not isinstance(LED_BLINK_DUTY, (int, float)) or LED_BLINK_DUTY <= 0.0 or LED_BLINK_DUTY >= 1.0:
                        print(f"Warning: Invalid led_blink_duty '{LED_BLINK_DUTY}', using default 0.5", file=sys.stderr)
                        LED_BLINK_DUTY = 0.5
                    if not isinstance(UI_REFRESH_MS, (int, float)) or UI_REFRESH_MS < 10:
                        print(f"Warning: Invalid ui_refresh_ms '{UI_REFRESH_MS}', using default 100", file=sys.stderr)
                        UI_REFRESH_MS = 100
                    else:
                        UI_REFRESH_MS = int(UI_REFRESH_MS)
                    # Oscillation/blinking animation has been removed for reliability.
        except Exception as e:
            print(f"Warning: Failed to load config.yaml: {e}", file=sys.stderr)

load_config()

try:
    import pygame
    import numpy as np
except Exception as e:
    print("Missing dependency:", e, file=sys.stderr)
    sys.exit(1)

try:
    import xgboost as xgb  # optional; only used when SIM_XGB is False
except Exception:
    xgb = None

try:
    import joblib
except ImportError:
    joblib = None
    print("Warning: joblib not installed. Model loading may fail.", file=sys.stderr)

try:
    import gpiod
except ImportError:
    gpiod = None
    print("Warning: gpiod not installed. GPIO button support disabled.", file=sys.stderr)

try:
    import serial
    import serial.tools.list_ports
    pyserial_available = True
except ImportError:
    serial = None
    pyserial_available = False
    # This will be checked when NeoPixel controller is initialized - will raise error if needed


class GazeClient:
    def __init__(self, host=GP_HOST, port=GP_PORT, simulate=SIM_GAZE):
        self.host, self.port = host, port
        self.simulate = simulate
        self.q = queue.Queue(maxsize=1024)
        self._thr = None
        self._stop = threading.Event()
        self.connected = False
        self.receiving = False
        self._sim_connected = False
        self._sim_stream = False
        self._t0 = time.time()
        self._sock = None  # Socket reference for sending commands
        self._sock_lock = threading.Lock()  # Thread-safe socket access
        # Calibration results
        # - calib_result: final calibration result from <CAL ID="CALIB_RESULT" .../>
        # - calib_result_summary: latest <ACK ID="CALIBRATE_RESULT_SUMMARY" .../> (progress/diagnostics only)
        self.calib_result = None
        self.calib_result_summary = None
        self.calib_result_lock = threading.Lock()  # Thread-safe calibration result access
        self._ack_events = {}  # Dictionary to store ACK events by ID
        self._ack_lock = threading.Lock()  # Lock for ACK events
        self._rec_count = 0  # Counter for REC messages
        self._cal_count = 0  # Counter for CAL messages
        # Calibration point progress (from CAL messages)
        # Gazepoint sends:
        #   <CAL ID="CALIB_START_PT" PT="1..5" CALX=".." CALY=".." />
        #   <CAL ID="CALIB_RESULT_PT" PT="1..5" ... />
        # We use CALIB_START_PT to sync external LEDs with the actual point being collected.
        self._calib_progress_lock = threading.Lock()
        self._calib_pt = None  # int 1..5
        self._calib_pt_started_at = None  # time.time() when CALIB_START_PT was received
        self._calib_pt_ended_at = None  # time.time() when CALIB_RESULT_PT was received
        self._calib_pt_calx = None  # float 0..1
        self._calib_pt_caly = None  # float 0..1

    def start(self):
        if self._thr and self._thr.is_alive():
            return
        self._stop.clear()
        if self.simulate:
            self._thr = threading.Thread(target=self._run_sim, daemon=True)
        else:
            self._thr = threading.Thread(target=self._run_real, daemon=True)
        self._thr.start()

    def stop(self):
        self._stop.set()
        if self._thr:
            self._thr.join(timeout=1.0)

    # Dev controls
    def sim_connect(self):
        self._sim_connected = True

    def sim_disconnect(self):
        self._sim_connected = False
        self._sim_stream = False

    def sim_toggle_stream(self):
        if self._sim_connected:
            self._sim_stream = not self._sim_stream

    # OpenGaze API v2 Calibration Commands
    def _send_command(self, cmd, wait_for_ack=None, timeout=2.0):
        """Send a command to Gazepoint (thread-safe)
        
        Args:
            cmd: Command string to send
            wait_for_ack: Optional ACK ID to wait for (e.g., "CALIBRATE_SHOW")
            timeout: Timeout in seconds for waiting for ACK
        
        Returns:
            True if command sent (and ACK received if wait_for_ack specified), False otherwise
        """
        if self.simulate:
            return False  # Commands not supported in simulation mode
        
        # Set up ACK event BEFORE sending command to avoid race condition
        ack_received = None
        if wait_for_ack:
            ack_received = threading.Event()
            with self._ack_lock:
                self._ack_events[wait_for_ack] = ack_received
        
        # Send command with socket lock
        send_success = False
        with self._sock_lock:
            if self._sock is None:
                if wait_for_ack:
                    with self._ack_lock:
                        self._ack_events.pop(wait_for_ack, None)
                return False
            try:
                self._sock.sendall(cmd.encode('utf-8') + b'\r\n')
                send_success = True
            except Exception as e:
                if wait_for_ack:
                    with self._ack_lock:
                        self._ack_events.pop(wait_for_ack, None)
                return False
        
        # Wait for ACK outside of socket lock to avoid blocking receive thread
        if wait_for_ack and ack_received and send_success:
            if ack_received.wait(timeout=timeout):
                with self._ack_lock:
                    self._ack_events.pop(wait_for_ack, None)
                return True
            else:
                with self._ack_lock:
                    self._ack_events.pop(wait_for_ack, None)
                return False
        
        return send_success

    def calibrate_show(self, show=True):
        """Show or hide the calibration graphical window"""
        state = "1" if show else "0"
        return self._send_command(f'<SET ID="CALIBRATE_SHOW" STATE="{state}" />', wait_for_ack="CALIBRATE_SHOW")

    def calibrate_clear(self):
        """Clear the internal list of calibration points"""
        return self._send_command('<SET ID="CALIBRATE_CLEAR" />', wait_for_ack="CALIBRATE_CLEAR")

    def calibrate_reset(self):
        """Reset the internal list of calibration points to default values"""
        return self._send_command('<SET ID="CALIBRATE_RESET" />', wait_for_ack="CALIBRATE_RESET")

    def calibrate_addpoint(self, x, y):
        """Add a calibration point to the internal point list (OpenGaze API v2, Section 3.10).

        Args:
            x: X coordinate in normalized screen space [0..1] (percentage of screen width)
            y: Y coordinate in normalized screen space [0..1] (percentage of screen height)

        Returns:
            True if ACK received, False otherwise
        """
        try:
            xf = float(x)
            yf = float(y)
        except Exception:
            return False
        return self._send_command(
            f'<SET ID="CALIBRATE_ADDPOINT" X="{xf:.5f}" Y="{yf:.5f}" />',
            wait_for_ack="CALIBRATE_ADDPOINT",
        )


    def calibrate_timeout(self, timeout_ms=1000):
        """Set the duration of each calibration point (not including animation time)
        
        Args:
            timeout_ms: Duration in milliseconds. Will be converted to seconds for API.
                        The API expects VALUE in seconds (float > 0) as per Section 3.5.
        
        Returns:
            True if command sent successfully, False otherwise
        """
        # Convert milliseconds to seconds as per OpenGaze API specification (Section 3.5)
        timeout_sec = timeout_ms / 1000.0
        return self._send_command(f'<SET ID="CALIBRATE_TIMEOUT" VALUE="{timeout_sec}" />')

    def calibrate_delay(self, delay_ms=200):
        """Set the duration of the calibration animation before calibration at each point begins
        
        Args:
            delay_ms: Duration in milliseconds. Will be converted to seconds for API.
                      The API expects VALUE in seconds (float >= 0) as per Section 3.6.
        
        Returns:
            True if command sent successfully, False otherwise
        """
        # Convert milliseconds to seconds as per OpenGaze API specification (Section 3.6)
        delay_sec = delay_ms / 1000.0
        return self._send_command(f'<SET ID="CALIBRATE_DELAY" VALUE="{delay_sec}" />')

    def calibrate_result_summary(self):
        """Request calibration result summary"""
        return self._send_command('<GET ID="CALIBRATE_RESULT_SUMMARY" />', wait_for_ack="CALIBRATE_RESULT_SUMMARY")
    
    def calibrate_stop(self):
        """Stop any ongoing calibration sequence"""
        return self._send_command('<SET ID="CALIBRATE_START" STATE="0" />', wait_for_ack="CALIBRATE_START")
    
    def calibrate_start(self):
        """Start the calibration sequence"""
        return self._send_command('<SET ID="CALIBRATE_START" STATE="1" />', wait_for_ack="CALIBRATE_START")

    def get_calibration_result(self):
        """Get the latest calibration result summary"""
        with self.calib_result_lock:
            return self.calib_result

    def get_calibration_point_progress(self):
        """Get latest calibration point progress from CAL messages.

        Returns:
            dict with keys: pt (1..5 or None), started_at (float or None), ended_at (float or None),
                            calx (float or None), caly (float or None)
        """
        with self._calib_progress_lock:
            return {
                "pt": self._calib_pt,
                "started_at": self._calib_pt_started_at,
                "ended_at": self._calib_pt_ended_at,
                "calx": self._calib_pt_calx,
                "caly": self._calib_pt_caly,
            }

    def reset_calibration_point_progress(self):
        """Clear stored calibration point progress (so we don't act on stale CAL messages)."""
        with self._calib_progress_lock:
            self._calib_pt = None
            self._calib_pt_started_at = None
            self._calib_pt_ended_at = None
            self._calib_pt_calx = None
            self._calib_pt_caly = None
    
    def _enable_gaze_data_fields(self):
        """Enable all gaze data fields according to OpenGaze API"""
        if self.simulate:
            return
        
        # List of data fields to enable (Section 3.2-3.14)
        fields = [
            "ENABLE_SEND_COUNTER",      # Frame counter (CNT)
            "ENABLE_SEND_TIME",         # Timestamp (TIME)
            "ENABLE_SEND_POG_BEST",     # Best POG (BPOGX, BPOGY, BPOGV) - preferred
            "ENABLE_SEND_POG_LEFT",     # Left eye POG (LPOGX, LPOGY, LPOGV)
            "ENABLE_SEND_POG_RIGHT",    # Right eye POG (RPOGX, RPOGY, RPOGV)
            "ENABLE_SEND_POG_FIX",      # Fixation POG (FPOGX, FPOGY, FPOGV)
            "ENABLE_SEND_PUPIL_LEFT",   # Left pupil 2D data (LPD in pixels, LPV validity)
            "ENABLE_SEND_PUPIL_RIGHT",  # Right pupil 2D data (RPD in pixels, RPV validity)
            "ENABLE_SEND_EYE_LEFT",     # Left eye 3D data (LEYEZ, LPUPILD in meters)
            "ENABLE_SEND_EYE_RIGHT",    # Right eye 3D data (REYEZ, RPUPILD in meters)
        ]
        
        for field in fields:
            cmd = f'<SET ID="{field}" STATE="1" />'
            self._send_command(cmd, wait_for_ack=field, timeout=1.0)
            time.sleep(0.05)  # Small delay between commands

    # Real client with XML protocol parsing
    def _run_real(self):
        self.receiving = False
        self.connected = False
        
        # Retry loop: continuously attempt to connect until successful or stopped
        while not self._stop.is_set():
            sock = None
            try:
                # Attempt connection
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1.0)
                sock.connect((self.host, self.port))
                sock.settimeout(1.0)  # Increased timeout to ensure we don't miss messages
                self.connected = True
                
                # Store socket reference for sending commands
                with self._sock_lock:
                    self._sock = sock
                
                # Enable data streaming via XML protocol
                # Only enable basic data streaming on connection
                # Other fields will be enabled by enable_gaze_data_fields() method
                enable_sent = False
                with self._sock_lock:
                    if self._sock is not None:
                        try:
                            # Enable data streaming (Section 3.1)
                            self._sock.sendall(b'<SET ID="ENABLE_SEND_DATA" STATE="1" />\r\n')
                            enable_sent = True
                        except Exception:
                            pass
                if enable_sent:
                    # Wait a bit for ACK message to be processed
                    time.sleep(0.2)
                    
                # Enable all gaze data fields
                self._enable_gaze_data_fields()
                
                buf = b""
                while not self._stop.is_set():
                    try:
                        data = sock.recv(4096)
                        if not data:
                            break
                        buf += data
                        
                        # Parse XML messages (newline-delimited)
                        while b'\r\n' in buf:
                            line, buf = buf.split(b'\r\n', 1)
                            if not line:
                                continue
                            
                            line_str = line.decode('utf-8', errors='ignore')
                            
                            # Count REC messages
                            if b'<REC' in line:
                                self._rec_count += 1
                            
                            # Helper function to extract XML attributes
                            def get_attr(msg, attr, default):
                                # Try with quotes first
                                idx = msg.find(attr + '="')
                                if idx != -1:
                                    start = idx + len(attr) + 2
                                    end = msg.find('"', start)
                                    if end != -1:
                                        try:
                                            val_str = msg[start:end]
                                            if '.' in val_str:
                                                return float(val_str)
                                            else:
                                                return int(val_str)
                                        except:
                                            return msg[start:end]
                                
                                # Try without quotes (space-separated)
                                idx = msg.find(attr + '=')
                                if idx != -1:
                                    start = idx + len(attr) + 1
                                    # Skip whitespace
                                    while start < len(msg) and msg[start] in ' \t':
                                        start += 1
                                    end = start
                                    while end < len(msg) and msg[end] not in ' \t/>"':
                                        end += 1
                                    if end > start:
                                        try:
                                            val_str = msg[start:end].strip('"\'')
                                            if '.' in val_str:
                                                return float(val_str)
                                            else:
                                                return int(val_str)
                                        except:
                                            pass
                                return default
                            
                            # Parse ACK messages: <ACK ID="..." ... />
                            if b'<ACK' in line:
                                try:
                                    # Extract ACK ID
                                    ack_id_start = line_str.find('ID="')
                                    if ack_id_start != -1:
                                        ack_id_start += 4
                                        ack_id_end = line_str.find('"', ack_id_start)
                                        if ack_id_end != -1:
                                            ack_id = line_str[ack_id_start:ack_id_end]
                                            
                                            # Special handling for CALIBRATE_RESULT_SUMMARY ACK
                                            if ack_id == "CALIBRATE_RESULT_SUMMARY":
                                                # Parse calibration result from ACK message
                                                avg_error = get_attr(line_str, 'AVE_ERROR', None)
                                                num_points = get_attr(line_str, 'VALID_POINTS', None)
                                                
                                                
                                                # Store calibration *summary* if we have data.
                                                # IMPORTANT: This is NOT treated as "calibration finished" because it can be returned mid-calibration.
                                                if avg_error is not None or num_points is not None:
                                                    with self.calib_result_lock:
                                                        success = 1 if (num_points is not None and num_points >= 4) else 0
                                                        self.calib_result_summary = {
                                                            'average_error': avg_error if avg_error is not None else 0.0,
                                                            'num_points': num_points if num_points is not None else 0,
                                                            'success': success,
                                                            'source': 'CALIBRATE_RESULT_SUMMARY',
                                                        }
                                            
                                            # Signal waiting thread if any
                                            with self._ack_lock:
                                                if ack_id in self._ack_events:
                                                    self._ack_events[ack_id].set()
                                except Exception as e:
                                    pass
                            
                            # Parse CAL messages: <CAL ID="CALIB_START_PT" ... />, <CAL ID="CALIB_RESULT_PT" ... />, <CAL ID="CALIB_RESULT" ... />
                            elif b'<CAL' in line:
                                try:
                                    self._cal_count += 1
                                    # Extract CAL ID (handle possible leading/trailing spaces)
                                    cal_id_start = line_str.find('ID="')
                                    if cal_id_start != -1:
                                        cal_id_start += 4
                                        cal_id_end = line_str.find('"', cal_id_start)
                                        if cal_id_end != -1:
                                            cal_id = line_str[cal_id_start:cal_id_end].strip()
                                            
                                            if cal_id == "CALIB_RESULT":
                                                # Parse final calibration result
                                                
                                                # Extract calibration data for all points
                                                # Format: CALX1, CALY1, LX1, LY1, LV1, RX1, RY1, RV1, CALX2, CALY2, ...
                                                calib_data = {}
                                                max_points = 5  # Typically 5 calibration points
                                                
                                                for pt in range(1, max_points + 1):
                                                    calx = get_attr(line_str, f'CALX{pt}', None)
                                                    caly = get_attr(line_str, f'CALY{pt}', None)
                                                    lx = get_attr(line_str, f'LX{pt}', None)
                                                    ly = get_attr(line_str, f'LY{pt}', None)
                                                    lv = get_attr(line_str, f'LV{pt}', None)
                                                    rx = get_attr(line_str, f'RX{pt}', None)
                                                    ry = get_attr(line_str, f'RY{pt}', None)
                                                    rv = get_attr(line_str, f'RV{pt}', None)
                                                    
                                                    if calx is not None and caly is not None:
                                                        calib_data[pt] = {
                                                            'calx': calx, 'caly': caly,
                                                            'lx': lx, 'ly': ly, 'lv': lv,
                                                            'rx': rx, 'ry': ry, 'rv': rv
                                                        }
                                                
                                                # Calculate average error and valid points
                                                valid_points = 0
                                                total_error = 0.0
                                                error_count = 0
                                                
                                                for pt, data in calib_data.items():
                                                    # Check if at least one eye is valid
                                                    l_valid = data.get('lv', 0) == 1
                                                    r_valid = data.get('rv', 0) == 1
                                                    
                                                    if l_valid or r_valid:
                                                        valid_points += 1
                                                        
                                                        # Calculate error for left eye if valid
                                                        if l_valid and data.get('lx') is not None and data.get('ly') is not None:
                                                            dx = data['lx'] - data['calx']
                                                            dy = data['ly'] - data['caly']
                                                            error = math.sqrt(dx*dx + dy*dy)
                                                            total_error += error
                                                            error_count += 1
                                                        
                                                        # Calculate error for right eye if valid
                                                        if r_valid and data.get('rx') is not None and data.get('ry') is not None:
                                                            dx = data['rx'] - data['calx']
                                                            dy = data['ry'] - data['caly']
                                                            error = math.sqrt(dx*dx + dy*dy)
                                                            total_error += error
                                                            error_count += 1
                                                
                                                avg_error = total_error / error_count if error_count > 0 else 0.0
                                                success = 1 if valid_points >= 4 else 0
                                                
                                                # Store calibration result
                                                with self.calib_result_lock:
                                                    self.calib_result = {
                                                        'average_error': avg_error,
                                                        'num_points': valid_points,
                                                        'success': success,
                                                        'calib_data': calib_data,
                                                        'source': 'CALIB_RESULT',
                                                    }
                                            elif cal_id in ("CALIB_START_PT", "CALIB_RESULT_PT"):
                                                # Calibration point progress
                                                pt = get_attr(line_str, "PT", None)
                                                calx = get_attr(line_str, "CALX", None)
                                                caly = get_attr(line_str, "CALY", None)
                                                try:
                                                    pt = int(pt) if pt is not None else None
                                                except Exception:
                                                    pt = None

                                                # CALIB_START_PT indicates the beginning of a new point (use it as our clock)
                                                if cal_id == "CALIB_START_PT" and pt is not None:
                                                    with self._calib_progress_lock:
                                                        self._calib_pt = pt
                                                        self._calib_pt_started_at = time.time()
                                                        self._calib_pt_ended_at = None
                                                        self._calib_pt_calx = calx
                                                        self._calib_pt_caly = caly
                                                # CALIB_RESULT_PT indicates the end of a point; keep timestamp for logging/diagnostics.
                                                elif cal_id == "CALIB_RESULT_PT" and pt is not None:
                                                    with self._calib_progress_lock:
                                                        if self._calib_pt == pt and self._calib_pt_started_at is not None:
                                                            self._calib_pt_ended_at = time.time()
                                except Exception as e:
                                    pass
                            
                            # Parse REC message: <REC ... BPOGX="..." BPOGY="..." ... />
                            # Try multiple POG fields in order of preference (Section 5)
                            elif b'<REC' in line:
                                self.receiving = True
                                try:
                                    # Capture all attributes present in the REC frame for raw diagnostics display.
                                    raw_fields = {}
                                    for m in re.finditer(r'([A-Za-z0-9_]+)="([^"]*)"', line_str):
                                        key = m.group(1).upper()
                                        val = m.group(2).strip()
                                        raw_fields[key] = None if val == "" else val

                                    # Try Best POG first (Section 5.7 - average or best available)
                                    gx = get_attr(line_str, 'BPOGX', None)
                                    gy = get_attr(line_str, 'BPOGY', None)
                                    bpogv = get_attr(line_str, 'BPOGV', None)
                                    valid = bpogv
                                    
                                    # Extract all gaze validity flags for fix #3 (multiple validity check)
                                    fpogv = get_attr(line_str, 'FPOGV', None)
                                    lpogv = get_attr(line_str, 'LPOGV', None)
                                    rpogv = get_attr(line_str, 'RPOGV', None)
                                    
                                    # Fallback to Fixation POG (Section 5.4)
                                    if gx is None:
                                        gx = get_attr(line_str, 'FPOGX', None)
                                        gy = get_attr(line_str, 'FPOGY', None)
                                        valid = fpogv
                                    
                                    # Fallback to Left Eye POG (Section 5.5)
                                    if gx is None:
                                        gx = get_attr(line_str, 'LPOGX', None)
                                        gy = get_attr(line_str, 'LPOGY', None)
                                        valid = lpogv
                                    
                                    # Fallback to Right Eye POG (Section 5.6)
                                    if gx is None:
                                        gx = get_attr(line_str, 'RPOGX', None)
                                        gy = get_attr(line_str, 'RPOGY', None)
                                        valid = rpogv
                                    
                                    # Default values if still None
                                    if gx is None:
                                        gx = 0.5
                                        gy = 0.5
                                        valid = 0
                                    
                                    # Convert validity to boolean
                                    valid = valid > 0.5 if valid is not None else False
                                    bpogv = bpogv > 0.5 if bpogv is not None else False
                                    fpogv = fpogv > 0.5 if fpogv is not None else False
                                    lpogv = lpogv > 0.5 if lpogv is not None else False
                                    rpogv = rpogv > 0.5 if rpogv is not None else False
                                    
                                    # Extract pupil diameter (Sections 5.8 and 5.9)
                                    # Try left eye pupil diameter
                                    lpd = get_attr(line_str, 'LPD', None)
                                    # Try right eye pupil diameter
                                    rpd = get_attr(line_str, 'RPD', None)
                                    
                                    # Average both if available, otherwise use whichever is available
                                    if lpd is not None and rpd is not None:
                                        pupil = (lpd + rpd) / 2.0
                                    elif lpd is not None:
                                        pupil = lpd
                                    elif rpd is not None:
                                        pupil = rpd
                                    else:
                                        pupil = 2.5  # Default fallback
                                    
                                    # Extract eye tracking data (LEYEZ, REYEZ, LPV, RPV, LPUPILD, RPUPILD, LPUPILV, RPUPILV)
                                    leyez = get_attr(line_str, 'LEYEZ', None)
                                    reyez = get_attr(line_str, 'REYEZ', None)
                                    lpv = get_attr(line_str, 'LPV', None)  # Left pupil validity (from ENABLE_SEND_PUPIL_LEFT)
                                    rpv = get_attr(line_str, 'RPV', None)  # Right pupil validity (from ENABLE_SEND_PUPIL_RIGHT)
                                    lpupilv = get_attr(line_str, 'LPUPILV', None)  # Left 3D eye data validity (from ENABLE_SEND_EYE_LEFT)
                                    rpupilv = get_attr(line_str, 'RPUPILV', None)  # Right 3D eye data validity (from ENABLE_SEND_EYE_RIGHT)
                                    lpupild = get_attr(line_str, 'LPUPILD', None)  # Left pupil diameter in meters (from ENABLE_SEND_EYE_LEFT)
                                    rpupild = get_attr(line_str, 'RPUPILD', None)  # Right pupil diameter in meters (from ENABLE_SEND_EYE_RIGHT)
                                    
                                    # Store original validity values before conversion for fix #3
                                    lpupilv_raw = lpupilv
                                    rpupilv_raw = rpupilv
                                    
                                    # Convert validity to boolean
                                    lpv = lpv > 0.5 if lpv is not None else False
                                    rpv = rpv > 0.5 if rpv is not None else False
                                    lpupilv = lpupilv > 0.5 if lpupilv is not None else False
                                    rpupilv = rpupilv > 0.5 if rpupilv is not None else False
                                    
                                    # Fix #1: Filter distance values by validity flags
                                    # Only use LEYEZ/REYEZ when 3D eye data is valid (LPUPILV/RPUPILV)
                                    # Fallback to LPV/RPV if LPUPILV/RPUPILV not available
                                    if lpupilv_raw is not None:
                                        # Use LPUPILV if available (more accurate for 3D data)
                                        if not lpupilv:
                                            leyez = None
                                    elif not lpv:
                                        # Fallback to LPV if LPUPILV not available
                                        leyez = None
                                    
                                    if rpupilv_raw is not None:
                                        # Use RPUPILV if available (more accurate for 3D data)
                                        if not rpupilv:
                                            reyez = None
                                    elif not rpv:
                                        # Fallback to RPV if RPUPILV not available
                                        reyez = None
                                    
                                    # Fix #3: Check multiple validity flags to detect absence faster
                                    # If all key validity flags indicate absence, clear distance values immediately
                                    # This provides faster detection than waiting for any single flag
                                    gaze_invalid = not bpogv and not fpogv  # No valid gaze (Best or Fixation)
                                    
                                    # Check if both eyes have invalid 3D data
                                    # Use raw values to check if they were available
                                    left_eye_3d_invalid = (lpupilv_raw is not None and not lpupilv) or (lpupilv_raw is None and not lpv)
                                    right_eye_3d_invalid = (rpupilv_raw is not None and not rpupilv) or (rpupilv_raw is None and not rpv)
                                    both_eyes_3d_invalid = left_eye_3d_invalid and right_eye_3d_invalid
                                    
                                    # If no valid gaze AND both eyes have invalid 3D data, user is likely absent
                                    # Clear distance values immediately for faster response
                                    if gaze_invalid and both_eyes_3d_invalid:
                                        leyez = None
                                        reyez = None
                                    
                                    # Normalize gaze coordinates (Gazepoint uses 0-1 range)
                                    gx = max(0.0, min(1.0, float(gx)))
                                    gy = max(0.0, min(1.0, float(gy)))
                                    
                                    t = time.time()
                                    self._push_sample(
                                        t,
                                        gx,
                                        gy,
                                        pupil,
                                        valid,
                                        leyez=leyez,
                                        reyez=reyez,
                                        lpv=lpv,
                                        rpv=rpv,
                                        lpupild=lpupild,
                                        rpupild=rpupild,
                                        lpd=lpd,
                                        rpd=rpd,
                                        lpupilv=lpupilv,
                                        rpupilv=rpupilv,
                                        bpogv=bpogv,
                                        fpogv=fpogv,
                                        lpogv=lpogv,
                                        rpogv=rpogv,
                                        raw_fields=raw_fields,
                                    )
                                except Exception:
                                    # Fallback on parse error - use center position with invalid flag
                                    t = time.time()
                                    self._push_sample(
                                        t,
                                        0.5,
                                        0.5,
                                        2.5,
                                        False,
                                        leyez=None,
                                        reyez=None,
                                        lpv=False,
                                        rpv=False,
                                        lpupild=None,
                                        rpupild=None,
                                        raw_fields={},
                                    )
                            
                    except socket.timeout:
                        # Timeout is normal - continue reading
                        continue
                    except Exception:
                        break
            except Exception:
                # Connection failed, will retry
                self.connected = False
                self.receiving = False
            finally:
                with self._sock_lock:
                    self._sock = None
                if sock:
                    try:
                        sock.close()
                    except:
                        pass
                self.connected = False
                self.receiving = False
            
            # Wait before retrying connection (if not stopped)
            if not self._stop.is_set():
                time.sleep(1.0)  # Wait 1 second before retrying

    # Simulated client
    def _run_sim(self):
        self.connected = self._sim_connected
        self.receiving = False
        t0 = time.time()
        ang = 0.0
        while not self._stop.is_set():
            self.connected = self._sim_connected
            if self._sim_connected and self._sim_stream:
                self.receiving = True
                now = time.time()
                dt = now - t0
                ang += 0.05
                # Lissajous-like motion in [0,1]
                gx = 0.5 + 0.4 * math.sin(ang)
                gy = 0.5 + 0.3 * math.sin(ang * 1.7)
                # occasional blink invalidation
                valid = (int(dt * 3) % 20) != 0
                pupil = 2.5 + 0.1 * math.sin(ang * 0.7)
                
                # Simulate eye tracking data
                # LEYEZ and REYEZ: simulate distance in meters (as per OpenGaze API Section 5.11)
                # Typical range: 0.4-0.9 meters (40-90cm), optimal around 0.6m (60cm)
                leyez = 0.6 + 0.15 * math.sin(ang * 0.5)  # Vary around optimal (60cm)
                reyez = 0.6 + 0.15 * math.cos(ang * 0.5)  # Slightly different phase
                
                # LPV and RPV: simulate pupil validity (occasional invalid)
                lpv = (int(dt * 3) % 25) != 0
                rpv = (int(dt * 3) % 23) != 0  # Slightly different pattern
                
                # LPUPILD and RPUPILD: simulate pupil diameter in meters (typical range: 2-8mm = 0.002-0.008m)
                lpupild = 0.004 + 0.001 * math.sin(ang * 0.6)  # Vary around 4mm
                rpupild = 0.004 + 0.001 * math.cos(ang * 0.6)  # Slightly different phase
                
                self._push_sample(
                    now,
                    gx,
                    gy,
                    pupil,
                    valid,
                    leyez=leyez,
                    reyez=reyez,
                    lpv=lpv,
                    rpv=rpv,
                    lpupild=lpupild,
                    rpupild=rpupild,
                    raw_fields={
                        "BPOGX": f"{gx:.6f}",
                        "BPOGY": f"{gy:.6f}",
                        "BPOGV": "1" if valid else "0",
                        "LEYEZ": f"{leyez:.6f}",
                        "REYEZ": f"{reyez:.6f}",
                        "LPV": "1" if lpv else "0",
                        "RPV": "1" if rpv else "0",
                        "LPUPILD": f"{lpupild:.6f}",
                        "RPUPILD": f"{rpupild:.6f}",
                    },
                )
                time.sleep(1.0 / 60.0)
            else:
                self.receiving = False
                time.sleep(0.05)

    def _push_sample(
        self,
        t,
        gx,
        gy,
        pupil,
        valid,
        leyez=None,
        reyez=None,
        lpv=None,
        rpv=None,
        lpupild=None,
        rpupild=None,
        raw_fields=None,
        **extra_fields,
    ):
        sample = {
            "t": t, "gx": gx, "gy": gy, "pupil": pupil, "valid": valid,
            "leyez": leyez, "reyez": reyez, "lpv": lpv, "rpv": rpv,
            "lpupild": lpupild, "rpupild": rpupild
        }
        if raw_fields is not None:
            sample["raw_fields"] = raw_fields
        if extra_fields:
            sample.update(extra_fields)
        try:
            self.q.put_nowait(sample)
        except queue.Full:
            try:
                self.q.get_nowait()
            except Exception:
                pass


class Affine2D:
    def __init__(self):
        self.A = np.array([[1, 0, 0], [0, 1, 0]], dtype=float)

    def fit(self, src_pts, dst_pts):
        X = []
        Y = []
        for (x, y), (u, v) in zip(src_pts, dst_pts):
            X.append([x, y, 1, 0, 0, 0])
            X.append([0, 0, 0, x, y, 1])
            Y.append(u)
            Y.append(v)
        X = np.array(X, dtype=float)
        Y = np.array(Y, dtype=float)
        try:
            p, *_ = np.linalg.lstsq(X, Y, rcond=None)
            self.A = np.array([[p[0], p[1], p[2]], [p[3], p[4], p[5]]], dtype=float)
        except Exception:
            self.A = np.array([[1, 0, 0], [0, 1, 0]], dtype=float)

    def apply(self, x, y):
        v = np.array([x, y, 1.0])
        out = self.A @ v
        return float(out[0]), float(out[1])


class GPIOButtonMonitor:
    """Monitor GPIO button on LattePanda Iota (GP0 + GND)"""
    def __init__(self, gpio_chip="/dev/gpiochip0", gpio_line=0, callback=None, press_callback=None, release_callback=None):
        self.gpio_chip = gpio_chip
        self.gpio_line = gpio_line
        self.callback = callback  # Legacy: called on press only
        self.press_callback = press_callback  # Called when button is pressed
        self.release_callback = release_callback  # Called when button is released
        self._thr = None
        self._stop = threading.Event()
        self._last_press_time = 0
        self.debounce_time = 0.2  # 200ms debounce
        
    def start(self):
        if gpiod is None:
            print("Warning: gpiod not available, GPIO button disabled.", file=sys.stderr)
            return
        
        if self._thr and self._thr.is_alive():
            return
        
        self._stop.clear()
        self._thr = threading.Thread(target=self._run, daemon=True)
        self._thr.start()
    
    def stop(self):
        self._stop.set()
        if self._thr:
            self._thr.join(timeout=1.0)
    
    def _run(self):
        """Monitor GPIO button in background thread"""
        try:
            # Request GPIO line with pull-up (button pulls to GND when pressed)
            chip = gpiod.Chip(self.gpio_chip)
            line = chip.get_line(self.gpio_line)
            
            # Configure as input with pull-up
            # When button is pressed (connected to GND), line will read 0
            # When button is released, pull-up keeps it at 1
            line.request(consumer="marker_button", type=gpiod.LINE_REQ_DIR_IN, flags=gpiod.LINE_REQ_FLAG_BIAS_PULL_UP)
            
            print(f"GPIO button monitoring started on {self.gpio_chip} line {self.gpio_line}")
            last_state = 1  # Released (pull-up)
            
            while not self._stop.is_set():
                # Read button state (0 = pressed, 1 = released)
                current_state = line.get_value()
                
                # Detect falling edge (button press)
                if last_state == 1 and current_state == 0:
                    # Button pressed
                    now = time.time()
                    if now - self._last_press_time > self.debounce_time:
                        self._last_press_time = now
                        if self.callback:
                            self.callback()
                        if self.press_callback:
                            self.press_callback()
                
                # Detect rising edge (button release)
                if last_state == 0 and current_state == 1:
                    # Button released
                    if self.release_callback:
                        self.release_callback()
                
                last_state = current_state
                time.sleep(0.01)  # Poll at 100Hz
                
        except Exception as e:
            print(f"Warning: GPIO button monitor failed: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()


class Rp2040Controller:
    """Control RP2040 co-processor over serial.

    Responsibilities:
    - NeoPixel control (existing INIT/PIXEL/ALL/BRIGHTNESS commands)
    - OLED UI control (OLED:UI:* commands)
    - Receive button edge events (BTN:PRESS/RELEASE:BTN_*) and forward to callback
    """

    def __init__(self, serial_port="", serial_baud=115200, num_pixels=4, brightness=0.3):
        self.serial_port = serial_port
        self.serial_baud = serial_baud
        self.num_pixels = num_pixels
        self.brightness = brightness
        self._serial = None
        self._initialized = False
        self._current_led = -1  # Currently active LED (-1 = all off)
        self._lock = threading.Lock()  # Thread lock for serial access
        self._rx_thr = None
        self._rx_stop = threading.Event()
        self._button_callback = None  # callable(kind:str, btn_name:str)
        self._boot_callback = None  # callable(kind:str, boot_id:int, uptime_s:int)
        self._last_seen_wall_time = None
        self._last_boot_id = None
        self._last_uptime_s = None
        # Serial/heartbeat log for UI (thread-safe, last N lines)
        self._serial_log = []
        self._serial_log_max = 500
        self._serial_log_lock = threading.Lock()
        # Cache last sent state to avoid spamming the serial link every frame (reduces flicker/glitches)
        self._last_mode = None  # "off" | "single" | "all"
        self._last_led = None
        self._last_rgb = None  # (r,g,b) after brightness applied

    def set_button_callback(self, cb):
        """Set callback(kind, btn_name) where kind is 'PRESS'|'RELEASE'."""
        self._button_callback = cb

    def set_boot_callback(self, cb):
        """Set callback(kind, boot_id, uptime_s) for BOOT/HB parsing."""
        self._boot_callback = cb

    def is_alive(self, timeout_s: float = 3.0) -> bool:
        """True if we saw BOOT/HB recently."""
        if self._last_seen_wall_time is None:
            return False
        try:
            return (time.time() - float(self._last_seen_wall_time)) <= float(timeout_s)
        except Exception:
            return False

    def last_seen_age_s(self):
        if self._last_seen_wall_time is None:
            return None
        try:
            return float(time.time() - float(self._last_seen_wall_time))
        except Exception:
            return None

    def _append_serial_log(self, line: str):
        """Append a line to the serial log (thread-safe)."""
        if not line:
            return
        with self._serial_log_lock:
            self._serial_log.append(line.strip())
            if len(self._serial_log) > self._serial_log_max:
                self._serial_log.pop(0)

    def get_serial_log(self, max_entries: int = 40):
        """Return the last max_entries serial log lines (newest last)."""
        with self._serial_log_lock:
            return list(self._serial_log[-max_entries:])

    def _handle_rx_line(self, line: str):
        if not line:
            return
        up = line.strip()
        # Log all RX lines for heartbeat/serial panel
        self._append_serial_log(up)
        # BOOT/HB (1 Hz):
        #   BOOT:<boot_id>:<uptime_s>
        #   HB:<boot_id>:<uptime_s>
        if up.startswith("BOOT:") or up.startswith("HB:"):
            try:
                parts = up.split(":")
                kind = parts[0].strip().upper()  # BOOT or HB
                boot_id = int(parts[1].strip()) if len(parts) > 1 else None
                uptime_s = int(parts[2].strip()) if len(parts) > 2 else None
                self._last_seen_wall_time = time.time()
                self._last_uptime_s = uptime_s
                # Treat HB with a changed boot_id as a reboot (robustness).
                if boot_id is not None and (self._last_boot_id is None or boot_id != self._last_boot_id):
                    self._last_boot_id = boot_id
                    if self._boot_callback:
                        self._boot_callback("BOOT", boot_id, uptime_s if uptime_s is not None else 0)
            except Exception:
                pass
            return
        if up.startswith("BTN:PRESS:") or up.startswith("BTN:RELEASE:"):
            try:
                parts = up.split(":")
                # BTN:PRESS:BTN_A
                kind = parts[1].strip().upper()
                btn = parts[2].strip().upper() if len(parts) >= 3 else ""
                if self._button_callback and btn:
                    self._button_callback(kind, btn)
            except Exception:
                pass

    def ack_boot(self, boot_id: int):
        """Send ACK:BOOT:<boot_id> (no response expected)."""
        try:
            self._send_command(f"ACK:BOOT:{int(boot_id)}", expect_ack=False)
        except Exception:
            pass

    def reinit_outputs(self, oled_init: bool = True):
        """Re-send INIT and optionally OLED:INIT after RP2040 reboot."""
        if not self._initialized:
            return False
        try:
            brightness_int = int(255 * self.brightness)
            self._send_command(f"INIT:{self.num_pixels}:{brightness_int}", expect_ack=True, timeout_s=0.5)
            self.all_off()
            if oled_init:
                self._send_command("OLED:INIT", expect_ack=False)
            return True
        except Exception:
            return False

    def _rx_loop(self):
        """Continuously read serial lines so the RP2040 TX buffer never blocks."""
        while not self._rx_stop.is_set():
            try:
                if self._serial is None:
                    time.sleep(0.05)
                    continue
                raw = self._serial.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="ignore").strip()
                self._handle_rx_line(line)
            except Exception:
                time.sleep(0.02)
        
    def _find_serial_port(self):
        """Auto-detect serial port by looking for microcontroller"""
        if not pyserial_available:
            return None
        
        try:
            ports = serial.tools.list_ports.comports()
            
            for port in ports:
                port_name = port.device.upper() if sys.platform == 'win32' else port.device  # Normalize to uppercase for Windows only
                try:
                    # Try to open port
                    test_serial = serial.Serial(port_name, self.serial_baud, timeout=2.0)
                    
                    # Clear any existing data
                    test_serial.reset_input_buffer()
                    
                    # Wait a bit and read any available data (might be HELLO message)
                    time.sleep(0.5)
                    lines_read = []
                    start_time = time.time()
                    while time.time() - start_time < 2.0:  # Read for up to 2 seconds
                        if test_serial.in_waiting > 0:
                            try:
                                line = test_serial.readline().decode('utf-8', errors='ignore').strip()
                                if line:
                                    lines_read.append(line)
                                    up = line.upper()
                                    if "HELLO" in up and ("NEOPIXEL" in up or "OLED" in up):
                                        test_serial.close()
                                        return port_name
                            except UnicodeDecodeError:
                                continue
                        time.sleep(0.1)
                    
                    # If no HELLO message, try sending a PING/HELLO command to see if device responds
                    test_serial.reset_input_buffer()
                    test_serial.write(b"PING\n")
                    test_serial.flush()
                    time.sleep(0.5)
                    
                    if test_serial.in_waiting > 0:
                        response = test_serial.readline().decode('utf-8', errors='ignore').strip()
                        up = response.upper()
                        if "HELLO" in up and ("NEOPIXEL" in up or "OLED" in up):
                            # Device responded with HELLO NEOPIXEL - confirmed!
                            test_serial.close()
                            return port_name
                    
                    # Try a harmless command as fallback (ALL:OFF should work even without HELLO)
                    test_serial.reset_input_buffer()
                    test_serial.write(b"ALL:OFF\n")
                    test_serial.flush()
                    time.sleep(0.8)  # Give more time for response
                    
                    if test_serial.in_waiting > 0:
                        response = test_serial.readline().decode('utf-8', errors='ignore').strip()
                        if "ACK" in response.upper() or "ERROR" in response.upper():
                            # Device responded - likely our NeoPixel controller
                            test_serial.close()
                            return port_name
                    
                    # Also try INIT command as another fallback
                    test_serial.reset_input_buffer()
                    test_serial.write(b"INIT:4:76\n")
                    test_serial.flush()
                    time.sleep(0.8)
                    
                    if test_serial.in_waiting > 0:
                        response = test_serial.readline().decode('utf-8', errors='ignore').strip()
                        if "ACK" in response.upper() or "ERROR" in response.upper():
                            # Device responded - likely our NeoPixel controller
                            test_serial.close()
                            return port_name
                    
                    test_serial.close()
                except serial.SerialException:
                    continue
                except Exception:
                    continue
                    
        except Exception:
            pass
        
        return None
    
    def _drain_input(self, max_lines=50, max_time_s=0.05):
        """Drain any pending serial input (HELLO/ACK/ERROR), to avoid buffer buildup."""
        if self._serial is None:
            return
        t0 = time.time()
        lines = 0
        try:
            while lines < max_lines and (time.time() - t0) < max_time_s and self._serial.in_waiting > 0:
                raw = self._serial.readline()
                if raw:
                    line = raw.decode("utf-8", errors="ignore").strip()
                    self._handle_rx_line(line)
                lines += 1
        except Exception:
            pass

    def _read_response(self, timeout_s=0.25):
        """Read lines until we see ACK or ERROR (ignoring HELLO), or until timeout."""
        if self._serial is None:
            return None
        deadline = time.time() + timeout_s
        try:
            while time.time() < deadline:
                if self._serial.in_waiting > 0:
                    line = self._serial.readline().decode('utf-8', errors='ignore').strip()
                    if not line:
                        continue
                    # Always parse/log the line so BOOT/HB never get dropped while waiting for ACK.
                    self._handle_rx_line(line)
                    up = line.upper()
                    if up.startswith("ACK") or up.startswith("ERROR"):
                        return line
                else:
                    time.sleep(0.005)
        except Exception:
            return None
        return None

    def _send_command(self, command, expect_ack=True, timeout_s=0.25):
        """Send command to microcontroller via serial and read responses.

        This prevents the RP2040 from blocking on Serial.println("ACK") when the host never reads,
        and makes LED behavior reliable during long-running calibration loops.
        """
        if not self._initialized or self._serial is None:
            return False

        try:
            with self._lock:
                cmd_str = command + "\n"
                self._serial.write(cmd_str.encode('utf-8'))
                self._serial.flush()
                if not expect_ack:
                    return True
            # Read ACK/ERROR without holding lock (RX thread may also be running)
            resp = self._read_response(timeout_s=timeout_s)
            if resp is not None and resp.upper().startswith("ERROR"):
                print(f"Warning: RP2040 error for '{command}': {resp}", file=sys.stderr)
            return True
        except Exception as e:
            print(f"Warning: Failed to send RP2040 command '{command}': {e}", file=sys.stderr)
            return False
    
    def start(self):
        """Initialize serial connection to RP2040 co-processor"""
        if not pyserial_available:
            raise ImportError(
                "pyserial library is required but not installed. "
                "Install with: pip install pyserial"
            )
        
        if self._initialized:
            return True
        
        try:
            # Determine which port to use
            port = self.serial_port
            if not port or port == "":
                port = self._find_serial_port()
                if port is None:
                    # List available ports for user reference
                    available_ports = []
                    try:
                        if pyserial_available:
                            ports = serial.tools.list_ports.comports()
                            available_ports = [p.device for p in ports]
                    except:
                        pass
                    
                    error_msg = (
                        "Could not auto-detect NeoPixel microcontroller.\n"
                        "Make sure:\n"
                        "  - RP2040 is connected via USB\n"
                        "  - RP2040 firmware is uploaded and running\n"
                        "  - RP2040 responds to commands (try: python test_neopixels.py)\n"
                    )
                    if available_ports:
                        error_msg += f"  - Available COM ports: {', '.join(available_ports)}\n"
                        error_msg += f"  - Try specifying one in config.yaml: neopixel_serial_port: \"{available_ports[0]}\"\n"
                        error_msg += f"  - Or run 'python test_neopixels.py' to test and find the correct port\n"
                    else:
                        error_msg += "  - No COM ports found - check USB connection\n"
                    error_msg += "  - Or specify neopixel_serial_port in config.yaml"
                    
                    raise RuntimeError(error_msg)
            else:
                # Normalize port name to uppercase (Windows COM ports are case-sensitive)
                # IMPORTANT: don't uppercase on Linux/macOS (e.g. /dev/ttyACM0 is case-sensitive)
                if sys.platform == "win32":
                    port = port.upper()
            
            # Check if port exists before trying to open
            try:
                available_ports = [p.device for p in serial.tools.list_ports.comports()]
                if port not in available_ports:
                    # Try case-insensitive match
                    port_upper = port.upper()
                    matching_ports = [p for p in available_ports if p.upper() == port_upper]
                    if matching_ports:
                        port = matching_ports[0]
                    else:
                        raise RuntimeError(
                            f"Serial port {port} not found.\n"
                            f"Available ports: {', '.join(available_ports) if available_ports else 'None'}\n"
                            f"Make sure:\n"
                            f"  - RP2040 is connected via USB\n"
                            f"  - Check Device Manager for the correct COM port\n"
                            f"  - Try unplugging and replugging USB cable"
                        )
            except Exception:
                pass
            
            # Open serial connection with better error handling
            try:
                self._serial = serial.Serial(
                    port=port,
                    baudrate=self.serial_baud,
                    timeout=1.0,
                    write_timeout=1.0
                )
            except serial.SerialException as e:
                error_msg = str(e)
                if "PermissionError" in error_msg or "Access is denied" in error_msg or "could not open port" in error_msg.lower():
                    raise RuntimeError(
                        f"Permission denied opening serial port {port}.\n"
                        f"Possible causes:\n"
                        f"  - Port is already in use by another program (close Serial Monitor, Arduino IDE, etc.)\n"
                        f"  - Insufficient permissions (try running as administrator)\n"
                        f"  - Port is locked by another process\n"
                        f"Solutions:\n"
                        f"  1. Close any programs using the serial port (Arduino IDE Serial Monitor, etc.)\n"
                        f"  2. Unplug and replug the USB cable\n"
                        f"  3. Restart the application\n"
                        f"  4. Check Device Manager to see if port is available"
                    ) from e
                else:
                    raise RuntimeError(
                        f"Failed to open serial port {port}: {e}\n"
                        f"Check that the port exists and is not in use by another program"
                    ) from e
            
            # Wait a bit for connection to stabilize
            time.sleep(0.5)
            
            # Clear any pending data
            if self._serial.in_waiting > 0:
                self._serial.reset_input_buffer()
            # Drain any boot-time HELLO spam (avoids mixing with ACK reads)
            self._drain_input(max_lines=200, max_time_s=0.5)

            # Start RX loop to keep buffers drained (and receive button events)
            self._rx_stop.clear()
            self._rx_thr = threading.Thread(target=self._rx_loop, daemon=True)
            self._rx_thr.start()
            
            # Send initialization command with brightness
            brightness_int = int(255 * self.brightness)
            self._send_command(f"INIT:{self.num_pixels}:{brightness_int}", expect_ack=True, timeout_s=0.5)
            
            # Turn off all pixels initially
            self.all_off()
            
            self._initialized = True
            print(f"RP2040 controller initialized on {port}")
            return True
            
        except serial.SerialException as e:
            error_msg = (
                f"NeoPixel controller failed to initialize: {e}\n"
                f"Possible causes:\n"
                f"  - Serial port {port if 'port' in locals() else 'unknown'} not available\n"
                f"  - Port already in use by another application\n"
                f"  - Microcontroller not connected or not powered\n"
                f"  - Wrong baud rate (current: {self.serial_baud})\n"
                f"Install pyserial with: pip install pyserial"
            )
            raise RuntimeError(error_msg) from e
        except Exception as e:
            error_msg = (
                f"NeoPixel controller failed to initialize: {e}\n"
                f"Install pyserial with: pip install pyserial"
            )
            raise RuntimeError(error_msg) from e
    
    def stop(self):
        """Cleanup and turn off all NeoPixels"""
        self.all_off()
        self._rx_stop.set()
        if self._rx_thr:
            self._rx_thr.join(timeout=1.0)
            self._rx_thr = None
        if self._serial is not None:
            try:
                with self._lock:
                    self._serial.close()
            except Exception:
                pass
            self._serial = None
        self._initialized = False
        self._current_led = -1
        self._last_mode = None
        self._last_led = None
        self._last_rgb = None

    # -----------------------
    # OLED UI helpers (v3)
    # -----------------------

    def oled_set_screen(self, screen_name: str):
        """Set OLED UI screen by name (e.g., 'BOOT', 'RECORDING', 'RESULTS')."""
        self._send_command(f"OLED:UI:SCREEN:{screen_name}", expect_ack=False)

    def oled_set_bool(self, var_name: str, value: bool):
        v = "1" if value else "0"
        self._send_command(f"OLED:UI:SET:BOOL:{var_name}:{v}", expect_ack=False)

    def oled_set_u8(self, var_name: str, value: int):
        v = max(0, min(255, int(value)))
        self._send_command(f"OLED:UI:SET:U8:{var_name}:{v}", expect_ack=False)

    def oled_set_str(self, var_name: str, value: str):
        # Avoid sending raw newlines (protocol is line-based). Firmware unescapes \\n -> newline.
        safe = (value or "").replace("\n", "\\n")
        self._send_command(f"OLED:UI:SET:STR:{var_name}:{safe}", expect_ack=False)
    
    def set_led(self, led_index, color=(255, 255, 255), animation_brightness=1.0):
        """Turn on a specific NeoPixel (0-3) with color and turn off all others
        
        Args:
            led_index: Index of the LED (0-3)
            color: RGB color tuple (default: white)
            animation_brightness: Brightness multiplier for animation (0.0-1.0, default: 1.0)
        """
        if not self._initialized:
            raise RuntimeError("NeoPixel controller not initialized. Call start() first.")
        
        if led_index < 0 or led_index >= self.num_pixels:
            raise ValueError(f"LED index {led_index} out of range (0-{self.num_pixels-1})")
        
        # Apply brightness to color (both global brightness and animation brightness)
        r, g, b = color
        total_brightness = self.brightness * animation_brightness
        r = int(r * total_brightness)
        g = int(g * total_brightness)
        b = int(b * total_brightness)

        # If brightness is effectively off, just turn everything off
        if r <= 0 and g <= 0 and b <= 0:
            self.all_off()
            return

        # Idempotency: don't resend if nothing changes
        if self._last_mode == "single" and self._last_led == led_index and self._last_rgb == (r, g, b):
            return
        
        # Turn off all pixels first, then set the active one
        # Only do ALL:OFF when switching into single-pixel mode or changing the active pixel
        if self._last_mode != "single" or self._last_led != led_index:
            self._send_command("ALL:OFF", expect_ack=True)
        self._send_command(f"PIXEL:{led_index}:{r}:{g}:{b}", expect_ack=True)
        
        self._current_led = led_index
        self._last_mode = "single"
        self._last_led = led_index
        self._last_rgb = (r, g, b)
        if led_index >= 0:
            pass
    
    
    def all_off(self):
        """Turn off all NeoPixels"""
        if not self._initialized:
            return
        if self._last_mode == "off":
            return
        self._send_command("ALL:OFF", expect_ack=True)
        self._current_led = -1
        self._last_mode = "off"
        self._last_led = None
        self._last_rgb = None
    
    def all_on(self, color=(255, 255, 255), animation_brightness=1.0):
        """Turn on all NeoPixels with specified color (useful for testing)
        
        Args:
            color: RGB color tuple (default: white)
            animation_brightness: Brightness multiplier for animation (0.0-1.0, default: 1.0)
        """
        if not self._initialized:
            raise RuntimeError("NeoPixel controller not initialized. Call start() first.")
        
        # Apply brightness to color (both global brightness and animation brightness)
        r, g, b = color
        total_brightness = self.brightness * animation_brightness
        r = int(r * total_brightness)
        g = int(g * total_brightness)
        b = int(b * total_brightness)

        # If brightness is effectively off, just turn everything off
        if r <= 0 and g <= 0 and b <= 0:
            self.all_off()
            return

        # Idempotency: don't resend if nothing changes
        if self._last_mode == "all" and self._last_rgb == (r, g, b):
            return
        
        self._send_command(f"ALL:ON:{r}:{g}:{b}", expect_ack=True)
        self._current_led = -2  # Special value for "all on"
        self._last_mode = "all"
        self._last_led = None
        self._last_rgb = (r, g, b)
    
    
    def set_color(self, led_index, r, g, b):
        """Set specific RGB color for a NeoPixel"""
        if not self._initialized:
            raise RuntimeError("NeoPixel controller not initialized. Call start() first.")
        
        if led_index < 0 or led_index >= self.num_pixels:
            raise ValueError(f"LED index {led_index} out of range (0-{self.num_pixels-1})")
        
        # Apply brightness
        r = int(r * self.brightness)
        g = int(g * self.brightness)
        b = int(b * self.brightness)
        
        self._send_command(f"PIXEL:{led_index}:{r}:{g}:{b}")
    
    def set_brightness(self, brightness):
        """Adjust brightness (0.0-1.0)"""
        if not self._initialized:
            raise RuntimeError("NeoPixel controller not initialized. Call start() first.")
        
        if brightness < 0.0 or brightness > 1.0:
            raise ValueError(f"Brightness must be between 0.0 and 1.0, got {brightness}")
        
        self.brightness = brightness
        brightness_int = int(255 * brightness)
        self._send_command(f"BRIGHTNESS:{brightness_int}", expect_ack=True)
    
    def test_led(self, led_index, duration=2.0, color=(255, 255, 255)):
        """Test a specific NeoPixel by turning it on for a duration"""
        if not self._initialized:
            raise RuntimeError("NeoPixel controller not initialized. Call start() first.")
        
        if led_index < 0 or led_index >= self.num_pixels:
            raise ValueError(f"LED index {led_index} out of range (0-{self.num_pixels-1})")
        
        self.set_led(led_index, color)
        time.sleep(duration)
        self.all_off()


def time_strings(t0):
    now = time.time()
    elapsed_ms = int((now - t0) * 1000)
    hh = elapsed_ms // (3600 * 1000)
    mm = (elapsed_ms // (60 * 1000)) % 60
    ss = (elapsed_ms // 1000) % 60
    ms = elapsed_ms % 1000
    elapsed_str = f"{hh:02d}:{mm:02d}:{ss:02d}:{ms:03d}ms"
    wall = datetime.now()
    wall_str = f"{wall.hour:02d}:{wall.minute:02d}:{wall.second:02d}:{int(wall.microsecond/1000):03d}"
    return elapsed_ms, elapsed_str, wall_str


def draw_circle(screen, color, pos, r=12):
    # Use a vivid orange to clearly distinguish from red
    colors = {"red": (220, 50, 47), "orange": (255, 165, 0), "green": (0, 200, 0)}
    pygame.draw.circle(screen, colors.get(color, (128, 128, 128)), pos, r)

def get_distance_color(eyez_value):
    """Get color for distance value based on ranges
    
    Args:
        eyez_value: Distance in meters (as per OpenGaze API Section 5.11)
                    LEYEZ/REYEZ are in meters, not normalized values
    
    Returns:
        Color tuple (R, G, B) based on distance zones:
        - Red: < 55 cm (too close) or > 75 cm (too far)
        - Green: 55-75 cm (good)
    """
    if eyez_value is None:
        return (128, 128, 128)  # Gray for no data
    
    # Convert meters to cm for comparison
    # LEYEZ/REYEZ are in meters according to API Section 5.11
    distance_cm = eyez_value * 100.0
    
    # Distance zones: < 55 = too close, 55-75 = good, > 75 = too far
    if distance_cm < 55.0:
        return (220, 50, 47)  # Red - Too Close (< 55 cm)
    elif distance_cm <= 75.0:
        return (0, 200, 0)   # Green - Good (55-75 cm)
    else:
        return (220, 50, 47)  # Red - Too Far (> 75 cm)

def get_distance_cm(eyez_value):
    """Convert LEYEZ/REYEZ value from meters to centimeters
    
    Args:
        eyez_value: Distance in meters (as per OpenGaze API Section 5.11)
                    LEYEZ/REYEZ are in meters, not normalized values
    
    Returns:
        Distance in centimeters, or None if eyez_value is None
    """
    if eyez_value is None:
        return None
    # LEYEZ/REYEZ are in meters according to API Section 5.11
    # Convert meters to centimeters
    return eyez_value * 100.0

def draw_eye_view(screen, eye_data, eye_data_time, font, small, big):
    """Draw eye view display with two eyes, validity, distance, and pupil diameter"""
    # Check if data is too old (timeout)
    if eye_data is None or eye_data_time is None:
        # Show "No data" message
        txt = big.render("No Eye Data", True, (128, 128, 128))
        screen.blit(txt, (WIDTH // 2 - txt.get_width() // 2, HEIGHT // 2 - 20))
        return
    
    current_time = time.time()
    if current_time - eye_data_time > EYE_VIEW_TIMEOUT:
        # Data is too old, clear display
        txt = big.render("No Recent Data", True, (128, 128, 128))
        screen.blit(txt, (WIDTH // 2 - txt.get_width() // 2, HEIGHT // 2 - 20))
        return
    
    # Extract values
    leyez = eye_data.get("leyez")
    reyez = eye_data.get("reyez")
    # NOTE: Gazepoint validity fields are reported as LPV/RPV, but the physical
    # "left/right" can appear swapped depending on tracker coordinate conventions.
    # The UI uses user-facing left/right, so we map as:
    #   left_open  <- rpv
    #   right_open <- lpv
    lpv_raw = bool(eye_data.get("lpv", False))
    rpv_raw = bool(eye_data.get("rpv", False))
    # Prefer diameter presence to decide "open" when available, otherwise validity.
    lpupild_raw = eye_data.get("lpupild")  # meters
    rpupild_raw = eye_data.get("rpupild")  # meters

    left_open = bool(rpv_raw) if rpupild_raw is None else (rpupild_raw is not None)
    right_open = bool(lpv_raw) if lpupild_raw is None else (lpupild_raw is not None)

    # For display values, keep physical mapping consistent with open/closed mapping.
    lpv = left_open
    rpv = right_open
    lpupild = rpupild_raw
    rpupild = lpupild_raw
    
    # Eye positions (centered horizontally, spaced vertically)
    eye_radius = 40
    left_eye_x = WIDTH // 4
    right_eye_x = 3 * WIDTH // 4
    eye_y = HEIGHT // 3
    
    # Draw left eye
    left_eye_color = (0, 200, 0) if lpv else (220, 50, 47)  # Green if valid, red if invalid
    pygame.draw.circle(screen, left_eye_color, (left_eye_x, eye_y), eye_radius, 3)
    # Draw LEFT label
    left_label = font.render("LEFT", True, (255, 255, 255))
    screen.blit(left_label, (left_eye_x - left_label.get_width() // 2, eye_y - eye_radius - 30))
    
    # Draw right eye
    right_eye_color = (0, 200, 0) if rpv else (220, 50, 47)  # Green if valid, red if invalid
    pygame.draw.circle(screen, right_eye_color, (right_eye_x, eye_y), eye_radius, 3)
    # Draw RIGHT label
    right_label = font.render("RIGHT", True, (255, 255, 255))
    screen.blit(right_label, (right_eye_x - right_label.get_width() // 2, eye_y - eye_radius - 30))
    
    # Draw Distance value under left eye
    leyez_y = eye_y + eye_radius + 20
    if leyez is not None:
        distance_cm = get_distance_cm(leyez)
        distance_color = get_distance_color(leyez)
        if distance_cm is not None:
            distance_text = f"Distance: {distance_cm:.1f} cm"
        else:
            distance_text = "Distance: N/A"
        distance_surf = small.render(distance_text, True, distance_color)
        screen.blit(distance_surf, (left_eye_x - distance_surf.get_width() // 2, leyez_y))
    else:
        distance_surf = small.render("Distance: N/A", True, (128, 128, 128))
        screen.blit(distance_surf, (left_eye_x - distance_surf.get_width() // 2, leyez_y))
    
    # Draw Distance value under right eye
    reyez_y = eye_y + eye_radius + 20
    if reyez is not None:
        distance_cm = get_distance_cm(reyez)
        distance_color = get_distance_color(reyez)
        if distance_cm is not None:
            distance_text = f"Distance: {distance_cm:.1f} cm"
        else:
            distance_text = "Distance: N/A"
        distance_surf = small.render(distance_text, True, distance_color)
        screen.blit(distance_surf, (right_eye_x - distance_surf.get_width() // 2, reyez_y))
    else:
        distance_surf = small.render("Distance: N/A", True, (128, 128, 128))
        screen.blit(distance_surf, (right_eye_x - distance_surf.get_width() // 2, reyez_y))
    
    # Draw pupil diameter values below Distance
    pupil_y = leyez_y + 25
    
    # Left pupil diameter
    if lpupild is not None:
        lpupild_mm = lpupild * 1000  # Convert from meters to mm
        lpupild_text = f"Left pupil diameter: {lpupild_mm:.2f} mm"
        lpupild_surf = small.render(lpupild_text, True, (255, 255, 255))
        screen.blit(lpupild_surf, (left_eye_x - lpupild_surf.get_width() // 2, pupil_y))
    else:
        lpupild_surf = small.render("Left pupil diameter: N/A", True, (128, 128, 128))
        screen.blit(lpupild_surf, (left_eye_x - lpupild_surf.get_width() // 2, pupil_y))
    
    # Right pupil diameter
    if rpupild is not None:
        rpupild_mm = rpupild * 1000  # Convert from meters to mm
        rpupild_text = f"Right pupil diameter: {rpupild_mm:.2f} mm"
        rpupild_surf = small.render(rpupild_text, True, (255, 255, 255))
        screen.blit(rpupild_surf, (right_eye_x - rpupild_surf.get_width() // 2, pupil_y))
    else:
        rpupild_surf = small.render("Right pupil diameter: N/A", True, (128, 128, 128))
        screen.blit(rpupild_surf, (right_eye_x - rpupild_surf.get_width() // 2, pupil_y))


def main():
    pygame.init()
    # Set up display: frameless window; optionally borderless "windowed fullscreen".
    display_flags = pygame.NOFRAME
    global WIDTH, HEIGHT
    if FULLSCREEN:
        info = pygame.display.Info()
        WIDTH, HEIGHT = int(info.current_w), int(info.current_h)
        screen = pygame.display.set_mode((WIDTH, HEIGHT), display_flags)
    else:
        screen = pygame.display.set_mode((WIDTH, HEIGHT), display_flags)
    pygame.display.set_caption("Gaze App")
    font = pygame.font.SysFont(None, 26)
    big = pygame.font.SysFont(None, 40)
    small = pygame.font.SysFont(None, 20)

    logo = None
    for p in ("assets/logo.jpg", "logo.jpg"):
        if os.path.exists(p):
            try:
                logo = pygame.image.load(p)
            except Exception:
                logo = None
            break

    # Splash
    splash_until = time.time() + 0.8
    while time.time() < splash_until:
        screen.fill((0, 0, 0))
        if logo:
            img = pygame.transform.smoothscale(logo, (int(WIDTH * 0.7), int(WIDTH * 0.7 * logo.get_height() / logo.get_width())))
            screen.blit(img, (WIDTH // 2 - img.get_width() // 2, HEIGHT // 2 - img.get_height() // 2))
        pygame.display.flip()
        pygame.time.delay(10)

    gp = GazeClient(simulate=SIM_GAZE)
    gp.start()
    
    # Button events can come from:
    # - keyboard simulation (Pygame)
    # - RP2040 serial (BTN:PRESS/RELEASE)
    # Queue items are (kind, btn, src) where src is "KB"|"RP2040".
    btn_event_q = queue.Queue()
    # RP2040 boot/heartbeat events: (kind, boot_id, uptime_s)
    rp2040_evt_q = queue.Queue()

    # Start GPIO button monitor for LattePanda Iota (if enabled)
    gpio_monitor = None
    if GPIO_BTN_MARKER_ENABLE and gpiod is not None:
        gpio_monitor = GPIOButtonMonitor(gpio_chip=GPIO_CHIP, gpio_line=GPIO_BTN_MARKER_PIN, callback=gpio_button_callback)
        gpio_monitor.debounce_time = GPIO_BTN_MARKER_DEBOUNCE
        gpio_monitor.start()
    elif GPIO_BTN_MARKER_ENABLE and gpiod is None:
        print("WARNING: GPIO button enabled but gpiod library not available!")
    
    # Start GPIO button monitor for eye view (if enabled)
    gpio_eye_view_monitor = None
    if GPIO_BTN_EYE_VIEW_ENABLE and gpiod is not None:
        gpio_eye_view_monitor = GPIOButtonMonitor(gpio_chip=GPIO_CHIP, gpio_line=GPIO_BTN_EYE_VIEW_PIN, 
                                                   press_callback=gpio_eye_view_button_press,
                                                   release_callback=gpio_eye_view_button_release)
        gpio_eye_view_monitor.debounce_time = GPIO_BTN_EYE_VIEW_DEBOUNCE
        gpio_eye_view_monitor.start()
    elif GPIO_BTN_EYE_VIEW_ENABLE and gpiod is None:
        print("WARNING: Eye view GPIO button enabled but gpiod library not available!")
    
    # Start NeoPixel controller for calibration LEDs (if enabled)
    led_controller = None
    if GPIO_LED_CALIBRATION_ENABLE:
        try:
            led_controller = Rp2040Controller(
                serial_port=NEOPIXEL_SERIAL_PORT,
                serial_baud=NEOPIXEL_SERIAL_BAUD,
                num_pixels=NEOPIXEL_COUNT,
                brightness=NEOPIXEL_BRIGHTNESS
            )
            # start() will raise error if library unavailable or initialization fails
            led_controller.start()
            # Forward RP2040 button edges into the main loop.
            try:
                led_controller.set_button_callback(lambda kind, btn: btn_event_q.put((kind, btn, "RP2040")))
            except Exception:
                pass
            # Forward RP2040 BOOT detection into main loop.
            try:
                led_controller.set_boot_callback(lambda kind, boot_id, uptime_s: rp2040_evt_q.put((kind, boot_id, uptime_s)))
            except Exception:
                pass
            print("NeoPixel controller initialized successfully")
        except Exception as e:
            print(f"Warning: Failed to initialize NeoPixel controller: {e}", file=sys.stderr)
            print("NeoPixel LEDs will not be available. Continuing without hardware LEDs...", file=sys.stderr)
            led_controller = None
    
    # Load XGBoost models at startup (if not in simulation mode)
    if not SIM_XGB:
        load_xgb_models()

    conn_status = "red"
    calib_status = "red"
    receiving_hint = False

    # FLOW screen id (matches ui/v3 UiScreen names).
    # BOOT -> FIND_POSITION -> (MOVE_*/IN_POSITION) -> CALIBRATION -> RECORD_CONFIRMATION ->
    # RECORDING -> STOP_RECORD -> INFERENCE_LOADING -> RESULTS, with MONITORING as a BTN_B-held modal.
    state = "BOOT"
    prev_state = None  # for MONITORING modal
    monitoring_active = False
    running = True
    clock = pygame.time.Clock()
    position_next_eval = 0.0  # head positioning UI refresh cadence (UI_REFRESH_MS)

    # Ensure OLED starts on BOOT screen (if RP2040 is connected)
    if led_controller is not None:
        try:
            led_controller.oled_set_screen("BOOT")
        except Exception:
            pass

    # (btn_event_q is defined earlier, before hardware initialization)

    # Calibration
    aff = Affine2D()
    calib_points = []
    target_points = []
    calib_step = -1
    calib_step_start = 0.0
    calib_collect_start = 0.0  # When to start collecting samples (after delay)
    calib_sequence = []  # Sequence of LED indices for calibration
    calib_led_animation_start = {}  # Track animation start time for each LED index
    led_calib_last_point_key = None  # (pt, started_at) to detect Gazepoint point transitions
    using_led_calib = False  # Flag for LED-based calibration active
    using_overlay_calib = False  # Flag for overlay calibration active
    # CALIB_DELAY and CALIB_DWELL are loaded from config.yaml in load_config()
    calib_quality = "none"  # none|ok|low|failed
    calib_avg_error = None  # Average error value for display (when ok or low)
    current_calib_override = None  # None|'failed'|'low'

    # Calibration debug logging (saved to logs/<timestamp>/calibration_debug.csv)
    calib_debug_events = []
    calib_debug_t0 = None
    calib_debug_saved_for_t0 = None
    calib_debug_last_point_key = None  # (pt, started_at)
    calib_debug_last_point_end_key = None  # (pt, ended_at)
    calib_debug_last_result_sig = None  # (source, num_points, avg_error, success)

    def log_calibration_event(event, method=None, note=None, **fields):
        """Append a structured calibration debug event for later CSV export."""
        nonlocal calib_debug_events, calib_debug_t0
        now_ts = time.time()
        elapsed = (now_ts - calib_debug_t0) if calib_debug_t0 else None
        ev = {
            "wall_time": datetime.fromtimestamp(now_ts).strftime("%H:%M:%S:%f")[:-3],
            "elapsed_s": round(elapsed, 3) if elapsed is not None else None,
            "event": event,
            "method": method,
            "state": state,
            "pt": None,
            "calx": None,
            "caly": None,
            "pt_started_at": None,
            "pt_ended_at": None,
            "phase_elapsed_s": None,
            "in_delay_phase": None,
            "gp_calibrate_delay_s": GP_CALIBRATE_DELAY,
            "gp_calibrate_timeout_s": GP_CALIBRATE_TIMEOUT,
            "calib_result_source": None,
            "valid_points": None,
            "avg_error": None,
            "success": None,
            "note": note,
        }
        ev.update(fields or {})
        calib_debug_events.append(ev)

    # Collection
    session_t0 = None
    recording_elapsed_frozen = None  # seconds, freezes after stop
    next_event_index = 1
    event_open = False
    event_started_at = None  # wall time (time.time()) when current event started
    event_elapsed_frozen = None  # seconds, freezes after stop
    events = []  # list of (elapsed_ms, elapsed_str, wall_str, label)
    gaze_samples = []  # store minimal fields for analysis

    # Analyzing/Results
    analyze_t0 = 0.0
    per_event_scores = {}
    global_score = 0.0
    results_scroll = 0.0
    results_pages = []  # list of {"title": str, "vals": [str,str,str,str]}
    results_page_index = 0
    analysis_total_values = 0
    analysis_values_done = 0
    analysis_seconds_per_value = 3  # also written to models/model_metadata.json
    # If model metadata exists, prefer its ETA hints.
    try:
        meta_path = os.path.join("models", "model_metadata.json")
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            est = meta.get("estimated_seconds_per_value")
            if isinstance(est, (int, float)) and est > 0:
                analysis_seconds_per_value = float(est)
    except Exception:
        pass
    # Transient user feedback message
    info_msg = None
    info_msg_until = 0.0
    
    # Button press visual feedback
    button_pressed_until = 0.0
    
    # Eye view state
    eye_view_active = False  # Whether eye view is currently displayed
    last_eye_data = None  # Store last eye tracking data for display
    last_eye_data_time = None  # Timestamp of last eye data update

    # Dev defaults for gaze sim: start disconnected, user can press '1' to connect

    def generate_calibration_sequence():
        """Generate calibration sequence based on LED_ORDER, LED_RANDOM_ORDER, and LED_REPETITIONS
        
        Returns:
            List of physical LED indices (0-3) in the order they should be displayed
        """
        # Start with the configured LED order
        sequence = list(LED_ORDER)
        
        # Randomize if enabled
        if LED_RANDOM_ORDER:
            sequence = sequence.copy()
            random.shuffle(sequence)
        
        # Repeat each LED the specified number of times
        repeated_sequence = []
        for led_index in sequence:
            repeated_sequence.extend([led_index] * LED_REPETITIONS)
        
        return repeated_sequence

    def start_calibration(override=None):
        nonlocal state, calib_status, calib_step, calib_step_start, calib_points, target_points, calib_quality, aff, current_calib_override, calib_avg_error
        nonlocal using_led_calib, using_overlay_calib, calib_sequence, calib_led_animation_start, led_calib_last_point_key
        nonlocal calib_debug_events, calib_debug_t0, calib_debug_saved_for_t0
        nonlocal calib_debug_last_point_key, calib_debug_last_point_end_key, calib_debug_last_result_sig
        if not gp.connected:
            set_info_msg("Connect Gazepoint first")
            return
        # Start a new calibration debug log session
        calib_debug_t0 = time.time()
        calib_debug_saved_for_t0 = None
        calib_debug_events.clear()
        calib_debug_last_point_key = None
        calib_debug_last_point_end_key = None
        calib_debug_last_result_sig = None
        log_calibration_event(
            "calibration_start",
            method=GP_CALIBRATION_METHOD,
            note="start_calibration called",
            using_led_calib=GP_CALIBRATION_METHOD in ("LED", "BOTH"),
            using_overlay_calib=(GP_CALIBRATION_METHOD in ("OVERLAY", "BOTH") and not SIM_GAZE),
        )
        # FLOW screen stays CALIBRATION; internal calibration work runs while on this screen.
        state = "CALIBRATION"
        calib_status = "orange"
        calib_quality = "none"
        # Record override result for this calibration session (dev simulation)
        current_calib_override = override
        
        # For LED-based calibration, we want LEDs to match Gazepoint's actual calibration targets.
        # Keep sequence aligned to LED_ORDER (no randomization during real calibration).
        calib_sequence = list(LED_ORDER)
        # Reset animation + point tracking
        calib_led_animation_start.clear()
        led_calib_last_point_key = None
        if not SIM_GAZE:
            gp.reset_calibration_point_progress()
        
        # Initialize flags for which calibration methods are active based on enum
        using_led_calib = GP_CALIBRATION_METHOD in ("LED", "BOTH")
        using_overlay_calib = GP_CALIBRATION_METHOD in ("OVERLAY", "BOTH") and not SIM_GAZE
        
        # Ensure gaze data streaming is enabled (required for both calibration methods)
        if not SIM_GAZE:
            ok = gp._send_command('<SET ID="ENABLE_SEND_DATA" STATE="1" />')
            log_calibration_event("enable_send_data", method=GP_CALIBRATION_METHOD, ok=bool(ok))
            time.sleep(0.1)
        
        # Initialize LED-based calibration if enabled (use Gazepoint server-side calibration with overlay hidden)
        if using_led_calib:
            # Stop any ongoing calibration first (as per Gazepoint API documentation)
            ok = gp.calibrate_stop()
            log_calibration_event("gp_calibrate_stop", method="LED", ok=bool(ok))
            time.sleep(0.1)
            
            # Clear calibration result before starting
            with gp.calib_result_lock:
                gp.calib_result = None
                gp.calib_result_summary = None
            
            # Clear previous calibration points
            ok = gp.calibrate_clear()
            log_calibration_event("gp_calibrate_clear", method="LED", ok=bool(ok))
            time.sleep(0.1)
            
            # Add calibration points in the requested order (imposes point sequence)
            add_ok = True
            for (x, y) in GP_CALIBRATION_POINTS:
                ok = gp.calibrate_addpoint(x, y)
                add_ok = add_ok and bool(ok)
                log_calibration_event("gp_calibrate_addpoint", method="LED", ok=bool(ok), x=x, y=y)
                time.sleep(0.05)
            if not add_ok:
                log_calibration_event("gp_calibrate_addpoint_failed", method="LED", note="One or more ADDPOINT commands failed")
            
            # Set Gazepoint calibration timeout (data collection duration per point)
            timeout_ms = int(GP_CALIBRATE_TIMEOUT * 1000)
            ok = gp.calibrate_timeout(timeout_ms)
            log_calibration_event("gp_calibrate_timeout_set", method="LED", ok=bool(ok), timeout_ms=timeout_ms)
            time.sleep(0.1)
            
            # Set Gazepoint calibration delay (animation/preparation time before data collection)
            delay_ms = int(GP_CALIBRATE_DELAY * 1000)
            ok = gp.calibrate_delay(delay_ms)
            log_calibration_event("gp_calibrate_delay_set", method="LED", ok=bool(ok), delay_ms=delay_ms)
            time.sleep(0.1)
            
            # Hide calibration window (use LEDs instead of overlay)
            show_ok = gp.calibrate_show(False)
            log_calibration_event("gp_calibrate_show", method="LED", ok=bool(show_ok), show=False)
            if not show_ok:
                set_info_msg("Failed to configure calibration", dur=2.0)
                using_led_calib = False
                # If overlay calibration is also disabled, abort
                if not using_overlay_calib:
                    log_calibration_event("calibration_abort", method="LED", note="Failed to configure calibration (CALIBRATE_SHOW)")
                    save_calibration_logs(calib_debug_events, calib_debug_t0)
                    calib_debug_saved_for_t0 = calib_debug_t0
                    state = "CALIBRATION"
                    return
            
            # Start the calibration sequence and wait for ACK
            if using_led_calib:
                start_ok = gp.calibrate_start()
                log_calibration_event("gp_calibrate_start", method="LED", ok=bool(start_ok))
                if start_ok:
                    calib_step_start = time.time()  # Record when calibration started
                else:
                    set_info_msg("Failed to start calibration", dur=2.0)
                    gp.calibrate_show(False)  # Ensure calibration window is hidden
                    using_led_calib = False
                    # If overlay calibration is also disabled, abort
                    if not using_overlay_calib:
                        log_calibration_event("calibration_abort", method="LED", note="Failed to start calibration (CALIBRATE_START)")
                        save_calibration_logs(calib_debug_events, calib_debug_t0)
                        calib_debug_saved_for_t0 = calib_debug_t0
                        state = "CALIBRATION"
                        return
        
        # Start overlay calibration if enabled (only works with real hardware)
        if using_overlay_calib:
            # Stop any ongoing calibration first (as per Gazepoint API documentation)
            ok = gp.calibrate_stop()
            log_calibration_event("gp_calibrate_stop", method="OVERLAY", ok=bool(ok))
            time.sleep(0.1)
            
            # Clear calibration result before starting
            with gp.calib_result_lock:
                gp.calib_result = None
                gp.calib_result_summary = None
            
            # Clear previous calibration points
            ok = gp.calibrate_clear()
            log_calibration_event("gp_calibrate_clear", method="OVERLAY", ok=bool(ok))
            time.sleep(0.1)
            
            # Add calibration points in the requested order (imposes point sequence)
            add_ok = True
            for (x, y) in GP_CALIBRATION_POINTS:
                ok = gp.calibrate_addpoint(x, y)
                add_ok = add_ok and bool(ok)
                log_calibration_event("gp_calibrate_addpoint", method="OVERLAY", ok=bool(ok), x=x, y=y)
                time.sleep(0.05)
            if not add_ok:
                log_calibration_event("gp_calibrate_addpoint_failed", method="OVERLAY", note="One or more ADDPOINT commands failed")
            
            # Set calibration timeout (1 second per point)
            ok = gp.calibrate_timeout(1000)
            log_calibration_event("gp_calibrate_timeout_set", method="OVERLAY", ok=bool(ok), timeout_ms=1000)
            time.sleep(0.1)
            
            # Set calibration delay (200ms animation delay)
            ok = gp.calibrate_delay(200)
            log_calibration_event("gp_calibrate_delay_set", method="OVERLAY", ok=bool(ok), delay_ms=200)
            time.sleep(0.1)
            
            # Show calibration window and wait for ACK
            show_ok = gp.calibrate_show(True)
            log_calibration_event("gp_calibrate_show", method="OVERLAY", ok=bool(show_ok), show=True)
            if not show_ok:
                set_info_msg("Failed to show calibration window", dur=2.0)
                using_overlay_calib = False
                # If LED calibration is also disabled, abort
                if not using_led_calib:
                    log_calibration_event("calibration_abort", method="OVERLAY", note="Failed to show calibration window (CALIBRATE_SHOW)")
                    save_calibration_logs(calib_debug_events, calib_debug_t0)
                    calib_debug_saved_for_t0 = calib_debug_t0
                    state = "CALIBRATION"
                    return
            
            # Start the calibration sequence and wait for ACK
            if using_overlay_calib:
                start_ok = gp.calibrate_start()
                log_calibration_event("gp_calibrate_start", method="OVERLAY", ok=bool(start_ok))
                if not start_ok:
                    set_info_msg("Failed to start overlay calibration", dur=2.0)
                    gp.calibrate_show(False)  # Hide calibration window
                    using_overlay_calib = False
                    # If LED calibration is also disabled, abort
                    if not using_led_calib:
                        log_calibration_event("calibration_abort", method="OVERLAY", note="Failed to start overlay calibration (CALIBRATE_START)")
                        save_calibration_logs(calib_debug_events, calib_debug_t0)
                        calib_debug_saved_for_t0 = calib_debug_t0
                        state = "CALIBRATION"
                        return

    def start_collection():
        nonlocal state, session_t0, next_event_index, event_open, event_started_at, events, gaze_samples
        nonlocal recording_elapsed_frozen, event_elapsed_frozen
        if not gp.connected:
            set_info_msg("Connect Gazepoint first")
            return
        if calib_quality not in ("ok", "low"):
            set_info_msg("Calibrate first")
            return
        state = "RECORDING"
        if led_controller is not None:
            try:
                led_controller.oled_set_screen("RECORDING")
            except Exception:
                pass
        session_t0 = time.time()
        recording_elapsed_frozen = None
        next_event_index = 1
        event_open = False
        event_started_at = None
        event_elapsed_frozen = None
        events = []
        gaze_samples = []

    def stop_collection_begin_analysis():
        nonlocal state, analyze_t0, per_event_scores, global_score
        nonlocal event_open, next_event_index, event_started_at
        nonlocal results_pages, results_page_index, analysis_total_values, analysis_values_done
        nonlocal recording_elapsed_frozen, event_elapsed_frozen
        state = "INFERENCE_LOADING"
        if led_controller is not None:
            try:
                led_controller.oled_set_screen("INFERENCE_LOADING")
            except Exception:
                pass
        analyze_t0 = time.time()
        # Freeze timers for UI once recording stops.
        try:
            recording_elapsed_frozen = (time.time() - session_t0) if session_t0 else None
        except Exception:
            recording_elapsed_frozen = None
        try:
            event_elapsed_frozen = (time.time() - event_started_at) if (event_open and event_started_at is not None) else None
        except Exception:
            event_elapsed_frozen = None

        # If the last event is still open, auto-close it before analysis.
        if event_open and session_t0 is not None:
            elapsed_ms, elapsed_str, wall_str = time_strings(session_t0)
            label = f"EVENT{next_event_index}_STOP"
            events.append((elapsed_ms, elapsed_str, wall_str, label))
            event_open = False
            event_started_at = None
            next_event_index += 1
        
        # Save session logs to CSV
        save_session_logs(events, gaze_samples, session_t0)
        
        # Run analysis in a tiny thread to simulate progress
        def _run():
            nonlocal per_event_scores, global_score
            nonlocal results_pages, results_page_index, analysis_total_values, analysis_values_done

            # Build page list: [global, event1, event2, ...]
            n_events = max(0, next_event_index - 1)
            pages = [{"title": "GLOBAL RESULTS", "vals": ["", "", "", ""]}]
            for eidx in range(1, n_events + 1):
                pages.append({"title": f"EVENT {eidx} RESULTS", "vals": ["", "", "", ""]})

            results_pages = pages
            results_page_index = 0
            analysis_total_values = len(pages) * 4
            analysis_values_done = 0

            if SIM_XGB:
                # Mock model: generate 4 values per page, one every 3 seconds.
                for pidx, page in enumerate(pages):
                    for vidx in range(4):
                        time.sleep(float(analysis_seconds_per_value))
                        # Deterministic-ish values in [0..1]
                        val = 0.25 + 0.15 * (vidx) + 0.05 * (pidx % 5)
                        val = max(0.0, min(1.0, val))
                        page["vals"][vidx] = f"val{vidx+1}: {val:.3f}"
                        analysis_values_done += 1

                # Derive a simple scalar global/event score from val1 (placeholder)
                per_event_scores = {}
                for pidx in range(1, len(pages)):
                    try:
                        v1 = pages[pidx]["vals"][0].split(":")[1].strip()
                        per_event_scores[f"E{pidx}"] = float(v1)
                    except Exception:
                        per_event_scores[f"E{pidx}"] = 0.0
                global_score = float(sum(per_event_scores.values()) / len(per_event_scores)) if per_event_scores else 0.0
            else:
                # Real model path: model returns 4 global values, then 4 values per event.
                per_event_vals, global_vals = run_xgb_results({
                    "events": events,
                    "gaze": gaze_samples,
                }, aff=aff, session_t0=session_t0)
                global_vals = (global_vals or [0.0, 0.0, 0.0, 0.0])[:4]
                # For compatibility with existing CSV logging, keep a scalar score (val1).
                global_score = float(global_vals[0]) if global_vals else 0.0
                per_event_scores = {}

                # Fill page values immediately (no artificial delay)
                pages[0]["vals"] = [f"val{i+1}: {float(v):.3f}" for i, v in enumerate(global_vals)]
                for pidx in range(1, len(pages)):
                    ev = (per_event_vals or {}).get(f"E{pidx}") or [0.0, 0.0, 0.0, 0.0]
                    ev = (list(ev) + [0.0, 0.0, 0.0, 0.0])[:4]
                    per_event_scores[f"E{pidx}"] = float(ev[0])
                    pages[pidx]["vals"] = [f"val{i+1}: {float(v):.3f}" for i, v in enumerate(ev)]
                analysis_values_done = analysis_total_values
            
            # Save results to CSV
            save_results_logs(per_event_scores, global_score, session_t0)
            
            # flip to results after small delay
            time.sleep(0.3)
            set_results_state()
        threading.Thread(target=_run, daemon=True).start()

    def set_results_state():
        nonlocal state, results_scroll
        state = "RESULTS"
        if led_controller is not None:
            try:
                led_controller.oled_set_screen("RESULTS")
            except Exception:
                pass
        results_scroll = 0.0

    def marker_toggle():
        nonlocal event_open, next_event_index, event_started_at, button_pressed_until
        if session_t0 is None:
            return
        elapsed_ms, elapsed_str, wall_str = time_strings(session_t0)
        if not event_open:
            label = f"EVENT{next_event_index}_START"
            event_open = True
            event_started_at = time.time()
        else:
            label = f"EVENT{next_event_index}_STOP"
            event_open = False
            event_started_at = None
            next_event_index += 1
        events.append((elapsed_ms, elapsed_str, wall_str, label))
        # Show visual feedback for 200ms
        button_pressed_until = time.time() + 0.2

    def set_info_msg(msg, dur=2.0):
        nonlocal info_msg, info_msg_until
        info_msg = msg
        info_msg_until = time.time() + dur

    def reset_app_state():
        nonlocal state, calib_status, receiving_hint, aff, calib_points, target_points
        nonlocal calib_step, calib_step_start, calib_collect_start, calib_quality, calib_avg_error, current_calib_override
        nonlocal session_t0, recording_elapsed_frozen, next_event_index, event_open, event_started_at, event_elapsed_frozen, events, gaze_samples
        nonlocal analyze_t0, per_event_scores, global_score, results_scroll
        nonlocal results_pages, results_page_index, analysis_total_values, analysis_values_done
        nonlocal info_msg, info_msg_until, last_calib_gaze, using_led_calib, using_overlay_calib
        nonlocal eye_view_active, last_eye_data, last_eye_data_time, calib_sequence, calib_led_animation_start
        nonlocal led_calib_last_point_key
        state = "BOOT"
        # Ensure the OLED is immediately put back to BOOT even if the state was already BOOT.
        if led_controller is not None:
            try:
                led_controller.oled_set_screen("BOOT")
            except Exception:
                pass
        calib_status = "red"
        receiving_hint = False
        aff = Affine2D()
        calib_points = []
        target_points = []
        calib_step = -1
        calib_step_start = 0.0
        calib_sequence = []
        calib_led_animation_start.clear()
        led_calib_last_point_key = None
        calib_collect_start = 0.0
        calib_quality = "none"
        calib_avg_error = None
        current_calib_override = None
        using_led_calib = False
        using_overlay_calib = False
        if not SIM_GAZE:
            gp.reset_calibration_point_progress()
        session_t0 = None
        recording_elapsed_frozen = None
        next_event_index = 1
        event_open = False
        event_started_at = None
        event_elapsed_frozen = None
        events = []
        gaze_samples = []
        analyze_t0 = 0.0
        per_event_scores = {}
        global_score = 0.0
        results_scroll = 0.0
        results_pages = []
        results_page_index = 0
        analysis_total_values = 0
        analysis_values_done = 0
        info_msg = None
        info_msg_until = 0.0
        last_calib_gaze = None
        eye_view_active = False
        last_eye_data = None
        last_eye_data_time = None
        # Force the next OLED sync to re-send dynamic vars (avoid stale cached values after reset).
        try:
            oled_last.clear()
        except Exception:
            pass
        set_info_msg("App state reset", dur=2.0)

    def _position_status_from_eye_data():
        """Return position status string: 'Good'|'Far'|'Near'."""
        nonlocal last_eye_data
        if not last_eye_data:
            return "Far"
        leyez = last_eye_data.get("leyez")
        reyez = last_eye_data.get("reyez")
        # Prefer any available eye distance (meters) and convert to cm.
        dist_cm = None
        if leyez is not None:
            dist_cm = get_distance_cm(leyez)
        elif reyez is not None:
            dist_cm = get_distance_cm(reyez)
        if dist_cm is None:
            return "Far"
        if dist_cm < 55.0:
            return "Near"
        if dist_cm > 75.0:
            return "Far"
        return "Good"

    def _set_screen(new_screen: str):
        """Set FLOW screen and update OLED immediately."""
        nonlocal state
        if new_screen == state:
            return
        state = new_screen
        if led_controller is not None:
            try:
                led_controller.oled_set_screen(new_screen)
            except Exception:
                pass

    def handle_button(kind: str, btn: str):
        """Handle a button edge event from keyboard or RP2040."""
        nonlocal prev_state, monitoring_active
        nonlocal results_pages, results_page_index
        kind = (kind or "").upper()
        btn = (btn or "").upper()

        # Reset button (RP2040 BTN_CENTER / keyboard "S") resets the whole app state.
        # This is intentionally handled before any modal/state gating.
        if kind == "PRESS" and btn == "BTN_CENTER":
            monitoring_active = False
            prev_state = None
            reset_app_state()
            _set_screen("BOOT")
            return

        # Modal monitoring (hold BTN_B)
        if btn == "BTN_B":
            if kind == "PRESS" and state != "MONITORING":
                prev_state = state
                monitoring_active = True
                _set_screen("MONITORING")
            elif kind == "RELEASE" and state == "MONITORING":
                monitoring_active = False
                _set_screen(prev_state or "BOOT")
            return

        # Ignore all other inputs while monitoring modal is active
        if state == "MONITORING":
            return

        if kind != "PRESS":
            return

        if state == "BOOT":
            if btn == "BTN_RIGHT":
                _set_screen("FIND_POSITION")
            return

        # FIND_POSITION is an explicit "ready" step.
        # Stay on it until RIGHT is pressed, then choose a positioning hint screen.
        if state == "FIND_POSITION":
            if btn == "BTN_RIGHT":
                pos = _position_status_from_eye_data()
                if pos == "Good":
                    _set_screen("IN_POSITION")
                elif pos == "Near":
                    _set_screen("MOVE_FARTHER")
                else:
                    _set_screen("MOVE_CLOSER")
            return

        # On hint screens, advancement to calibration is NEVER automatic:
        # user must press RIGHT while in a good position.
        if state in ("MOVE_CLOSER", "MOVE_FARTHER", "IN_POSITION"):
            if btn == "BTN_RIGHT":
                pos = _position_status_from_eye_data()
                if pos == "Good":
                    _set_screen("CALIBRATION")
                else:
                    # Keep user on positioning step; OLED/Pygame will update the hint screen.
                    set_info_msg("Not in position yet", dur=1.0)
            return

        if state == "CALIBRATION":
            running_now = using_led_calib or using_overlay_calib
            done_now = (not running_now) and (calib_quality in ("ok", "low", "failed"))
            if btn == "BTN_RIGHT":
                if (not running_now) and calib_quality == "none":
                    start_calibration(override=None)
                elif done_now and calib_quality in ("ok", "low"):
                    _set_screen("RECORD_CONFIRMATION")
            elif btn == "BTN_LEFT":
                if done_now:
                    start_calibration(override=None)
            return

        if state == "RECORD_CONFIRMATION":
            if btn == "BTN_RIGHT":
                start_collection()
            return

        if state == "RECORDING":
            if btn == "BTN_A":
                marker_toggle()
            elif btn == "BTN_RIGHT":
                _set_screen("STOP_RECORD")
            return

        if state == "STOP_RECORD":
            if btn == "BTN_LEFT":
                _set_screen("RECORDING")
            elif btn == "BTN_RIGHT":
                stop_collection_begin_analysis()
            return

        if state == "RESULTS":
            if btn == "BTN_RIGHT" and results_pages and results_page_index < (len(results_pages) - 1):
                results_page_index += 1
            elif btn == "BTN_LEFT" and results_pages and results_page_index > 0:
                results_page_index -= 1
            return

    # -----------------------
    # OLED v3 sync (cached)
    # -----------------------
    oled_last = {}

    def _oled_set_bool(var_name: str, value: bool):
        if led_controller is None:
            return
        key = ("B", var_name)
        v = bool(value)
        if oled_last.get(key) == v:
            return
        oled_last[key] = v
        try:
            led_controller.oled_set_bool(var_name, v)
        except Exception:
            pass

    def _oled_set_u8(var_name: str, value: int):
        if led_controller is None:
            return
        key = ("U8", var_name)
        v = int(max(0, min(255, int(value))))
        if oled_last.get(key) == v:
            return
        oled_last[key] = v
        try:
            led_controller.oled_set_u8(var_name, v)
        except Exception:
            pass

    def _oled_set_str(var_name: str, value: str):
        if led_controller is None:
            return
        key = ("S", var_name)
        v = "" if value is None else str(value)
        if oled_last.get(key) == v:
            return
        oled_last[key] = v
        try:
            led_controller.oled_set_str(var_name, v)
        except Exception:
            pass

    def _fmt_mmss(seconds: float) -> str:
        if seconds is None or seconds < 0:
            return "--:--"
        s = int(seconds)
        m = s // 60
        ss = s % 60
        return f"{m:02d}:{ss:02d}"

    def oled_sync():
        """Push current state + dynamic vars to the OLED (ui/v4)."""
        rp2040_ok = (led_controller is not None and getattr(led_controller, "_serial", None) is not None)
        rp2040_alive = bool(led_controller.is_alive(RP2040_HEARTBEAT_TIMEOUT_S)) if led_controller is not None else False
        # BOOT screen status
        if state == "BOOT":
            # Eye tracker checkbox must reflect tracker connection.
            _oled_set_bool("ui_tracker_detected", bool(gp.connected))
            # LED checkbox reflects whether the RP2040 co-processor is connected.
            _oled_set_bool("ui_led_detected", bool(rp2040_ok and rp2040_alive))
            # Connection reflects whether we're actually receiving gaze data.
            _oled_set_bool("ui_connection", bool(gp.receiving))
            _oled_set_str("ui_loading_data", "")

        # CALIBRATION screen vars
        if state == "CALIBRATION":
            running_now = using_led_calib or using_overlay_calib
            done_now = (not running_now) and (calib_quality in ("ok", "low", "failed"))
            _oled_set_str("ui_calib_start_btn", "Start calibration>" if (not running_now and calib_quality == "none") else "")
            _oled_set_str("ui_calib_redo_btn", "<Redo" if done_now else "")
            _oled_set_str("ui_calib_next_btn", "Next>" if (done_now and calib_quality in ("ok", "low")) else "")
            # Calibration result as raw average error
            if done_now and calib_quality in ("ok", "low") and calib_avg_error is not None:
                try:
                    _oled_set_str("ui_calib_result", f"{float(calib_avg_error):.3f}")
                except Exception:
                    _oled_set_str("ui_calib_result", "")
            else:
                _oled_set_str("ui_calib_result", "")

            # LED indicators
            ul = ur = bl = br = False
            if running_now:
                if calib_step == 4:
                    ul = ur = bl = br = True
                elif calib_step == 0:
                    br = True  # low_right
                elif calib_step == 1:
                    bl = True  # low_left
                elif calib_step == 2:
                    ul = True  # high_left
                elif calib_step == 3:
                    ur = True  # high_right
            _oled_set_bool("ui_led_up_left", ul)
            _oled_set_bool("ui_led_up_right", ur)
            _oled_set_bool("ui_led_bottom_left", bl)
            _oled_set_bool("ui_led_bottom_right", br)

        # RECORDING screen vars
        if state == "RECORDING":
            total = (time.time() - session_t0) if session_t0 else None
            _oled_set_str("ui_recording_timer", _fmt_mmss(total))
            if event_open and event_started_at is not None:
                _oled_set_str("ui_event_time", _fmt_mmss(time.time() - event_started_at))
                # Event is currently open => next A press will STOP it.
                _oled_set_str("ui_event_name", f"STOP EVENT {next_event_index}")
            else:
                _oled_set_str("ui_event_time", "--:--")
                # No open event => next A press will START the next event.
                _oled_set_str("ui_event_name", f"START EVENT {next_event_index}")

        # INFERENCE_LOADING
        if state == "INFERENCE_LOADING":
            pct = 0
            rem_s = None
            if analysis_total_values > 0:
                pct = int(100 * float(analysis_values_done) / float(analysis_total_values))
                pct = max(0, min(100, pct))
                rem_s = (analysis_total_values - analysis_values_done) * float(analysis_seconds_per_value)
            _oled_set_u8("ui_inference_prog_bar", pct)
            _oled_set_str("ui_inference_timer", _fmt_mmss(rem_s) if rem_s is not None else "")
            _oled_set_str("ui_loading_data", "")

        # STOP_RECORD warning
        if state == "STOP_RECORD":
            if event_open:
                _oled_set_str("ui_close_event_warning", f"Event marker {next_event_index} will be closed automatically")
            else:
                _oled_set_str("ui_close_event_warning", "")

        # RESULTS (placeholder wiring; refined in later todos)
        if state == "RESULTS":
            page = results_pages[results_page_index] if (results_pages and 0 <= results_page_index < len(results_pages)) else {"title": "RESULTS", "vals": ["", "", "", ""]}
            _oled_set_str("ui_results_title", page.get("title", "RESULTS"))
            _oled_set_str("ui_results_prev_btn", "<Previous" if (results_pages and results_page_index > 0) else "")
            _oled_set_str("ui_results_next_btn", "Next>" if (results_pages and results_page_index < (len(results_pages) - 1)) else "")
            vals = page.get("vals") or ["", "", "", ""]
            vals = (vals + ["", "", "", ""])[:4]
            _oled_set_str("ui_result_1", vals[0])
            _oled_set_str("ui_result_2", vals[1])
            _oled_set_str("ui_result_3", vals[2])
            _oled_set_str("ui_result_4", vals[3])

        # MONITORING modal
        if state == "MONITORING":
            if last_eye_data:
                lpv_raw = bool(last_eye_data.get("lpv"))
                rpv_raw = bool(last_eye_data.get("rpv"))
                lpupild_raw = last_eye_data.get("lpupild")
                rpupild_raw = last_eye_data.get("rpupild")
                left_open = bool(rpv_raw) if rpupild_raw is None else (rpupild_raw is not None)
                right_open = bool(lpv_raw) if lpupild_raw is None else (lpupild_raw is not None)
            else:
                left_open = False
                right_open = False
            _oled_set_bool("ui_left_eye", bool(left_open))
            _oled_set_bool("ui_right_eye", bool(right_open))
            pos = _position_status_from_eye_data()
            # v4 UI uses ui_text_el_269 for position status.
            _oled_set_str("ui_text_el_269", pos)
            if last_calib_gaze and len(last_calib_gaze) >= 2:
                gx = max(0.0, min(1.0, float(last_calib_gaze[0])))
                gy = max(0.0, min(1.0, float(last_calib_gaze[1])))
                _oled_set_u8("ui_gaze_x", int(gx * 255))
                _oled_set_u8("ui_gaze_y", int(gy * 255))
            else:
                _oled_set_u8("ui_gaze_x", 128)
                _oled_set_u8("ui_gaze_y", 128)
    
    def gpio_button_callback():
        """Called when GPIO marker button is pressed"""
        nonlocal button_pressed_until
        if state == "COLLECTING":
            marker_toggle()
    
    def gpio_eye_view_button_press():
        """Called when GPIO eye view button is pressed (hold down)"""
        nonlocal eye_view_active
        eye_view_active = True
    
    def gpio_eye_view_button_release():
        """Called when GPIO eye view button is released"""
        nonlocal eye_view_active
        eye_view_active = False
    
    def set_eye_view(active):
        """Set eye view display state"""
        nonlocal eye_view_active
        eye_view_active = active

    def draw_status_header():
        conn_x = 50  # moved 20px to the right
        cal_x = WIDTH - 50  # moved 20px to the left
        draw_circle(screen, conn_status, (conn_x, 30))
        if receiving_hint:
            pygame.draw.circle(screen, (255, 255, 255), (conn_x, 30), 4)
        # Blink calibration circle while calibrating
        if state == "CALIBRATION":
            blink_on = (int(time.time() * 2) % 2) == 0
            if blink_on:
                draw_circle(screen, calib_status, (cal_x, 30))
        else:
            draw_circle(screen, calib_status, (cal_x, 30))
        # Middle recording indicator when recording
        if state == "RECORDING":
            mid_x = WIDTH // 2
            # blink at ~2 Hz
            blink_on = (int(time.time() * 2) % 2) == 0
            if blink_on:
                pygame.draw.circle(screen, (220, 50, 47), (mid_x, 30), 12)
            lbl_col = small.render("Recording", True, (200, 200, 200))
            screen.blit(lbl_col, (mid_x - lbl_col.get_width() // 2, 30 + 16))
        # Labels under circles
        lbl_conn = small.render("Connection", True, (200, 200, 200))
        screen.blit(lbl_conn, (conn_x - lbl_conn.get_width() // 2, 30 + 16))
        lbl_cal = small.render("Calibration", True, (200, 200, 200))
        screen.blit(lbl_cal, (cal_x - lbl_cal.get_width() // 2, 30 + 16))
        # Display calibration quality value if ok or low
        if calib_quality in ("ok", "low") and calib_avg_error is not None:
            try:
                error_str = f"{float(calib_avg_error):.3f}"
            except Exception:
                error_str = ""
            lbl_error = small.render(error_str, True, (180, 180, 180))
            screen.blit(lbl_error, (cal_x - lbl_error.get_width() // 2, 30 + 16 + lbl_cal.get_height() + 2))

    def draw_preview_and_markers():
        # Stacked vertical squares: top preview, bottom marker list
        top_y = 120
        # compute square size to fit two squares plus spacing
        spacing = 10
        sq = min(WIDTH - 20, (HEIGHT - top_y - 40 - spacing) // 2)
        sq = max(120, sq)
        cx = WIDTH // 2
        
        # Top square: preview with label
        preview_label = small.render("Gaze Preview", True, (180, 180, 180))
        screen.blit(preview_label, (cx - preview_label.get_width() // 2, top_y - 20))
        
        rect = pygame.Rect(cx - sq // 2, top_y, sq, sq)
        pygame.draw.rect(screen, (30, 30, 30), rect, border_radius=6)
        pygame.draw.rect(screen, (60, 60, 60), rect, 2, border_radius=6)  # Border
        
        if last_calib_gaze is not None:
            # Handle new format: (gx, gy, valid) or old format: (gx, gy)
            if len(last_calib_gaze) == 3:
                gx, gy, valid = last_calib_gaze
            else:
                gx, gy = last_calib_gaze
                valid = True  # Assume valid for old format compatibility
            
            if valid:
                # Valid gaze: draw at actual position
                # Gazepoint coordinates: gx=0.0 (left), gx=1.0 (right), gy=0.0 (top), gy=1.0 (bottom)
                # Map normalized coordinates (0-1) to preview rectangle pixels
                dx = rect.left + int(gx * rect.width)
                dy = rect.top + int(gy * rect.height)
                # Clamp to rectangle bounds to prevent drawing outside
                dx = max(rect.left, min(rect.right - 1, dx))
                dy = max(rect.top, min(rect.bottom - 1, dy))
                pygame.draw.circle(screen, (0, 200, 255), (dx, dy), 6)
                # Draw a small trail effect
                pygame.draw.circle(screen, (0, 150, 200), (dx, dy), 8, 1)
            else:
                # Invalid gaze: show blinking red marker at center
                blink_rate = 0.5  # Blink every 0.5 seconds
                should_show = int(time.time() / blink_rate) % 2 == 0
                if should_show:
                    pygame.draw.circle(screen, (255, 0, 0), (rect.centerx, rect.centery), 8)
                    pygame.draw.circle(screen, (200, 0, 0), (rect.centerx, rect.centery), 10, 2)
        
        # Draw crosshair in center for reference
        pygame.draw.line(screen, (60, 60, 60), 
                       (rect.centerx - 10, rect.centery), 
                       (rect.centerx + 10, rect.centery), 1)
        pygame.draw.line(screen, (60, 60, 60), 
                       (rect.centerx, rect.centery - 10), 
                       (rect.centerx, rect.centery + 10), 1)
        
        # Bottom square: marker list with label
        markers_label = small.render("Event Markers", True, (180, 180, 180))
        screen.blit(markers_label, (cx - markers_label.get_width() // 2, rect.bottom + spacing - 20))
        
        list_rect = pygame.Rect(cx - sq // 2, rect.bottom + spacing, sq, sq)
        pygame.draw.rect(screen, (20, 20, 20), list_rect, border_radius=6)
        pygame.draw.rect(screen, (60, 60, 60), list_rect, 2, border_radius=6)  # Border
        
        # Draw markers
        y = list_rect.top + 8
        if len(events) == 0:
            # Show placeholder text when no events
            placeholder = small.render("No markers yet", True, (120, 120, 120))
            screen.blit(placeholder, (list_rect.centerx - placeholder.get_width() // 2, 
                                     list_rect.centery - placeholder.get_height() // 2))
        else:
            for i in range(max(0, len(events) - 14), len(events)):
                if y + font.get_height() > list_rect.bottom - 8:
                    break  # Stop if we run out of space
                _, elapsed_str, wall_str, label = events[i]
                line = f"{elapsed_str} : {label}"
                surf = font.render(line, True, (230, 230, 230))
                screen.blit(surf, (list_rect.left + 8, y))
                y += surf.get_height() + 2

    last_calib_gaze = None
    last_sample_raw = None  # latest full sample dict from the eye tracker
    key_log = []  # list of (time, label)
    button_log = []  # list of (time, src, kind, btn)
    app_t0 = time.time()
    serial_log_autoscroll = True
    serial_log_scroll_offset = 0  # lines from bottom when autoscroll is disabled
    serial_log_rect_for_input = None

    def _fmt_unknown(v):
        if v is None:
            return "unknown"
        if isinstance(v, str) and v.strip() == "":
            return "unknown"
        return str(v)

    def log_button(kind: str, btn: str, src: str):
        button_log.append((time.time(), src, kind, btn))
        if len(button_log) > 40:
            del button_log[: len(button_log) - 40]

    def log_key(label):
        if not SHOW_KEYS:
            return
        key_log.append((time.time(), label))
        if len(key_log) > 20:
            del key_log[: len(key_log) - 20]

    # Map keys to labels for overlay; only log when the corresponding sim toggle is enabled
    KEY_LABELS_GPIO = {
        pygame.K_z: "Z",
        pygame.K_x: "X",
        pygame.K_n: "N",
        pygame.K_b: "B",
        pygame.K_m: "M",
    }
    KEY_LABELS_GAZE = {
        pygame.K_1: "1",
        pygame.K_2: "2",
        pygame.K_3: "3",
    }

    def draw_key_overlay():
        if not SHOW_KEYS:
            return
        cheat = [
            "W/A/S/D/X — Joystick Up/Left/Center/Right/Down",
            "P — A button (toggle event marker in RECORDING)",
            "L (hold) — B button (Monitoring modal)",
            "M — Quit",
        ]
        if SIM_GAZE:
            cheat += [
                "1 — Gaze: Connected",
                "2 — Gaze: Disconnected",
                "3 — Gaze: Toggle stream",
            ]
        cheat += [
            "R — Reset app state",
        ]
        last = [lbl for (_, lbl) in key_log[-6:]]
        # Build surfaces
        pad = 6
        surfs = [small.render(t, True, (240, 240, 240)) for t in cheat]
        if last:
            surfs.append(small.render("", True, (240, 240, 240)))
            surfs.append(small.render("Last: " + " ".join(last), True, (200, 200, 200)))
        if not surfs:
            return
        w = 0
        h = 0
        for s in surfs:
            w = max(w, s.get_width())
            h += s.get_height() + 2
        base_y = HEIGHT - 10
        bg = pygame.Rect(8, base_y - h - pad, w + pad * 2, h + pad)
        pygame.draw.rect(screen, (20, 20, 20), bg, border_radius=6)
        y = base_y - h
        for s in surfs:
            screen.blit(s, (8 + pad, y))
            y += s.get_height() + 2
    
    def draw_button_feedback():
        """Draw visual feedback icon when GPIO button is pressed"""
        now = time.time()
        if now < button_pressed_until:
            # Draw icon in bottom right corner
            icon_size = 40
            margin = 20
            icon_x = WIDTH - icon_size - margin
            icon_y = HEIGHT - icon_size - margin
            
            # Draw circular background
            center_x = icon_x + icon_size // 2
            center_y = icon_y + icon_size // 2
            pygame.draw.circle(screen, (0, 200, 100), (center_x, center_y), icon_size // 2)
            
            # Draw "A" letter in white (event marker button)
            a_font = pygame.font.SysFont(None, 32, bold=True)
            a_text = a_font.render("A", True, (255, 255, 255))
            a_x = center_x - a_text.get_width() // 2
            a_y = center_y - a_text.get_height() // 2
            screen.blit(a_text, (a_x, a_y))
            
            # Draw "Event" label below icon
            label = small.render("Event", True, (200, 200, 200))
            label_x = center_x - label.get_width() // 2
            label_y = icon_y + icon_size + 4
            screen.blit(label, (label_x, label_y))

    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                # Keyboard -> simulated button edges (FLOW)
                KEY_TO_BTN = {
                    pygame.K_w: "BTN_UP",
                    pygame.K_x: "BTN_DOWN",
                    pygame.K_a: "BTN_LEFT",
                    pygame.K_d: "BTN_RIGHT",
                    pygame.K_s: "BTN_CENTER",
                    pygame.K_p: "BTN_A",
                    pygame.K_l: "BTN_B",
                }
                if ev.key in KEY_TO_BTN:
                    k = KEY_TO_BTN[ev.key]
                    if SHOW_KEYS:
                        log_key(k.replace("BTN_", ""))
                    btn_event_q.put(("PRESS", k, "KB"))
                elif SIM_GAZE and ev.key == pygame.K_1:
                    log_key("1")
                    gp.sim_connect()
                elif SIM_GAZE and ev.key == pygame.K_2:
                    log_key("2")
                    gp.sim_disconnect()
                elif SIM_GAZE and ev.key == pygame.K_3:
                    log_key("3")
                    gp.sim_toggle_stream()
                elif ev.key == pygame.K_m:
                    if SHOW_KEYS:
                        log_key("M")
                    running = False
                elif ev.key == pygame.K_r:
                    log_key("R")
                    # Keep reset behavior consistent with RP2040 reset button (BTN_CENTER).
                    btn_event_q.put(("PRESS", "BTN_CENTER", "KB"))
            elif ev.type == pygame.KEYUP:
                # Only BTN_B is hold-to-monitor in the FLOW.
                if ev.key == pygame.K_l:
                    btn_event_q.put(("RELEASE", "BTN_B", "KB"))
            elif ev.type == pygame.MOUSEWHEEL:
                # Heartbeat/serial panel scrolling.
                if serial_log_rect_for_input is not None:
                    mx, my = pygame.mouse.get_pos()
                    if serial_log_rect_for_input.collidepoint(mx, my):
                        line_h = small.get_height() + 2
                        visible_rows = max(1, (serial_log_rect_for_input.height - 40) // line_h)
                        total_lines = len(led_controller.get_serial_log(1000)) if led_controller else 0
                        max_offset = max(0, total_lines - visible_rows)
                        if ev.y > 0:
                            # First upward scroll disables autoscroll and navigates to older lines.
                            if serial_log_autoscroll:
                                serial_log_autoscroll = False
                            serial_log_scroll_offset = min(max_offset, serial_log_scroll_offset + int(ev.y))
                        elif ev.y < 0 and (not serial_log_autoscroll):
                            serial_log_scroll_offset = max(0, serial_log_scroll_offset + int(ev.y))
                            # Re-enable autoscroll when user returns to newest line.
                            if serial_log_scroll_offset == 0:
                                serial_log_autoscroll = True

        # Apply all queued button events (keyboard + RP2040)
        try:
            while True:
                item = btn_event_q.get_nowait()
                if isinstance(item, tuple) and len(item) == 3:
                    kind, btn, src = item
                elif isinstance(item, tuple) and len(item) == 2:
                    kind, btn = item
                    src = "?"
                else:
                    continue
                try:
                    log_button(kind, btn, src)
                except Exception:
                    pass
                handle_button(kind, btn)
        except queue.Empty:
            pass

        # Handle RP2040 BOOT detection events.
        try:
            while True:
                kind, boot_id, uptime_s = rp2040_evt_q.get_nowait()
                if kind != "BOOT" or led_controller is None:
                    continue

                # Case A (default): full re-init including eye tracking state.
                if RP2040_BOOT_REINIT_APP_STATE:
                    reset_app_state()
                    _set_screen("BOOT")
                else:
                    # Case B: keep current pipeline; force OLED resync.
                    try:
                        oled_last.clear()
                    except Exception:
                        pass

                # Reinitialize RP2040 outputs and resync OLED to current state.
                try:
                    led_controller.reinit_outputs(oled_init=True)
                except Exception:
                    pass

                # Ensure OLED shows the current FLOW screen.
                try:
                    led_controller.oled_set_screen(state)
                except Exception:
                    pass

                # Force a sync ASAP (next tick is fine; doing it now reduces visible stale UI).
                try:
                    oled_sync()
                except Exception:
                    pass

                # Send ACK so RP2040 switches from BOOT spam to HB.
                try:
                    led_controller.ack_boot(boot_id)
                except Exception:
                    pass
        except queue.Empty:
            pass

        # Pull gaze samples
        # Show red when disconnected, green when connected
        conn_status = "green" if gp.connected else "red"
        receiving_hint = gp.receiving
        
        # Process all available samples to prevent queue buildup and reduce latency
        # For display, we only need the latest sample, but we process all to avoid accumulation
        samples_processed = 0
        max_samples_per_frame = 100  # Safety limit to prevent blocking on single frame
        queue_size_before = gp.q.qsize()  # Monitor queue size for latency diagnosis
        try:
            while samples_processed < max_samples_per_frame:
                s = gp.q.get_nowait()
                samples_processed += 1
                
                if state == "RECORDING":
                    gaze_samples.append(s)
                
                # Remember last for preview (include validity) - only keep latest for display
                # This reduces processing overhead while ensuring we have the most recent data
                gx_val = max(0.0, min(1.0, s.get("gx", 0.5)))
                gy_val = max(0.0, min(1.0, s.get("gy", 0.5)))
                valid_val = s.get("valid", True)
                last_calib_gaze = (gx_val, gy_val, valid_val)
                
                # Store last eye data for eye view display (always update, not just when active)
                # Fix #4: Clear distance values immediately when validity flags are False
                lpv_val = s.get("lpv", False)
                rpv_val = s.get("rpv", False)
                leyez_val = s.get("leyez") if lpv_val else None  # Clear if invalid
                reyez_val = s.get("reyez") if rpv_val else None  # Clear if invalid
                
                last_eye_data = {
                    "leyez": leyez_val,
                    "reyez": reyez_val,
                    "lpv": lpv_val,
                    "rpv": rpv_val,
                    "lpupild": s.get("lpupild") if lpv_val else None,  # Clear if invalid
                    "rpupild": s.get("rpupild") if rpv_val else None  # Clear if invalid
                }
                last_sample_raw = s
                last_eye_data_time = time.time()  # Update timestamp when new data arrives
        except queue.Empty:
            pass
        
        # Optional: Warn if queue is building up (indicates processing can't keep up)
        # This helps diagnose latency issues
        queue_size_after = gp.q.qsize()
        if queue_size_before > 50:  # Threshold for warning
            print(f"Warning: Queue size is {queue_size_before} samples. This may cause latency. "
                  f"Processed {samples_processed} samples this frame.", file=sys.stderr)

        # Positioning hint screens (not FIND_POSITION): continuously re-evaluate and
        # update the OLED/UI hint screen. Advancement to CALIBRATION stays RIGHT-press only.
        if state in ("MOVE_CLOSER", "MOVE_FARTHER", "IN_POSITION"):
            now = time.time()
            if now >= position_next_eval:
                pos = _position_status_from_eye_data()
                if pos == "Good":
                    desired = "IN_POSITION"
                elif pos == "Near":
                    desired = "MOVE_FARTHER"
                else:
                    desired = "MOVE_CLOSER"
                _set_screen(desired)
                position_next_eval = now + (float(UI_REFRESH_MS) / 1000.0)

        # Sync current screen variables to OLED
        oled_sync()

        # Calibration sequencing
        if state == "CALIBRATION":
            # Handle overlay calibration (if enabled)
            overlay_complete = False
            if using_overlay_calib:
                # Use OpenGaze API v2 calibration
                # Wait for CALIB_RESULT message from Gazepoint (sent after calibration completes)
                calib_result = gp.get_calibration_result()
                if calib_result is not None:
                    # Calibration completed - process result
                    if current_calib_override == "failed":
                        calib_status = "red"
                        calib_quality = "failed"
                        calib_avg_error = None
                        set_info_msg("Calibration failed, try again", dur=3.0)
                    elif current_calib_override == "low":
                        calib_status = "orange"
                        calib_quality = "low"
                        # Use a simulated error value for override
                        calib_avg_error = CALIB_LOW_THRESHOLD - 0.1
                        set_info_msg("Ready, low quality calibration", dur=2.0)
                    else:
                        # Evaluate calibration quality based on result
                        avg_error = calib_result.get('average_error')
                        num_points = calib_result.get('num_points')
                        success = calib_result.get('success')
                        
                        # Handle None values to prevent TypeError
                        if num_points is None:
                            num_points = 0
                        if success is None:
                            success = 0
                        if avg_error is None:
                            avg_error = 0.0
                        
                        # Debug: print calibration result for troubleshooting
                        print(f"Calibration result: success={success}, num_points={num_points}, avg_error={avg_error:.4f}")
                        
                        if success and num_points >= 4:
                            if avg_error < CALIB_OK_THRESHOLD:
                                calib_status = "green"
                                calib_quality = "ok"
                                calib_avg_error = avg_error
                                set_info_msg("Calibration complete", dur=2.0)
                            elif avg_error < CALIB_LOW_THRESHOLD:
                                calib_status = "orange"
                                calib_quality = "low"
                                calib_avg_error = avg_error
                                set_info_msg("Ready, low quality calibration", dur=2.0)
                            else:
                                calib_status = "red"
                                calib_quality = "failed"
                                calib_avg_error = None
                                set_info_msg(f"Calibration failed (error: {avg_error:.2f}), try again", dur=3.0)
                        else:
                            calib_status = "red"
                            calib_quality = "failed"
                            calib_avg_error = None
                            fail_reason = f"success={success}, points={num_points}"
                            set_info_msg(f"Calibration failed ({fail_reason}), try again", dur=3.0)
                    
                    # Hide calibration window
                    gp.calibrate_show(False)
                    # Re-enable data fields after calibration (some devices may reset them)
                    # Run in background thread to avoid blocking UI
                    def _reenable_fields():
                        time.sleep(0.2)  # Small delay before re-enabling
                        gp._enable_gaze_data_fields()
                    threading.Thread(target=_reenable_fields, daemon=True).start()
                    # Reset override for next time
                    current_calib_override = None
                    overlay_complete = True
                    using_overlay_calib = False
                    # If LED calibration is also active, don't change state yet
                    if not using_led_calib:
                        if calib_debug_saved_for_t0 != calib_debug_t0:
                            log_calibration_event("calibration_end", method="OVERLAY", note="overlay result -> READY")
                            save_calibration_logs(calib_debug_events, calib_debug_t0)
                            calib_debug_saved_for_t0 = calib_debug_t0
                        state = "CALIBRATION"
                else:
                    # Still calibrating overlay, wait for CALIB_RESULT message
                    # The server will send CALIB_START_PT and CALIB_RESULT_PT messages for each point
                    # and finally CALIB_RESULT when calibration completes
                    elapsed = time.time() - calib_step_start
                    
                    # If calibration has been running for more than 15 seconds, periodically request result summary
                    # This is a workaround in case the server isn't sending CAL messages properly
                    if elapsed > 15.0:
                        last_check = getattr(start_calibration, '_last_result_check', 0)
                        if elapsed - last_check >= 3.0:  # Check every 3 seconds
                            ok = gp.calibrate_result_summary()
                            log_calibration_event(
                                "poll_result_summary",
                                method="OVERLAY",
                                ok=bool(ok),
                                note=f"elapsed={elapsed:.3f}s",
                            )
                            start_calibration._last_result_check = elapsed
                    
                    # Check if calibration has been running for too long (timeout after 60 seconds)
                    if elapsed > 60.0:
                        set_info_msg("Overlay calibration timeout - please try again", dur=3.0)
                        log_calibration_event("calibration_timeout", method="OVERLAY", note=f"elapsed={elapsed:.3f}s")
                        gp.calibrate_show(False)
                        using_overlay_calib = False
                        # If LED calibration is also disabled, abort
                        if not using_led_calib:
                            current_calib_override = None
                            state = "CALIBRATION"
                            calib_status = "red"
                            calib_quality = "failed"
                            if calib_debug_saved_for_t0 != calib_debug_t0:
                                log_calibration_event("calibration_end", method="OVERLAY", note="timeout abort -> READY")
                                save_calibration_logs(calib_debug_events, calib_debug_t0)
                                calib_debug_saved_for_t0 = calib_debug_t0
            
            # Handle LED-based calibration (if enabled) - uses Gazepoint server-side calibration
            led_complete = False
            if using_led_calib:
                now = time.time()

                # Use real point progression from CAL messages (avoids drift/glitches).
                progress = gp.get_calibration_point_progress() if not SIM_GAZE else None
                pt = progress.get("pt") if progress else None  # 1..5 from Gazepoint
                pt_started_at = progress.get("started_at") if progress else None
                pt_ended_at = progress.get("ended_at") if progress else None
                calx = progress.get("calx") if progress else None
                caly = progress.get("caly") if progress else None

                # If we haven't received CALIB_START_PT yet, keep LEDs off (Gazepoint will send it).
                if pt is None or pt_started_at is None:
                    calib_step = -1
                    if led_controller is not None:
                        led_controller.all_off()
                else:
                    # Detect new point start and reset animation tracking
                    point_key = (pt, pt_started_at)
                    is_new_point = point_key != led_calib_last_point_key
                    if is_new_point:
                        led_calib_last_point_key = point_key
                        calib_led_animation_start.clear()
                        # Debug log: new point started (from CALIB_START_PT)
                        if calib_debug_last_point_key != point_key:
                            calib_debug_last_point_key = point_key
                            log_calibration_event(
                                "calib_point_start",
                                method="LED",
                                pt=pt,
                                calx=calx,
                                caly=caly,
                                pt_started_at=pt_started_at,
                            )

                    # Debug log: point ended (from CALIB_RESULT_PT)
                    if pt_ended_at is not None:
                        end_key = (pt, pt_ended_at)
                        if calib_debug_last_point_end_key != end_key:
                            calib_debug_last_point_end_key = end_key
                            log_calibration_event(
                                "calib_point_end",
                                method="LED",
                                pt=pt,
                                calx=calx,
                                caly=caly,
                                pt_started_at=pt_started_at,
                                pt_ended_at=pt_ended_at,
                            )

                    phase_elapsed = max(0.0, now - pt_started_at)
                    in_delay_phase = phase_elapsed < GP_CALIBRATE_DELAY

                    # Map Gazepoint's current calibration target to the correct physical LED(s).
                    # Prefer CALX/CALY (most reliable); fall back to PT ordering if CALX/CALY unavailable.
                    logical_step = -1  # 0..3 for corners, 4 for center
                    if calx is not None and caly is not None:
                        try:
                            cx = float(calx)
                            cy = float(caly)
                            # Center point is typically at (0.5, 0.5)
                            if abs(cx - 0.5) <= 0.15 and abs(cy - 0.5) <= 0.15:
                                logical_step = 4
                            else:
                                right = cx >= 0.5
                                bottom = cy >= 0.5
                                if right and bottom:
                                    logical_step = 0  # low_right
                                elif (not right) and bottom:
                                    logical_step = 1  # low_left
                                elif (not right) and (not bottom):
                                    logical_step = 2  # high_left
                                else:
                                    logical_step = 3  # high_right
                        except Exception:
                            logical_step = -1
                    else:
                        # Fallback PT ordering (only used if CALX/CALY are missing).
                        # When using CALIBRATE_CLEAR + CALIBRATE_ADDPOINT, PT numbering follows the internal point list order.
                        # Our imposed order is: PT1=low_right, PT2=low_left, PT3=high_left, PT4=high_right
                        pt_map = {1: 0, 2: 1, 3: 2, 4: 3}
                        logical_step = pt_map.get(int(pt), -1)

                    if logical_step == 4:
                        # Center step: light all LEDs.
                        calib_step = 4
                        if led_controller is not None:
                            # Optional blink during the Gazepoint delay phase (to avoid spamming serial, we rely on idempotent calls)
                            if LED_BLINK_DURING_DELAY and in_delay_phase:
                                period = max(0.2, float(LED_BLINK_PERIOD_S))
                                duty = float(LED_BLINK_DUTY)
                                duty = max(0.01, min(0.99, duty))
                                should_on = (phase_elapsed % period) < (period * duty)
                                if should_on:
                                    led_controller.all_on()
                                else:
                                    led_controller.all_off()
                            else:
                                led_controller.all_on()
                    elif 0 <= logical_step < 4 and len(LED_ORDER) >= 4:
                        # Corner step: select the configured physical LED for that corner
                        physical_led = LED_ORDER[logical_step]
                        calib_step = logical_step

                        # Track animation start time for this LED (for stable blinking phase)
                        if physical_led not in calib_led_animation_start:
                            calib_led_animation_start[physical_led] = pt_started_at

                        if led_controller is not None:
                            # Blink only during the delay phase (before sampling), then hold steady during timeout/sampling.
                            # This is implemented to minimize serial traffic: set_led/all_off are idempotent and only send
                            # commands when the state actually changes (i.e., at blink edges or point transitions).
                            if LED_BLINK_DURING_DELAY and in_delay_phase:
                                period = max(0.2, float(LED_BLINK_PERIOD_S))
                                duty = float(LED_BLINK_DUTY)
                                duty = max(0.01, min(0.99, duty))
                                should_on = (phase_elapsed % period) < (period * duty)
                                if should_on:
                                    led_controller.set_led(physical_led)
                                else:
                                    led_controller.all_off()
                            else:
                                led_controller.set_led(physical_led)
                    else:
                        calib_step = -1
                        if led_controller is not None:
                            led_controller.all_off()
                
                # Wait for Gazepoint calibration result (same as overlay calibration)
                calib_result = gp.get_calibration_result()
                if calib_result is not None:
                    # Debug log: calibration result object became available
                    src = calib_result.get("source") if isinstance(calib_result, dict) else None
                    sig = (
                        src,
                        calib_result.get("num_points") if isinstance(calib_result, dict) else None,
                        calib_result.get("average_error") if isinstance(calib_result, dict) else None,
                        calib_result.get("success") if isinstance(calib_result, dict) else None,
                    )
                    if calib_debug_last_result_sig != sig:
                        calib_debug_last_result_sig = sig
                        log_calibration_event(
                            "calib_result_seen",
                            method="LED",
                            calib_result_source=src,
                            valid_points=sig[1],
                            avg_error=sig[2],
                            success=sig[3],
                        )
                    # Calibration completed - process result
                    led_complete = True
                    using_led_calib = False
                    if led_controller is not None:
                        led_controller.all_off()
                    
                    if current_calib_override == "failed":
                        calib_status = "red"
                        calib_quality = "failed"
                        calib_avg_error = None
                        set_info_msg("Calibration failed, try again", dur=3.0)
                    elif current_calib_override == "low":
                        calib_status = "orange"
                        calib_quality = "low"
                        # Use a simulated error value for override
                        calib_avg_error = CALIB_LOW_THRESHOLD - 0.1
                        set_info_msg("Ready, low quality calibration", dur=2.0)
                    else:
                        # Evaluate calibration quality based on Gazepoint result
                        avg_error = calib_result.get('average_error')
                        num_points = calib_result.get('num_points')
                        success = calib_result.get('success')
                        
                        # Handle None values to prevent TypeError
                        if num_points is None:
                            num_points = 0
                        if success is None:
                            success = 0
                        if avg_error is None:
                            avg_error = 0.0
                        
                        # Debug: print calibration result for troubleshooting
                        print(f"LED calibration result: success={success}, num_points={num_points}, avg_error={avg_error:.4f}")
                        
                        if success and num_points >= 4:
                            if avg_error < CALIB_OK_THRESHOLD:
                                calib_status = "green"
                                calib_quality = "ok"
                                calib_avg_error = avg_error
                                set_info_msg("LED calibration complete", dur=2.0)
                            elif avg_error < CALIB_LOW_THRESHOLD:
                                calib_status = "orange"
                                calib_quality = "low"
                                calib_avg_error = avg_error
                                set_info_msg("Ready, low quality calibration", dur=2.0)
                            else:
                                calib_status = "red"
                                calib_quality = "failed"
                                calib_avg_error = None
                                set_info_msg(f"Calibration failed (error: {avg_error:.2f}), try again", dur=3.0)
                        else:
                            calib_status = "red"
                            calib_quality = "failed"
                            calib_avg_error = None
                            fail_reason = f"success={success}, points={num_points}"
                            set_info_msg(f"Calibration failed ({fail_reason}), try again", dur=3.0)
                    
                    # Hide calibration window (should already be hidden, but ensure it)
                    gp.calibrate_show(False)
                    # Re-enable data fields after calibration (some devices may reset them)
                    # Run in background thread to avoid blocking UI
                    def _reenable_fields():
                        time.sleep(0.2)  # Small delay before re-enabling
                        gp._enable_gaze_data_fields()
                    threading.Thread(target=_reenable_fields, daemon=True).start()
                    # Reset override for next time
                    current_calib_override = None
                    # If overlay calibration is also active, don't change state yet
                    if not using_overlay_calib:
                        if calib_debug_saved_for_t0 != calib_debug_t0:
                            log_calibration_event(
                                "calibration_end",
                                method="LED",
                                note="led result -> READY",
                                calib_result_source=src,
                            )
                            save_calibration_logs(calib_debug_events, calib_debug_t0)
                            calib_debug_saved_for_t0 = calib_debug_t0
                        state = "CALIBRATION"
                else:
                    # Still calibrating, wait for CALIB_RESULT message from Gazepoint
                    elapsed = time.time() - calib_step_start
                    
                    # If calibration has been running for more than 15 seconds, periodically request result summary
                    if elapsed > 15.0:
                        last_check = getattr(start_calibration, '_last_result_check', 0)
                        if elapsed - last_check >= 3.0:  # Check every 3 seconds
                            ok = gp.calibrate_result_summary()
                            log_calibration_event(
                                "poll_result_summary",
                                method="LED",
                                ok=bool(ok),
                                note=f"elapsed={elapsed:.3f}s",
                            )
                            start_calibration._last_result_check = elapsed
                    
                    # Check if calibration has been running for too long (timeout after 60 seconds)
                    if elapsed > 60.0:
                        set_info_msg("Calibration timeout - please try again", dur=3.0)
                        log_calibration_event("calibration_timeout", method="LED", note=f"elapsed={elapsed:.3f}s")
                        gp.calibrate_show(False)
                        if led_controller is not None:
                            led_controller.all_off()
                        using_led_calib = False
                        # If overlay calibration is also disabled, abort
                        if not using_overlay_calib:
                            current_calib_override = None
                            state = "CALIBRATION"
                            calib_status = "red"
                            calib_quality = "failed"
                            if calib_debug_saved_for_t0 != calib_debug_t0:
                                log_calibration_event("calibration_end", method="LED", note="timeout abort -> READY")
                                save_calibration_logs(calib_debug_events, calib_debug_t0)
                                calib_debug_saved_for_t0 = calib_debug_t0
            
            # If both calibrations are complete, finalize
            if (overlay_complete or not using_overlay_calib) and (led_complete or not using_led_calib):
                if state == "CALIBRATION":
                    # Both are done, finalize
                    current_calib_override = None
                    state = "CALIBRATION"
                    if calib_debug_saved_for_t0 != calib_debug_t0:
                        log_calibration_event("calibration_end", method=GP_CALIBRATION_METHOD, note="finalize -> CALIBRATION")
                        save_calibration_logs(calib_debug_events, calib_debug_t0)
                        calib_debug_saved_for_t0 = calib_debug_t0

        # Draw
        screen.fill((0, 0, 0))
        draw_status_header()

        # On-screen calibration NeoPixel hints (only for LED-based calibration)
        if state == "CALIBRATION" and GPIO_LED_CALIBRATION_DISPLAY and using_led_calib:
            # Map logical positions to screen coordinates
            # LED_ORDER maps: [low_right, low_left, high_left, high_right] -> physical LED indices
            logical_positions = [
                (int(WIDTH * 0.9), int(HEIGHT * 0.85)),   # low_right (index 0 in LED_ORDER)
                (int(WIDTH * 0.1), int(HEIGHT * 0.85)),    # low_left (index 1 in LED_ORDER)
                (int(WIDTH * 0.1), int(HEIGHT * 0.15)),    # high_left (index 2 in LED_ORDER)
                (int(WIDTH * 0.9), int(HEIGHT * 0.15)),    # high_right (index 3 in LED_ORDER)
            ]
            # Determine if we're on the center point (calib_step == 4)
            is_center_point = (calib_step == 4)
            
            # Draw all LEDs in their configured positions
            # LED_ORDER[i] gives the physical LED index for logical position i
            for logical_idx in range(4):
                if logical_idx < len(LED_ORDER):
                    physical_led_idx = LED_ORDER[logical_idx]
                    pos = logical_positions[logical_idx]
                    # Check if this physical LED is currently active
                    if is_center_point:
                        # Center point: all LEDs are active
                        is_active = True
                    else:
                        # Corner points: check if this LED is in the current sequence step
                        is_active = (calib_step >= 0 and calib_step < 4 and 
                                    len(calib_sequence) > 0 and
                                    calib_sequence[calib_step % len(calib_sequence)] == physical_led_idx)
                    # Use white (255, 255, 255) for active NeoPixel to match hardware default
                    # Use dark gray for inactive pixels
                    color = (255, 255, 255) if is_active else (60, 60, 60)
                    pygame.draw.circle(screen, color, pos, 8)
            
            # Draw center indicator when on center point
            if is_center_point:
                center_pos = (WIDTH // 2, HEIGHT // 2)
                pygame.draw.circle(screen, (255, 255, 255), center_pos, 10)
                pygame.draw.circle(screen, (255, 255, 255), center_pos, 12, 2)
        
        # Hardware LED control during LED-based calibration
        # (LED control during calibration is handled in the calibration loop above)
        if led_controller is not None:
            # Turn off LEDs when not calibrating or when not using LED-based calibration.
            # (When calibrating with LEDs, the calibration loop above is the single source of truth.)
            if state != "CALIBRATION" or not using_led_calib:
                led_controller.all_off()

        # -----------------------
        # Debug dashboard (always-on)
        # -----------------------
        def _draw_panel(rect: pygame.Rect, title: str):
            # Panel background and border
            pygame.draw.rect(screen, (22, 22, 26), rect, border_radius=8)
            pygame.draw.rect(screen, (55, 55, 60), rect, 2, border_radius=8)
            # Title bar strip
            title_rect = pygame.Rect(rect.left + 2, rect.top + 2, rect.width - 4, 22)
            pygame.draw.rect(screen, (35, 35, 42), title_rect, border_radius=6)
            t = small.render(title, True, (220, 220, 230))
            screen.blit(t, (rect.left + 10, rect.top + 5))
            return rect.left + 10, rect.top + 28

        def _draw_lines(x: int, y: int, lines):
            for line in lines:
                if line is None:
                    continue
                s = small.render(str(line), True, (235, 235, 235))
                screen.blit(s, (x, y))
                y += s.get_height() + 2
            return y

        def _draw_pipeline_diagram(rect: pygame.Rect, state_name: str, monitoring: bool):
            """Draw the pipeline as boxes, highlighting the current step."""
            steps = [
                ("BOOT", {"BOOT"}),
                ("POS", {"FIND_POSITION", "MOVE_CLOSER", "MOVE_FARTHER", "IN_POSITION"}),
                ("CAL", {"CALIBRATION"}),
                ("CONF", {"RECORD_CONFIRMATION"}),
                ("REC", {"RECORDING", "STOP_RECORD"}),  # STOP_RECORD is still "recording context"
                ("INF", {"INFERENCE_LOADING"}),
                ("RES", {"RESULTS"}),
            ]
            cur = state_name
            cur_idx = 0
            for i, (_, states) in enumerate(steps):
                if cur in states:
                    cur_idx = i
                    break
            pad_x = 6
            pad_y = 6
            x0 = rect.left + pad_x
            y0 = rect.top + 30  # below title row
            w0 = rect.width - pad_x * 2
            h0 = 26
            n = len(steps)
            gap = 6
            box_w = max(30, (w0 - gap * (n - 1)) // n)
            for i, (label, _) in enumerate(steps):
                bx = x0 + i * (box_w + gap)
                r = pygame.Rect(bx, y0, box_w, h0)
                active = (i == cur_idx)
                bg = (0, 120, 255) if active else (28, 28, 28)
                bd = (200, 220, 255) if active else (70, 70, 70)
                pygame.draw.rect(screen, bg, r, border_radius=6)
                pygame.draw.rect(screen, bd, r, 2, border_radius=6)
                t = small.render(label, True, (15, 15, 15) if active else (220, 220, 220))
                screen.blit(t, (r.centerx - t.get_width() // 2, r.centery - t.get_height() // 2))
            if monitoring:
                pill = pygame.Rect(x0, y0 + h0 + 6, 78, 18)
                pygame.draw.rect(screen, (180, 80, 255), pill, border_radius=9)
                mtxt = small.render("MONITOR", True, (15, 15, 15))
                screen.blit(mtxt, (pill.centerx - mtxt.get_width() // 2, pill.centery - mtxt.get_height() // 2))

        def _shortcuts_lines():
            lines = [
                "W/A/S/D/X -> UP/LEFT/CENTER/RIGHT/DOWN",
                "P -> BTN_A marker (RECORDING)",
                "L hold -> BTN_B monitoring modal",
                "R -> reset app state, M -> quit",
            ]
            if SIM_GAZE:
                lines.append("1/2/3 -> gaze connect/disconnect/stream")
            if SHOW_KEYS and key_log:
                last = [lbl for (_, lbl) in key_log[-8:]]
                lines.append("Recent: " + " ".join(last))
            return lines

        # Panel layout: full width (no side limits), consistent margin
        MARGIN = 16
        GAP = 12
        PANEL_W = max(200, WIDTH - 2 * MARGIN)
        HALF_W = (PANEL_W - GAP) // 2
        TOP_Y = 72
        ROW_H_RAW = 150
        ROW_H_PIPELINE = 130
        ROW_H_EVENTS = 90
        ROW_H_BUTTONS = 90
        ROW_H_SHORTCUTS = 110
        ROW_H1 = max(
            120,
            min(
                220,
                HEIGHT
                - TOP_Y
                - ROW_H_RAW
                - ROW_H_PIPELINE
                - ROW_H_EVENTS
                - ROW_H_BUTTONS
                - ROW_H_SHORTCUTS
                - 6 * MARGIN
                - 80
                - 20,
            ),
        )  # preview + interpreted tracker height
        remaining_h = max(
            80,
            HEIGHT
            - TOP_Y
            - ROW_H1
            - ROW_H_RAW
            - ROW_H_PIPELINE
            - ROW_H_EVENTS
            - ROW_H_BUTTONS
            - ROW_H_SHORTCUTS
            - 6 * MARGIN
            - 20,
        )

        preview_rect = pygame.Rect(MARGIN, TOP_Y, HALF_W, ROW_H1)
        interpreted_rect = pygame.Rect(MARGIN + HALF_W + GAP, TOP_Y, HALF_W, ROW_H1)
        y2 = TOP_Y + ROW_H1 + MARGIN
        raw_rect = pygame.Rect(MARGIN, y2, PANEL_W, ROW_H_RAW)
        y3 = y2 + ROW_H_RAW + MARGIN
        pipeline_rect = pygame.Rect(MARGIN, y3, PANEL_W, ROW_H_PIPELINE)
        y4 = y3 + ROW_H_PIPELINE + MARGIN
        events_rect = pygame.Rect(MARGIN, y4, PANEL_W, ROW_H_EVENTS)
        y5 = y4 + ROW_H_EVENTS + MARGIN
        buttons_rect = pygame.Rect(MARGIN, y5, PANEL_W, ROW_H_BUTTONS)
        y6 = y5 + ROW_H_BUTTONS + MARGIN
        shortcuts_rect = pygame.Rect(MARGIN, y6, PANEL_W, ROW_H_SHORTCUTS)
        y7 = y6 + ROW_H_SHORTCUTS + MARGIN
        serial_log_rect = pygame.Rect(MARGIN, y7, PANEL_W, remaining_h)

        # Preview panel (gaze)
        px, py = _draw_panel(preview_rect, "Gaze preview (normalized)")
        inner = preview_rect.inflate(-16, -36)
        pygame.draw.rect(screen, (30, 30, 30), inner, border_radius=6)
        pygame.draw.rect(screen, (60, 60, 60), inner, 2, border_radius=6)
        # Crosshair
        pygame.draw.line(screen, (60, 60, 60), (inner.centerx - 10, inner.centery), (inner.centerx + 10, inner.centery), 1)
        pygame.draw.line(screen, (60, 60, 60), (inner.centerx, inner.centery - 10), (inner.centerx, inner.centery + 10), 1)
        if last_calib_gaze is not None:
            if len(last_calib_gaze) == 3:
                gx, gy, valid = last_calib_gaze
            else:
                gx, gy = last_calib_gaze
                valid = True
            if valid:
                dx = inner.left + int(float(gx) * inner.width)
                dy = inner.top + int(float(gy) * inner.height)
                dx = max(inner.left, min(inner.right - 1, dx))
                dy = max(inner.top, min(inner.bottom - 1, dy))
                pygame.draw.circle(screen, (0, 200, 255), (dx, dy), 6)
                pygame.draw.circle(screen, (0, 150, 200), (dx, dy), 8, 1)
            else:
                blink_rate = 0.5
                if int(time.time() / blink_rate) % 2 == 0:
                    pygame.draw.circle(screen, (255, 0, 0), (inner.centerx, inner.centery), 8)
                    pygame.draw.circle(screen, (200, 0, 0), (inner.centerx, inner.centery), 10, 2)

        # Interpreted tracker panel
        tx, ty = _draw_panel(interpreted_rect, "Eye tracker (interpreted)")
        pos = _position_status_from_eye_data()
        dist_cm = None
        if last_eye_data:
            try:
                leyez = last_eye_data.get("leyez")
                reyez = last_eye_data.get("reyez")
                z = leyez if leyez is not None else reyez
                if z is not None:
                    dist_cm = get_distance_cm(z)
            except Exception:
                dist_cm = None
        tracker_lines = [
            f"Connected: {bool(gp.connected)}  Receiving: {bool(gp.receiving)}",
            f"Queue size: {gp.q.qsize()}",
            f"Position eval: {pos}  (updates OLED @ {UI_REFRESH_MS}ms)",
        ]
        sample = last_sample_raw or {}
        gx_raw = sample.get("gx")
        gy_raw = sample.get("gy")
        valid_raw = sample.get("valid")
        leyez_raw = sample.get("leyez")
        reyez_raw = sample.get("reyez")
        lpv_raw_u = sample.get("lpv")
        rpv_raw_u = sample.get("rpv")
        lpupild_raw_u = sample.get("lpupild")
        rpupild_raw_u = sample.get("rpupild")
        lcm = get_distance_cm(leyez_raw) if leyez_raw is not None else None
        rcm = get_distance_cm(reyez_raw) if reyez_raw is not None else None
        left_open_u = None if (rpv_raw_u is None and rpupild_raw_u is None) else (bool(rpv_raw_u) if rpupild_raw_u is None else (rpupild_raw_u is not None))
        right_open_u = None if (lpv_raw_u is None and lpupild_raw_u is None) else (bool(lpv_raw_u) if lpupild_raw_u is None else (lpupild_raw_u is not None))
        tracker_lines.extend(
            [
                f"Gaze gx/gy: {_fmt_unknown(gx_raw)} / {_fmt_unknown(gy_raw)}",
                f"Gaze valid: {_fmt_unknown(valid_raw)}",
                f"Distance cm L/R: {_fmt_unknown(lcm)} / {_fmt_unknown(rcm)}",
                f"Eyes open L/R: {_fmt_unknown(left_open_u)} / {_fmt_unknown(right_open_u)}",
                f"Pupil diam m L/R: {_fmt_unknown(lpupild_raw_u)} / {_fmt_unknown(rpupild_raw_u)}",
                f"LPV/RPV: {_fmt_unknown(lpv_raw_u)} / {_fmt_unknown(rpv_raw_u)}",
                f"Last eye data age: {f'{(time.time() - last_eye_data_time):.2f}s' if last_eye_data_time is not None else 'unknown'}",
            ]
        )
        if last_calib_gaze is not None:
            if len(last_calib_gaze) == 3:
                gx, gy, valid = last_calib_gaze
            else:
                gx, gy = last_calib_gaze
                valid = True
            tracker_lines.append(f"gx/gy: {gx:.3f}, {gy:.3f}  valid: {bool(valid)}")
        if last_eye_data:
            lpv_raw = bool(last_eye_data.get("lpv"))
            rpv_raw = bool(last_eye_data.get("rpv"))
            lpupild_raw = last_eye_data.get("lpupild")
            rpupild_raw = last_eye_data.get("rpupild")
            left_open = bool(rpv_raw) if rpupild_raw is None else (rpupild_raw is not None)
            right_open = bool(lpv_raw) if lpupild_raw is None else (lpupild_raw is not None)
            tracker_lines.append(f"eyes open L/R: {bool(left_open)}/{bool(right_open)}  (raw lpv/rpv={lpv_raw}/{rpv_raw})")
            tracker_lines.append(f"pupil diam (m) raw L/R: {lpupild_raw} / {rpupild_raw}")
        if dist_cm is not None:
            tracker_lines.append(f"distance: {dist_cm:.1f} cm")
        if last_eye_data_time is not None:
            tracker_lines.append(f"last eye data: {time.time() - last_eye_data_time:.2f}s ago")
        if last_sample_raw:
            try:
                keys = sorted(list(last_sample_raw.keys()))
                head = ", ".join(keys[:8]) + (" …" if len(keys) > 8 else "")
                tracker_lines.append(f"sample keys({len(keys)}): {head}")
            except Exception:
                pass
        _draw_lines(tx, ty, tracker_lines)

        # Raw tracker panel (all available fields, unknown values explicitly shown)
        rx, ry = _draw_panel(raw_rect, "Eye tracker (raw REC fields)")
        raw_fields = sample.get("raw_fields") if isinstance(sample.get("raw_fields"), dict) else {}
        extra_keys = sorted(k for k in raw_fields.keys() if k not in EYE_TRACKER_RAW_FIELDS)
        raw_keys = list(EYE_TRACKER_RAW_FIELDS) + extra_keys
        raw_items = [(k, _fmt_unknown(raw_fields.get(k))) for k in raw_keys]
        if not raw_items:
            raw_items = [("status", "unknown")]

        def _clip_for_width(text: str, max_px: int) -> str:
            if max_px <= 8:
                return ""
            if small.size(text)[0] <= max_px:
                return text
            out = text
            while out and small.size(out + "...")[0] > max_px:
                out = out[:-1]
            return (out + "...") if out else "..."

        line_h = small.get_height() + 2
        content_h = max(1, raw_rect.height - 34)
        rows = max(1, content_h // line_h)
        cols = max(1, (len(raw_items) + rows - 1) // rows)
        col_w = max(1, (raw_rect.width - 20) // cols)
        for i, (k, v) in enumerate(raw_items):
            c = i // rows
            r = i % rows
            x = rx + c * col_w
            y = ry + r * line_h
            txt = _clip_for_width(f"{k}={v}", col_w - 6)
            surf = small.render(txt, True, (235, 235, 235))
            screen.blit(surf, (x, y))

        # Pipeline panel
        px2, py2 = _draw_panel(pipeline_rect, "Pipeline / state")
        rp2040_ok = (led_controller is not None and getattr(led_controller, "_serial", None) is not None)
        rp2040_alive = bool(led_controller.is_alive(RP2040_HEARTBEAT_TIMEOUT_S)) if led_controller is not None else False
        rp2040_age = led_controller.last_seen_age_s() if led_controller is not None else None
        running_now = using_led_calib or using_overlay_calib
        done_now = (not running_now) and (calib_quality in ("ok", "low", "failed"))
        # Freeze timers once recording has ended (analysis started).
        if session_t0:
            if state in ("RECORDING", "STOP_RECORD"):
                total_t = (time.time() - session_t0)
            else:
                total_t = recording_elapsed_frozen
        else:
            total_t = None

        if event_open and event_started_at is not None:
            if state in ("RECORDING", "STOP_RECORD"):
                ev_t = (time.time() - event_started_at)
            else:
                ev_t = event_elapsed_frozen
        else:
            ev_t = None

        pipeline_step = "POSITIONING" if state in ("FIND_POSITION", "MOVE_CLOSER", "MOVE_FARTHER", "IN_POSITION") else state
        msg_line = None
        if info_msg and time.time() < info_msg_until:
            msg_line = f"Info: {info_msg}"
        _draw_pipeline_diagram(pipeline_rect, state, monitoring_active or state == "MONITORING")
        pipeline_lines = [
            f"STEP: {pipeline_step}  OLED: {state}",
            f"RP2040: ok={bool(rp2040_ok)} alive={bool(rp2040_alive)} age={rp2040_age:.2f}s" if rp2040_age is not None else f"RP2040: ok={bool(rp2040_ok)} alive={bool(rp2040_alive)}",
            f"RP2040 port: {getattr(led_controller, 'serial_port', '') if led_controller else ''}",
            f"Tracker: connected={bool(gp.connected)} receiving={bool(gp.receiving)}",
            f"Calibration: running={bool(running_now)} done={bool(done_now)} quality={calib_quality} step={calib_step}",
            f"Recording total: {_fmt_mmss(total_t) if total_t is not None else '--:--'}  (state={state})",
            f"Event: open={bool(event_open)}  event_t={_fmt_mmss(ev_t) if ev_t is not None else '--:--'}  next={next_event_index}",
            f"Inference: {analysis_values_done}/{analysis_total_values}  page={results_page_index+1 if results_pages else 0}/{len(results_pages) if results_pages else 0}",
            msg_line,
        ]
        _draw_lines(px2, py2 + 58, pipeline_lines)

        # Events panel
        ex, ey = _draw_panel(events_rect, "Events / markers (latest)")
        if not events:
            _draw_lines(ex, ey, ["(none)"])
        else:
            lines = []
            for i in range(max(0, len(events) - 8), len(events)):
                _, elapsed_str, _, label = events[i]
                lines.append(f"{elapsed_str} {label}")
            _draw_lines(ex, ey, lines)

        # Buttons panel
        bx2, by2 = _draw_panel(buttons_rect, "Buttons (latest edges)")
        if not button_log:
            _draw_lines(bx2, by2, ["(none yet)"])
        else:
            lines = []
            for t_ev, src, kind, btn in button_log[-8:]:
                dt = t_ev - app_t0
                lines.append(f"{dt:6.1f}s {src:5s} {kind:7s} {btn}")
            _draw_lines(bx2, by2, lines)

        # Keyboard shortcuts panel
        kx2, ky2 = _draw_panel(shortcuts_rect, "Keyboard shortcuts")
        _draw_lines(kx2, ky2, _shortcuts_lines())

        # Heartbeat / Serial messages log
        sx, sy = _draw_panel(serial_log_rect, "Heartbeat / Serial log")
        serial_log_rect_for_input = serial_log_rect.copy()
        serial_lines_all = led_controller.get_serial_log(1000) if led_controller else []
        line_h = small.get_height() + 2
        visible_rows = max(1, (serial_log_rect.height - 40) // line_h)
        total_lines = len(serial_lines_all)
        max_offset = max(0, total_lines - visible_rows)
        if serial_log_autoscroll:
            serial_log_scroll_offset = 0
        else:
            serial_log_scroll_offset = max(0, min(serial_log_scroll_offset, max_offset))
            if serial_log_scroll_offset == 0:
                serial_log_autoscroll = True

        if serial_log_autoscroll:
            start_idx = max(0, total_lines - visible_rows)
            end_idx = total_lines
        else:
            end_idx = max(0, total_lines - serial_log_scroll_offset)
            start_idx = max(0, end_idx - visible_rows)

        status = f"autoscroll={'on' if serial_log_autoscroll else 'off'}  lines={total_lines}  offset={serial_log_scroll_offset}"
        sy_next = _draw_lines(sx, sy, [status])
        if not serial_lines_all:
            _draw_lines(sx, sy_next, ["(no RP2040 or no messages yet)"])
        else:
            _draw_lines(sx, sy_next, serial_lines_all[start_idx:end_idx])

        # Keep existing overlays (useful while debugging)
        draw_button_feedback()

        pygame.display.flip()
        clock.tick(FPS)

    gp.stop()
    if gpio_monitor:
        gpio_monitor.stop()
    if gpio_eye_view_monitor:
        gpio_eye_view_monitor.stop()
    if led_controller:
        led_controller.stop()
    pygame.quit()


def save_session_logs(events, gaze_samples, session_t0):
    """Save session events and gaze data to CSV files in /logs folder."""
    try:
        # Create logs directory
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        
        # Create session directory with timestamp
        if session_t0:
            session_timestamp = datetime.fromtimestamp(session_t0).strftime("%Y%m%d_%H%M%S")
        else:
            session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        session_dir = logs_dir / session_timestamp
        session_dir.mkdir(exist_ok=True)
        
        # Save events.csv
        events_path = session_dir / "events.csv"
        with open(events_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['elapsed_ms', 'wall_time', 'event'])
            
            # Add session start event
            if session_t0:
                wall_time = datetime.fromtimestamp(session_t0).strftime("%H:%M:%S:%f")[:-3]
                writer.writerow([0, wall_time, 'SESSION_START'])
            
            # Write all events
            for elapsed_ms, elapsed_str, wall_str, label in events:
                writer.writerow([elapsed_ms, wall_str, label])
            
            # Add session end event
            if session_t0:
                end_time = time.time()
                end_elapsed_ms = int((end_time - session_t0) * 1000)
                wall_time = datetime.fromtimestamp(end_time).strftime("%H:%M:%S:%f")[:-3]
                writer.writerow([end_elapsed_ms, wall_time, 'SESSION_END'])
        
        # Save gaze samples (sparse - every 10th sample to limit size)
        gaze_path = session_dir / "gaze.csv"
        with open(gaze_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'gx', 'gy', 'pupil', 'valid'])
            
            for i, sample in enumerate(gaze_samples):
                if i % 10 == 0:  # Save every 10th sample
                    writer.writerow([
                        sample.get('t', 0.0),
                        sample.get('gx', 0.5),
                        sample.get('gy', 0.5),
                        sample.get('pupil', 2.5),
                        sample.get('valid', True)
                    ])
    except Exception as e:
        print(f"Warning: Failed to save session logs: {e}", file=sys.stderr)

def save_results_logs(per_event_scores, global_score, session_t0):
    """Save analysis results to CSV file in /logs folder."""
    try:
        # Create logs directory
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        
        # Find or create session directory
        if session_t0:
            session_timestamp = datetime.fromtimestamp(session_t0).strftime("%Y%m%d_%H%M%S")
        else:
            session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        session_dir = logs_dir / session_timestamp
        session_dir.mkdir(exist_ok=True)
        
        # Save results.csv
        results_path = session_dir / "results.csv"
        with open(results_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['label', 'value'])
            
            # Write global score
            writer.writerow(['GLOBAL', f"{global_score:.6f}"])
            
            # Write per-event scores
            for event_key in sorted(per_event_scores.keys(), key=lambda k: int(k[1:]) if k.startswith("E") else 0):
                writer.writerow([event_key, f"{per_event_scores[event_key]:.6f}"])
    except Exception as e:
        print(f"Warning: Failed to save results logs: {e}", file=sys.stderr)


def save_calibration_logs(calib_events, calib_t0):
    """Save calibration debug logs to logs/<timestamp>/calibration_debug.csv.

    This is intentionally verbose so calibration failures (e.g., early stop after 1-2 points)
    can be diagnosed purely from logs.

    Args:
        calib_events: List[dict] of debug events.
        calib_t0: float UNIX timestamp (time.time()) for the calibration run (or None).
    """
    try:
        # Create logs directory
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)

        # Find or create session directory
        if calib_t0:
            session_timestamp = datetime.fromtimestamp(calib_t0).strftime("%Y%m%d_%H%M%S")
        else:
            session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        session_dir = logs_dir / session_timestamp
        session_dir.mkdir(exist_ok=True)

        calib_path = session_dir / "calibration_debug.csv"

        # Stable base columns; dynamically add extras from events
        base_fields = [
            "wall_time",
            "elapsed_s",
            "event",
            "method",
            "state",
            "pt",
            "calx",
            "caly",
            "pt_started_at",
            "pt_ended_at",
            "phase_elapsed_s",
            "in_delay_phase",
            "gp_calibrate_delay_s",
            "gp_calibrate_timeout_s",
            "calib_result_source",
            "valid_points",
            "avg_error",
            "success",
            "note",
        ]

        extra_fields = []
        for ev in calib_events or []:
            for k in ev.keys():
                if k not in base_fields and k not in extra_fields:
                    extra_fields.append(k)

        fieldnames = base_fields + extra_fields

        with open(calib_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for ev in calib_events or []:
                writer.writerow(ev)

        print(f"Saved calibration debug logs to {calib_path}")
    except Exception as e:
        print(f"Warning: Failed to save calibration debug logs: {e}", file=sys.stderr)


# Global model storage
_xgb_model = None
_xgb_loaded = False

def load_xgb_models():
    """Load XGBoost model from disk. Model outputs a vector: [global_score, score_1, score_2, ..., score_10]."""
    global _xgb_model, _xgb_loaded
    if _xgb_loaded or (xgb is None and joblib is None):
        return
    
    try:
        # Load the single model file
        model_path = MODEL_PATH
        if not os.path.exists(model_path):
            # Try alternative path
            if "/" in MODEL_PATH or "\\" in MODEL_PATH:
                base_dir = os.path.dirname(MODEL_PATH)
            else:
                base_dir = "models"
            model_path = os.path.join(base_dir, "model.xgb")
        
        if os.path.exists(model_path):
            if joblib is not None:
                _xgb_model = joblib.load(model_path)
                print(f"Loaded XGBoost model from {model_path}")
                _xgb_loaded = True
            else:
                print(f"Warning: joblib not available, cannot load model from {model_path}", file=sys.stderr)
        else:
            print(f"Warning: Model file not found: {model_path}", file=sys.stderr)
    except Exception as e:
        print(f"Warning: Failed to load XGBoost model: {e}", file=sys.stderr)
        _xgb_loaded = False

def extract_features(gaze_samples, events, session_t0, aff):
    """
    Extract features from gaze samples and events for XGBoost model.
    Returns a feature vector of 20 values.
    """
    if not gaze_samples:
        return np.zeros(20, dtype=np.float32)
    
    # Convert to numpy arrays for easier processing
    gaze_array = np.array([(s.get('gx', 0.5), s.get('gy', 0.5), s.get('pupil', 2.5), s.get('valid', True)) 
                           for s in gaze_samples])
    
    # Apply calibration transform if available (only for client-side calibration)
    # Note: When using Gazepoint calibration API (LED or OVERLAY), the data is already calibrated
    # by Gazepoint server, so we should not apply Affine2D transform in that case.
    # We only apply Affine2D for client-side calibration (not currently used in LED mode).
    if aff and len(gaze_array) > 0:
        # Check if we should skip Affine2D application
        # If calibration was done via Gazepoint API, data is already calibrated
        # For now, we apply it if aff is not identity (meaning client-side calibration was used)
        # But since LED calibration now uses Gazepoint API, this should rarely be needed
        is_identity = np.allclose(aff.A, np.array([[1, 0, 0], [0, 1, 0]]))
        if not is_identity:
            calibrated_gaze = []
            for gx, gy, pupil, valid in gaze_array:
                if valid:
                    cx, cy = aff.apply(gx, gy)
                    calibrated_gaze.append((cx, cy, pupil, valid))
                else:
                    calibrated_gaze.append((gx, gy, pupil, valid))
            gaze_array = np.array(calibrated_gaze)
    
    gx = gaze_array[:, 0]
    gy = gaze_array[:, 1]
    pupil = gaze_array[:, 2]
    valid = gaze_array[:, 3].astype(bool)
    
    # Calculate features
    valid_samples = gaze_array[valid]
    
    # Basic statistics
    mean_gaze_x = float(np.mean(gx[valid])) if np.any(valid) else 0.5
    mean_gaze_y = float(np.mean(gy[valid])) if np.any(valid) else 0.5
    gaze_variance_x = float(np.var(gx[valid])) if np.any(valid) else 0.0
    gaze_variance_y = float(np.var(gy[valid])) if np.any(valid) else 0.0
    gaze_std_x = float(np.std(gx[valid])) if np.any(valid) else 0.0
    gaze_std_y = float(np.std(gy[valid])) if np.any(valid) else 0.0
    
    # Blink count (invalid samples)
    blink_count = float(np.sum(~valid))
    
    # Validity rate
    validity_rate = float(np.mean(valid)) if len(valid) > 0 else 0.0
    
    # Pupil statistics
    pupil_mean = float(np.mean(pupil[valid])) if np.any(valid) else 2.5
    pupil_std = float(np.std(pupil[valid])) if np.any(valid) else 0.0
    
    # Gaze range
    gaze_range_x = float(np.max(gx[valid]) - np.min(gx[valid])) if np.any(valid) else 0.0
    gaze_range_y = float(np.max(gy[valid]) - np.min(gy[valid])) if np.any(valid) else 0.0
    
    # Calculate velocities (simple difference)
    if len(valid_samples) > 1:
        dx = np.diff(valid_samples[:, 0])
        dy = np.diff(valid_samples[:, 1])
        velocities = np.sqrt(dx**2 + dy**2)
        gaze_velocity_mean = float(np.mean(velocities)) if len(velocities) > 0 else 0.0
        gaze_velocity_std = float(np.std(velocities)) if len(velocities) > 0 else 0.0
    else:
        gaze_velocity_mean = 0.0
        gaze_velocity_std = 0.0
    
    # Fixation and saccade detection (simplified)
    # Fixation: low velocity samples
    if len(valid_samples) > 1:
        threshold = 0.01  # threshold for fixation
        fixations = velocities < threshold
        fixation_count = float(np.sum(fixations))
        fixation_duration = float(np.mean(velocities[fixations])) if np.any(fixations) else 0.0
        
        # Saccades: high velocity samples
        saccades = velocities >= threshold
        saccade_count = float(np.sum(saccades))
        saccade_rate = float(np.mean(velocities[saccades])) if np.any(saccades) else 0.0
    else:
        fixation_count = 0.0
        fixation_duration = 0.0
        saccade_count = 0.0
        saccade_rate = 0.0
    
    # Session duration (from events)
    session_duration = 0.0
    if events and session_t0:
        if len(events) >= 2:
            last_event_time = events[-1][0] / 1000.0  # Convert ms to seconds
            session_duration = last_event_time
    
    total_samples = float(len(gaze_samples))
    
    # Build feature vector (20 features)
    features = np.array([
        mean_gaze_x, mean_gaze_y, gaze_variance_x, gaze_variance_y,
        blink_count, fixation_duration, saccade_rate, session_duration,
        gaze_std_x, gaze_std_y, pupil_mean, pupil_std,
        validity_rate, gaze_range_x, gaze_range_y, gaze_velocity_mean,
        gaze_velocity_std, fixation_count, saccade_count, total_samples
    ], dtype=np.float32)
    
    return features

def run_xgb_results(collected, aff=None, session_t0=None):
    """
    Run XGBoost inference on collected data.
    Model outputs a vector of floats:
      - first 4 values: global results (val1..val4)
      - then 4 values per event slot (E1..E10), in order

    Returns (per_event_vals, global_vals) where:
      - global_vals is a list[float] of length 4
      - per_event_vals maps "E1", "E2", ... to list[float] of length 4
    """
    global _xgb_model
    
    # Load model if not already loaded
    if not _xgb_loaded:
        load_xgb_models()
    
    events = collected.get("events", [])
    gaze_samples = collected.get("gaze", [])
    
    # Extract features
    features = extract_features(gaze_samples, events, session_t0, aff)
    features_2d = features.reshape(1, -1)
    
    per_event = {}
    global_vals = [0.0, 0.0, 0.0, 0.0]
    
    # Get event indices from events
    event_ids = set()
    for _, _, _, lab in events:
        if lab.endswith("_START") or lab.endswith("_STOP"):
            head = lab.split("_")[0]  # e.g. "EVENT3"
            if head.startswith("EVENT"):
                try:
                    event_id = int(head[5:])
                    event_ids.add(event_id)
                except Exception:
                    pass
    
    # Predict using the single model that outputs a vector
    if _xgb_model is not None and _xgb_loaded:
        try:
            # Model outputs: [G1,G2,G3,G4, E1_1..E1_4, E2_1..E2_4, ..., E10_1..E10_4]
            predictions = _xgb_model.predict(features_2d)[0]  # Get first (and only) prediction
            
            # Verify output vector has expected length (44: 4 global + (10*4) event values)
            if len(predictions) < 44:
                raise ValueError(f"Expected 44 outputs, got {len(predictions)}")

            # Global values
            global_vals = [float(max(0.0, min(1.0, v))) for v in predictions[0:4]]
            
            # Extract per-event values for events that exist in the session
            for event_id in sorted(event_ids):
                if event_id >= 1 and event_id <= 10:  # Valid event range
                    key = f"E{event_id}"
                    off = 4 + (event_id - 1) * 4
                    ev = predictions[off : off + 4]
                    per_event[key] = [float(max(0.0, min(1.0, v))) for v in ev]
        except Exception as e:
            print(f"Warning: Model prediction failed: {e}", file=sys.stderr)
            # Fallback to random values
            for event_id in sorted(event_ids):
                key = f"E{event_id}"
                per_event[key] = [float(np.random.rand()) for _ in range(4)]
            global_vals = [float(np.random.rand()) for _ in range(4)]
    else:
        # Fallback to random values if model not available
        for event_id in sorted(event_ids):
            key = f"E{event_id}"
            per_event[key] = [float(np.random.rand()) for _ in range(4)]
        global_vals = [float(np.random.rand()) for _ in range(4)]

    return per_event, global_vals


if __name__ == "__main__":
    main()
