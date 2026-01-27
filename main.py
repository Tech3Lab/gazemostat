import os
import sys
import time
import math
import threading
import queue
import socket
import csv
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
SHOW_KEYS = True     # Show on-screen overlay of pressed keyboard inputs
FULLSCREEN = False    # Run app in fullscreen mode

WIDTH, HEIGHT = 480, 800
FPS = 30
GP_HOST, GP_PORT = "127.0.0.1", 4242
MODEL_PATH = "models/model.xgb"
FEATURE_WINDOW_MS = 1500
CALIB_OK_THRESHOLD = 1.0  # Maximum average error for OK calibration
CALIB_LOW_THRESHOLD = 2.0  # Maximum average error for low quality calibration
CALIB_DELAY = 0.3  # Delay after LED turns on before collecting samples (seconds)
CALIB_DWELL = 0.9  # Duration to collect samples (seconds)
GPIO_CHIP = "/dev/gpiochip0"  # GPIO chip device for LattePanda
GPIO_BTN_MARKER_DEBOUNCE = 0.2  # Marker button debounce time in seconds
GPIO_BTN_EYE_VIEW_SIM = True  # Enable keyboard shortcut for eye view
GPIO_BTN_EYE_VIEW_ENABLE = False  # Enable hardware button for eye view
GPIO_BTN_EYE_VIEW_PIN = 1  # GPIO pin for eye view button (GP1)
GPIO_BTN_EYE_VIEW_DEBOUNCE = 0.2  # Eye view button debounce time in seconds
GPIO_BTN_EYE_VIEW_KEY = "K_v"  # Keyboard shortcut key for eye view (V key)
EYE_VIEW_TIMEOUT = 3.0  # Timeout in seconds before clearing eye view data

# Load config.yaml if it exists
def load_config():
    global GPIO_BTN_MARKER_SIM, GPIO_BTN_MARKER_ENABLE, GPIO_BTN_MARKER_PIN
    global GPIO_LED_CALIBRATION_DISPLAY, GPIO_LED_CALIBRATION_KEYBOARD
    global GP_CALIBRATION_METHOD
    global GPIO_LED_CALIBRATION_ENABLE
    global NEOPIXEL_SERIAL_PORT, NEOPIXEL_SERIAL_BAUD, NEOPIXEL_COUNT, NEOPIXEL_BRIGHTNESS
    global SIM_GAZE, SIM_XGB, SHOW_KEYS, FULLSCREEN, GP_HOST, GP_PORT, MODEL_PATH, FEATURE_WINDOW_MS
    global CALIB_OK_THRESHOLD, CALIB_LOW_THRESHOLD, CALIB_DELAY, CALIB_DWELL
    global GPIO_CHIP, GPIO_BTN_MARKER_DEBOUNCE
    global GPIO_BTN_EYE_VIEW_SIM, GPIO_BTN_EYE_VIEW_ENABLE, GPIO_BTN_EYE_VIEW_PIN
    global GPIO_BTN_EYE_VIEW_DEBOUNCE, GPIO_BTN_EYE_VIEW_KEY, EYE_VIEW_TIMEOUT
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
                    CALIB_OK_THRESHOLD = config.get('calibration_ok_threshold', CALIB_OK_THRESHOLD)
                    CALIB_LOW_THRESHOLD = config.get('calibration_low_threshold', CALIB_LOW_THRESHOLD)
                    CALIB_DELAY = config.get('calib_delay', CALIB_DELAY)
                    CALIB_DWELL = config.get('calib_dwell', CALIB_DWELL)
                    GPIO_CHIP = config.get('gpio_chip', GPIO_CHIP)
                    GPIO_BTN_MARKER_DEBOUNCE = config.get('gpio_btn_marker_debounce', GPIO_BTN_MARKER_DEBOUNCE)
                    # Eye view button configuration
                    GPIO_BTN_EYE_VIEW_SIM = config.get('gpio_btn_eye_view_sim', GPIO_BTN_EYE_VIEW_SIM)
                    GPIO_BTN_EYE_VIEW_ENABLE = config.get('gpio_btn_eye_view_enable', GPIO_BTN_EYE_VIEW_ENABLE)
                    GPIO_BTN_EYE_VIEW_PIN = config.get('gpio_btn_eye_view_pin', GPIO_BTN_EYE_VIEW_PIN)
                    GPIO_BTN_EYE_VIEW_DEBOUNCE = config.get('gpio_btn_eye_view_debounce', GPIO_BTN_EYE_VIEW_DEBOUNCE)
                    GPIO_BTN_EYE_VIEW_KEY = config.get('gpio_btn_eye_view_key', GPIO_BTN_EYE_VIEW_KEY)
                    EYE_VIEW_TIMEOUT = config.get('eye_view_timeout', EYE_VIEW_TIMEOUT)
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
        self.calib_result = None  # Store calibration result summary
        self.calib_result_lock = threading.Lock()  # Thread-safe calibration result access
        self._ack_events = {}  # Dictionary to store ACK events by ID
        self._ack_lock = threading.Lock()  # Lock for ACK events
        self._rec_count = 0  # Counter for REC messages
        self._cal_count = 0  # Counter for CAL messages

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
        return self._send_command('<SET ID="CALIBRATE_CLEAR" />')

    def calibrate_reset(self):
        """Reset the internal list of calibration points to default values"""
        return self._send_command('<SET ID="CALIBRATE_RESET" />')

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
    
    def calibrate_start(self):
        """Start the calibration sequence"""
        return self._send_command('<SET ID="CALIBRATE_START" STATE="1" />', wait_for_ack="CALIBRATE_START")

    def get_calibration_result(self):
        """Get the latest calibration result summary"""
        with self.calib_result_lock:
            return self.calib_result
    
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
                                                
                                                
                                                # Store calibration result if we have data
                                                if avg_error is not None or num_points is not None:
                                                    # Only update if we have a meaningful result (not just 0,0)
                                                    # or if calibration has been running for a while
                                                    with self.calib_result_lock:
                                                        # If we already have a result, only update if new one has points
                                                        if self.calib_result is None or (num_points is not None and num_points > 0):
                                                            success = 1 if (num_points is not None and num_points >= 4) else 0
                                                            self.calib_result = {
                                                                'average_error': avg_error if avg_error is not None else 0.0,
                                                                'num_points': num_points if num_points is not None else 0,
                                                                'success': success
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
                                                        'calib_data': calib_data
                                                    }
                                            elif cal_id in ("CALIB_START_PT", "CALIB_RESULT_PT"):
                                                # Calibration point progress
                                                pass
                                except Exception as e:
                                    pass
                            
                            # Parse REC message: <REC ... BPOGX="..." BPOGY="..." ... />
                            # Try multiple POG fields in order of preference (Section 5)
                            elif b'<REC' in line:
                                self.receiving = True
                                try:
                                    # Try Best POG first (Section 5.7 - average or best available)
                                    gx = get_attr(line_str, 'BPOGX', None)
                                    gy = get_attr(line_str, 'BPOGY', None)
                                    valid = get_attr(line_str, 'BPOGV', None)
                                    
                                    # Fallback to Fixation POG (Section 5.4)
                                    if gx is None:
                                        gx = get_attr(line_str, 'FPOGX', None)
                                        gy = get_attr(line_str, 'FPOGY', None)
                                        valid = get_attr(line_str, 'FPOGV', None)
                                    
                                    # Fallback to Left Eye POG (Section 5.5)
                                    if gx is None:
                                        gx = get_attr(line_str, 'LPOGX', None)
                                        gy = get_attr(line_str, 'LPOGY', None)
                                        valid = get_attr(line_str, 'LPOGV', None)
                                    
                                    # Fallback to Right Eye POG (Section 5.6)
                                    if gx is None:
                                        gx = get_attr(line_str, 'RPOGX', None)
                                        gy = get_attr(line_str, 'RPOGY', None)
                                        valid = get_attr(line_str, 'RPOGV', None)
                                    
                                    # Default values if still None
                                    if gx is None:
                                        gx = 0.5
                                        gy = 0.5
                                        valid = 0
                                    
                                    # Convert validity to boolean
                                    valid = valid > 0.5 if valid is not None else False
                                    
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
                                    
                                    # Extract eye tracking data (LEYEZ, REYEZ, LPV, RPV, LPUPILD, RPUPILD)
                                    leyez = get_attr(line_str, 'LEYEZ', None)
                                    reyez = get_attr(line_str, 'REYEZ', None)
                                    lpv = get_attr(line_str, 'LPV', None)  # Left pupil validity (from ENABLE_SEND_PUPIL_LEFT)
                                    rpv = get_attr(line_str, 'RPV', None)  # Right pupil validity (from ENABLE_SEND_PUPIL_RIGHT)
                                    lpupild = get_attr(line_str, 'LPUPILD', None)  # Left pupil diameter in meters (from ENABLE_SEND_EYE_LEFT)
                                    rpupild = get_attr(line_str, 'RPUPILD', None)  # Right pupil diameter in meters (from ENABLE_SEND_EYE_RIGHT)
                                    
                                    # Convert validity to boolean
                                    lpv = lpv > 0.5 if lpv is not None else False
                                    rpv = rpv > 0.5 if rpv is not None else False
                                    
                                    # Normalize gaze coordinates (Gazepoint uses 0-1 range)
                                    gx = max(0.0, min(1.0, float(gx)))
                                    gy = max(0.0, min(1.0, float(gy)))
                                    
                                    t = time.time()
                                    self._push_sample(t, gx, gy, pupil, valid, leyez=leyez, reyez=reyez, 
                                                     lpv=lpv, rpv=rpv, lpupild=lpupild, rpupild=rpupild)
                                except Exception:
                                    # Fallback on parse error - use center position with invalid flag
                                    t = time.time()
                                    self._push_sample(t, 0.5, 0.5, 2.5, False, leyez=None, reyez=None,
                                                     lpv=False, rpv=False, lpupild=None, rpupild=None)
                            
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
                
                self._push_sample(now, gx, gy, pupil, valid, leyez=leyez, reyez=reyez,
                                 lpv=lpv, rpv=rpv, lpupild=lpupild, rpupild=rpupild)
                time.sleep(1.0 / 60.0)
            else:
                self.receiving = False
                time.sleep(0.05)

    def _push_sample(self, t, gx, gy, pupil, valid, leyez=None, reyez=None, lpv=None, rpv=None, 
                     lpupild=None, rpupild=None):
        sample = {
            "t": t, "gx": gx, "gy": gy, "pupil": pupil, "valid": valid,
            "leyez": leyez, "reyez": reyez, "lpv": lpv, "rpv": rpv,
            "lpupild": lpupild, "rpupild": rpupild
        }
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


class NeoPixelController:
    """Control NeoPixel LEDs via serial communication with microcontroller (Windows/Linux compatible)"""
    def __init__(self, serial_port="", serial_baud=115200, num_pixels=4, brightness=0.3):
        self.serial_port = serial_port
        self.serial_baud = serial_baud
        self.num_pixels = num_pixels
        self.brightness = brightness
        self._serial = None
        self._initialized = False
        self._current_led = -1  # Currently active LED (-1 = all off)
        self._lock = threading.Lock()  # Thread lock for serial access
        
    def _find_serial_port(self):
        """Auto-detect serial port by looking for microcontroller"""
        if not pyserial_available:
            return None
        
        try:
            ports = serial.tools.list_ports.comports()
            
            for port in ports:
                port_name = port.device.upper()  # Normalize to uppercase for Windows
                try:
                    # Try to open port
                    test_serial = serial.Serial(port_name, self.serial_baud, timeout=2.0)
                    
                    # Clear any existing data
                    test_serial.reset_input_buffer()
                    
                    # Wait a bit and read any available data (might be HELLO message)
                    time.sleep(0.5)
                    lines_read = []
                    start_time = time.time()
                    while time.time() - start_time < 1.5:  # Read for up to 1.5 seconds
                        if test_serial.in_waiting > 0:
                            try:
                                line = test_serial.readline().decode('utf-8', errors='ignore').strip()
                                if line:
                                    lines_read.append(line)
                                    if "HELLO" in line.upper() and "NEOPIXEL" in line.upper():
                                        test_serial.close()
                                        return port_name
                            except UnicodeDecodeError:
                                continue
                        time.sleep(0.1)
                    
                    # If no HELLO message, try sending a PING/HELLO command to see if device responds
                    test_serial.reset_input_buffer()
                    test_serial.write(b"PING\n")
                    test_serial.flush()
                    time.sleep(0.3)
                    
                    if test_serial.in_waiting > 0:
                        response = test_serial.readline().decode('utf-8', errors='ignore').strip()
                        if "HELLO" in response.upper() and "NEOPIXEL" in response.upper():
                            # Device responded with HELLO NEOPIXEL - confirmed!
                            test_serial.close()
                            return port_name
                    
                    # Try a harmless command as fallback
                    test_serial.reset_input_buffer()
                    test_serial.write(b"ALL:OFF\n")
                    test_serial.flush()
                    time.sleep(0.3)
                    
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
    
    def _send_command(self, command):
        """Send command to microcontroller via serial"""
        if not self._initialized or self._serial is None:
            return False
        
        try:
            with self._lock:
                cmd_str = command + "\n"
                self._serial.write(cmd_str.encode('utf-8'))
                self._serial.flush()
                return True
        except Exception as e:
            print(f"Warning: Failed to send NeoPixel command '{command}': {e}", file=sys.stderr)
            return False
    
    def start(self):
        """Initialize serial connection to NeoPixel microcontroller"""
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
                        "  - RP2040 sends 'HELLO NEOPIXEL' on boot (or responds to commands)\n"
                    )
                    if available_ports:
                        error_msg += f"  - Available COM ports: {', '.join(available_ports)}\n"
                        error_msg += f"  - Try specifying one in config.yaml: neopixel_serial_port: \"{available_ports[0]}\"\n"
                    else:
                        error_msg += "  - No COM ports found - check USB connection\n"
                    error_msg += "  - Or specify neopixel_serial_port in config.yaml"
                    
                    raise RuntimeError(error_msg)
            else:
                # Normalize port name to uppercase (Windows COM ports are case-sensitive)
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
            
            # Send initialization command with brightness
            brightness_int = int(255 * self.brightness)
            self._send_command(f"INIT:{self.num_pixels}:{brightness_int}")
            
            # Turn off all pixels initially
            self.all_off()
            
            self._initialized = True
            print(f"NeoPixel controller initialized on {port}")
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
        if self._serial is not None:
            try:
                with self._lock:
                    self._serial.close()
            except Exception:
                pass
            self._serial = None
        self._initialized = False
        self._current_led = -1
    
    def set_led(self, led_index, color=(255, 255, 255)):
        """Turn on a specific NeoPixel (0-3) with color and turn off all others"""
        if not self._initialized:
            raise RuntimeError("NeoPixel controller not initialized. Call start() first.")
        
        if led_index < 0 or led_index >= self.num_pixels:
            raise ValueError(f"LED index {led_index} out of range (0-{self.num_pixels-1})")
        
        if led_index == self._current_led:
            return  # Already in desired state
        
        # Apply brightness to color
        r, g, b = color
        r = int(r * self.brightness)
        g = int(g * self.brightness)
        b = int(b * self.brightness)
        
        # Turn off all pixels first, then set the active one
        self._send_command("ALL:OFF")
        time.sleep(0.01)  # Small delay
        self._send_command(f"PIXEL:{led_index}:{r}:{g}:{b}")
        
        self._current_led = led_index
        if led_index >= 0:
            pass
    
    def all_off(self):
        """Turn off all NeoPixels"""
        if not self._initialized:
            return
        
        self._send_command("ALL:OFF")
        self._current_led = -1
    
    def all_on(self, color=(255, 255, 255)):
        """Turn on all NeoPixels with specified color (useful for testing)"""
        if not self._initialized:
            raise RuntimeError("NeoPixel controller not initialized. Call start() first.")
        
        # Apply brightness to color
        r, g, b = color
        r = int(r * self.brightness)
        g = int(g * self.brightness)
        b = int(b * self.brightness)
        
        self._send_command(f"ALL:ON:{r}:{g}:{b}")
        self._current_led = -2  # Special value for "all on"
    
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
        self._send_command(f"BRIGHTNESS:{brightness_int}")
    
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
        - Green: 55-65 cm (optimal range)
        - Yellow: 45-55 cm or 65-75 cm (acceptable)
        - Red: < 45 cm (too close) or > 75 cm (too far)
    """
    if eyez_value is None:
        return (128, 128, 128)  # Gray for no data
    
    # Convert meters to cm for comparison
    # LEYEZ/REYEZ are in meters according to API Section 5.11
    distance_cm = eyez_value * 100.0
    
    # Distance zones:
    # - < 45 cm: Red (too close)
    # - 45-55 cm: Yellow (acceptable)
    # - 55-65 cm: Green (optimal/good)
    # - 65-75 cm: Yellow (acceptable)
    # - > 75 cm: Red (too far)
    if distance_cm < 45.0:
        return (220, 50, 47)  # Red - Too Close (< 45 cm)
    elif distance_cm < 55.0:
        return (255, 200, 0)  # Yellow - Acceptable (45-55 cm)
    elif distance_cm < 65.0:
        return (0, 200, 0)  # Green - Good (55-65 cm)
    elif distance_cm < 75.0:
        return (255, 200, 0)  # Yellow - Acceptable (65-75 cm)
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
    lpv = eye_data.get("lpv", False)  # Left pupil validity (LPV)
    rpv = eye_data.get("rpv", False)  # Right pupil validity (RPV)
    lpupild = eye_data.get("lpupild")  # Left pupil diameter in meters
    rpupild = eye_data.get("rpupild")  # Right pupil diameter in meters
    
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
    
    # Draw LEYEZ value under left eye
    leyez_y = eye_y + eye_radius + 20
    if leyez is not None:
        distance_cm = get_distance_cm(leyez)
        distance_color = get_distance_color(leyez)
        leyez_text = f"LEYEZ: {leyez:.3f}"
        if distance_cm is not None:
            leyez_text += f" ({distance_cm:.1f} cm)"
        leyez_surf = small.render(leyez_text, True, distance_color)
        screen.blit(leyez_surf, (left_eye_x - leyez_surf.get_width() // 2, leyez_y))
    else:
        leyez_surf = small.render("LEYEZ: N/A", True, (128, 128, 128))
        screen.blit(leyez_surf, (left_eye_x - leyez_surf.get_width() // 2, leyez_y))
    
    # Draw REYEZ value under right eye
    reyez_y = eye_y + eye_radius + 20
    if reyez is not None:
        distance_cm = get_distance_cm(reyez)
        distance_color = get_distance_color(reyez)
        reyez_text = f"REYEZ: {reyez:.3f}"
        if distance_cm is not None:
            reyez_text += f" ({distance_cm:.1f} cm)"
        reyez_surf = small.render(reyez_text, True, distance_color)
        screen.blit(reyez_surf, (right_eye_x - reyez_surf.get_width() // 2, reyez_y))
    else:
        reyez_surf = small.render("REYEZ: N/A", True, (128, 128, 128))
        screen.blit(reyez_surf, (right_eye_x - reyez_surf.get_width() // 2, reyez_y))
    
    # Draw pupil diameter values below LEYEZ/REYEZ
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
    # Set up display flags: frameless + optional fullscreen
    display_flags = pygame.NOFRAME
    if FULLSCREEN:
        display_flags |= pygame.FULLSCREEN
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
        led_controller = NeoPixelController(
            serial_port=NEOPIXEL_SERIAL_PORT,
            serial_baud=NEOPIXEL_SERIAL_BAUD,
            num_pixels=NEOPIXEL_COUNT,
            brightness=NEOPIXEL_BRIGHTNESS
        )
        # start() will raise error if library unavailable or initialization fails
        led_controller.start()
    
    # Load XGBoost models at startup (if not in simulation mode)
    if not SIM_XGB:
        load_xgb_models()

    conn_status = "red"
    calib_status = "red"
    receiving_hint = False

    state = "READY"  # READY|CALIBRATING|COLLECTING|ANALYZING|RESULTS
    running = True
    clock = pygame.time.Clock()

    # Calibration
    aff = Affine2D()
    calib_points = []
    target_points = []
    calib_step = -1
    calib_step_start = 0.0
    calib_collect_start = 0.0  # When to start collecting samples (after delay)
    using_led_calib = False  # Flag for LED-based calibration active
    using_overlay_calib = False  # Flag for overlay calibration active
    # CALIB_DELAY and CALIB_DWELL are loaded from config.yaml in load_config()
    calib_quality = "none"  # none|ok|low|failed
    calib_avg_error = None  # Average error value for display (when ok or low)
    current_calib_override = None  # None|'failed'|'low'

    # Collection
    session_t0 = None
    next_task_id = 1
    task_open = False
    events = []  # list of (elapsed_ms, elapsed_str, wall_str, label)
    gaze_samples = []  # store minimal fields for analysis

    # Analyzing/Results
    analyze_t0 = 0.0
    per_task_scores = {}
    global_score = 0.0
    results_scroll = 0.0
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

    def start_calibration(override=None):
        nonlocal state, calib_status, calib_step, calib_step_start, calib_points, target_points, calib_quality, aff, current_calib_override, calib_avg_error, using_led_calib, using_overlay_calib
        if not gp.connected:
            set_info_msg("Connect Gazepoint first")
            return
        state = "CALIBRATING"
        calib_status = "orange"
        calib_quality = "none"
        # Record override result for this calibration session (dev simulation)
        current_calib_override = override
        
        # Initialize flags for which calibration methods are active based on enum
        using_led_calib = GP_CALIBRATION_METHOD in ("LED", "BOTH")
        using_overlay_calib = GP_CALIBRATION_METHOD in ("OVERLAY", "BOTH") and not SIM_GAZE
        
        # Ensure gaze data streaming is enabled (required for both calibration methods)
        if not SIM_GAZE:
            gp._send_command('<SET ID="ENABLE_SEND_DATA" STATE="1" />')
            time.sleep(0.1)
        
        # Initialize LED-based calibration if enabled (use Gazepoint server-side calibration with overlay hidden)
        if using_led_calib:
            # Clear calibration result before starting
            with gp.calib_result_lock:
                gp.calib_result = None
            
            # Clear previous calibration points
            gp.calibrate_clear()
            time.sleep(0.1)
            
            # Reset calibration points to default (5 points)
            gp.calibrate_reset()
            time.sleep(0.1)
            
            # Set calibration timeout based on dwell time (convert seconds to milliseconds)
            timeout_ms = int(CALIB_DWELL * 1000)
            gp.calibrate_timeout(timeout_ms)
            time.sleep(0.1)
            
            # Set calibration delay (convert seconds to milliseconds)
            delay_ms = int(CALIB_DELAY * 1000)
            gp.calibrate_delay(delay_ms)
            time.sleep(0.1)
            
            # Hide calibration window (use LEDs instead of overlay)
            if not gp.calibrate_show(False):
                set_info_msg("Failed to configure calibration", dur=2.0)
                using_led_calib = False
                # If overlay calibration is also disabled, abort
                if not using_overlay_calib:
                    state = "READY"
                    return
            
            # Start the calibration sequence and wait for ACK
            if using_led_calib:
                if gp.calibrate_start():
                    calib_step_start = time.time()  # Record when calibration started
                else:
                    set_info_msg("Failed to start calibration", dur=2.0)
                    gp.calibrate_show(False)  # Ensure calibration window is hidden
                    using_led_calib = False
                    # If overlay calibration is also disabled, abort
                    if not using_overlay_calib:
                        state = "READY"
                        return
        
        # Start overlay calibration if enabled (only works with real hardware)
        if using_overlay_calib:
            # Clear calibration result before starting
            with gp.calib_result_lock:
                gp.calib_result = None
            
            # Clear previous calibration points
            gp.calibrate_clear()
            time.sleep(0.1)
            
            # Reset calibration points to default (5 points)
            gp.calibrate_reset()
            time.sleep(0.1)
            
            # Set calibration timeout (1 second per point)
            gp.calibrate_timeout(1000)
            time.sleep(0.1)
            
            # Set calibration delay (200ms animation delay)
            gp.calibrate_delay(200)
            time.sleep(0.1)
            
            # Show calibration window and wait for ACK
            if not gp.calibrate_show(True):
                set_info_msg("Failed to show calibration window", dur=2.0)
                using_overlay_calib = False
                # If LED calibration is also disabled, abort
                if not using_led_calib:
                    state = "READY"
                    return
            
            # Start the calibration sequence and wait for ACK
            if using_overlay_calib:
                if not gp.calibrate_start():
                    set_info_msg("Failed to start overlay calibration", dur=2.0)
                    gp.calibrate_show(False)  # Hide calibration window
                    using_overlay_calib = False
                    # If LED calibration is also disabled, abort
                    if not using_led_calib:
                        state = "READY"
                        return

    def start_collection():
        nonlocal state, session_t0, next_task_id, task_open, events, gaze_samples
        if not gp.connected:
            set_info_msg("Connect Gazepoint first")
            return
        if calib_quality not in ("ok", "low"):
            set_info_msg("Calibrate first")
            return
        state = "COLLECTING"
        session_t0 = time.time()
        next_task_id = 1
        task_open = False
        events = []
        gaze_samples = []

    def stop_collection_begin_analysis():
        nonlocal state, analyze_t0, per_task_scores, global_score
        state = "ANALYZING"
        analyze_t0 = time.time()
        
        # Save session logs to CSV
        save_session_logs(events, gaze_samples, session_t0)
        
        # Run analysis in a tiny thread to simulate progress
        def _run():
            nonlocal per_task_scores, global_score
            time.sleep(1.2)
            if SIM_XGB:
                # Fake: global = mean of per-task synthetic, per task = simple function of duration
                per_task_scores = {}
                # derive durations from events
                starts = {}
                for _, _, _, lab in events:
                    if lab.endswith("_START"):
                        starts[lab.split("_")[0]] = True
                # simple deterministic values
                for t in range(1, (next_task_id if not task_open else next_task_id) + 1):
                    key = f"T{t}"
                    per_task_scores[key] = round(0.5 + 0.1 * (t % 5), 3)
                if per_task_scores:
                    global_score = round(sum(per_task_scores.values()) / len(per_task_scores), 3)
                else:
                    global_score = 0.0
            else:
                per_task_scores, global_score = run_xgb_results({
                    "events": events,
                    "gaze": gaze_samples,
                }, aff=aff, session_t0=session_t0)
            
            # Save results to CSV
            save_results_logs(per_task_scores, global_score, session_t0)
            
            # flip to results after small delay
            time.sleep(0.3)
            set_results_state()
        threading.Thread(target=_run, daemon=True).start()

    def set_results_state():
        nonlocal state, results_scroll
        state = "RESULTS"
        results_scroll = 0.0

    def marker_toggle():
        nonlocal task_open, next_task_id, button_pressed_until
        if session_t0 is None:
            return
        elapsed_ms, elapsed_str, wall_str = time_strings(session_t0)
        if not task_open:
            label = f"T{next_task_id}_START"
            task_open = True
        else:
            label = f"T{next_task_id}_END"
            task_open = False
            next_task_id += 1
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
        nonlocal session_t0, next_task_id, task_open, events, gaze_samples
        nonlocal analyze_t0, per_task_scores, global_score, results_scroll
        nonlocal info_msg, info_msg_until, last_calib_gaze, using_led_calib, using_overlay_calib
        nonlocal eye_view_active, last_eye_data, last_eye_data_time
        state = "READY"
        calib_status = "red"
        receiving_hint = False
        aff = Affine2D()
        calib_points = []
        target_points = []
        calib_step = -1
        calib_step_start = 0.0
        calib_collect_start = 0.0
        calib_quality = "none"
        calib_avg_error = None
        current_calib_override = None
        using_led_calib = False
        using_overlay_calib = False
        session_t0 = None
        next_task_id = 1
        task_open = False
        events = []
        gaze_samples = []
        analyze_t0 = 0.0
        per_task_scores = {}
        global_score = 0.0
        results_scroll = 0.0
        info_msg = None
        info_msg_until = 0.0
        last_calib_gaze = None
        eye_view_active = False
        last_eye_data = None
        last_eye_data_time = None
        set_info_msg("App state reset", dur=2.0)
    
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
        if state == "CALIBRATING":
            blink_on = (int(time.time() * 2) % 2) == 0
            if blink_on:
                draw_circle(screen, calib_status, (cal_x, 30))
        else:
            draw_circle(screen, calib_status, (cal_x, 30))
        # Middle collecting indicator when collecting
        if state == "COLLECTING":
            mid_x = WIDTH // 2
            # blink at ~2 Hz
            blink_on = (int(time.time() * 2) % 2) == 0
            if blink_on:
                pygame.draw.circle(screen, (220, 50, 47), (mid_x, 30), 12)
            lbl_col = small.render("Collecting", True, (200, 200, 200))
            screen.blit(lbl_col, (mid_x - lbl_col.get_width() // 2, 30 + 16))
        # Labels under circles
        lbl_conn = small.render("Connection", True, (200, 200, 200))
        screen.blit(lbl_conn, (conn_x - lbl_conn.get_width() // 2, 30 + 16))
        lbl_cal = small.render("Calibration", True, (200, 200, 200))
        screen.blit(lbl_cal, (cal_x - lbl_cal.get_width() // 2, 30 + 16))
        # Display calibration quality value if ok or low
        if calib_quality in ("ok", "low") and calib_avg_error is not None:
            error_str = f"{calib_avg_error:.2f}"
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
    key_log = []  # list of (time, label)

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
        cheat = []
        if GPIO_LED_CALIBRATION_KEYBOARD:
            cheat += [
                "Z — Start calibration",
                "X — Start collection",
                "B — Stop collection (analyze)",
            ]
        if GPIO_BTN_MARKER_SIM:
            cheat += [
                "N — Marker (toggle start/end)",
            ]
        if GPIO_BTN_EYE_VIEW_SIM:
            key_name = GPIO_BTN_EYE_VIEW_KEY.replace("K_", "").upper()
            cheat += [
                f"{key_name} — Eye view (hold)",
            ]
        if led_controller is not None:
            cheat += [
                "T — Test all LEDs",
                "Q/W/E/U — Test LED 1/2/3/4",
            ]
        if SIM_GAZE:
            cheat += [
                "1 — Gaze: Connected",
                "2 — Gaze: Disconnected",
                "3 — Gaze: Toggle stream",
                "4 — Start failed calibration (sim)",
                "5 — Start bad calibration (low quality)",
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
            
            # Draw "M" letter in white
            m_font = pygame.font.SysFont(None, 32, bold=True)
            m_text = m_font.render("M", True, (255, 255, 255))
            m_x = center_x - m_text.get_width() // 2
            m_y = center_y - m_text.get_height() // 2
            screen.blit(m_text, (m_x, m_y))
            
            # Draw "Marker" label below icon
            label = small.render("Marker", True, (200, 200, 200))
            label_x = center_x - label.get_width() // 2
            label_y = icon_y + icon_size + 4
            screen.blit(label, (label_x, label_y))

    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if GPIO_LED_CALIBRATION_KEYBOARD and ev.key == pygame.K_z and state == "READY":
                    log_key("Z")
                    start_calibration(override=None)
                elif SIM_GAZE and ev.key == pygame.K_1:
                    log_key("1")
                    gp.sim_connect()
                elif SIM_GAZE and ev.key == pygame.K_2:
                    log_key("2")
                    gp.sim_disconnect()
                elif SIM_GAZE and ev.key == pygame.K_3:
                    log_key("3")
                    gp.sim_toggle_stream()
                elif SIM_GAZE and ev.key == pygame.K_4 and state == "READY":
                    # Start calibration with simulated failed result (same routine, overridden outcome)
                    log_key("4")
                    start_calibration(override="failed")
                elif SIM_GAZE and ev.key == pygame.K_5 and state == "READY":
                    # Start calibration with simulated low-quality result (same routine, overridden outcome)
                    log_key("5")
                    start_calibration(override="low")
                elif GPIO_LED_CALIBRATION_KEYBOARD and ev.key == pygame.K_x and state == "READY":
                    log_key("X")
                    start_collection()
                elif GPIO_BTN_MARKER_SIM and ev.key == pygame.K_n and state == "COLLECTING":
                    log_key("N")
                    marker_toggle()
                elif GPIO_LED_CALIBRATION_KEYBOARD and ev.key == pygame.K_b and state == "COLLECTING":
                    log_key("B")
                    stop_collection_begin_analysis()
                elif GPIO_BTN_EYE_VIEW_SIM:
                    # Parse configurable key from string (e.g., "K_v" -> pygame.K_v)
                    try:
                        key_attr = getattr(pygame, GPIO_BTN_EYE_VIEW_KEY, None)
                        if key_attr is not None and ev.key == key_attr:
                            log_key(GPIO_BTN_EYE_VIEW_KEY.replace("K_", "").upper())
                            set_eye_view(True)
                    except Exception:
                        pass
                elif ev.key == pygame.K_m:
                    if SHOW_KEYS:
                        log_key("M")
                    running = False
                # LED testing shortcuts (for debugging)
                elif ev.key == pygame.K_t and led_controller is not None:
                    # T key: Test all LEDs
                    log_key("T")
                    led_controller.all_on()
                    threading.Thread(target=lambda: (time.sleep(2), led_controller.all_off()), daemon=True).start()
                elif ev.key == pygame.K_q and led_controller is not None:
                    # Q key: Test LED 1
                    log_key("Q")
                    led_controller.test_led(0, duration=1.0)
                elif ev.key == pygame.K_w and led_controller is not None:
                    # W key: Test LED 2
                    log_key("W")
                    led_controller.test_led(1, duration=1.0)
                elif ev.key == pygame.K_e and led_controller is not None:
                    # E key: Test LED 3
                    log_key("E")
                    led_controller.test_led(2, duration=1.0)
                elif ev.key == pygame.K_u and led_controller is not None:
                    # U key: Test LED 4
                    log_key("U")
                    led_controller.test_led(3, duration=1.0)
                elif ev.key == pygame.K_r:
                    log_key("R")
                    reset_app_state()
            elif ev.type == pygame.KEYUP:
                if GPIO_BTN_EYE_VIEW_SIM:
                    # Parse configurable key from string (e.g., "K_v" -> pygame.K_v)
                    try:
                        key_attr = getattr(pygame, GPIO_BTN_EYE_VIEW_KEY, None)
                        if key_attr is not None and ev.key == key_attr:
                            set_eye_view(False)
                    except Exception:
                        pass

        # Pull gaze samples
        # Show red when disconnected, green when connected
        conn_status = "green" if gp.connected else "red"
        receiving_hint = gp.receiving
        try:
            for _ in range(2):
                s = gp.q.get_nowait()
                if state == "COLLECTING":
                    gaze_samples.append(s)
                # Remember last for preview (include validity)
                gx_val = max(0.0, min(1.0, s.get("gx", 0.5)))
                gy_val = max(0.0, min(1.0, s.get("gy", 0.5)))
                valid_val = s.get("valid", True)
                last_calib_gaze = (gx_val, gy_val, valid_val)
                # Store last eye data for eye view display (always update, not just when active)
                last_eye_data = {
                    "leyez": s.get("leyez"),
                    "reyez": s.get("reyez"),
                    "lpv": s.get("lpv"),
                    "rpv": s.get("rpv"),
                    "lpupild": s.get("lpupild"),
                    "rpupild": s.get("rpupild")
                }
                last_eye_data_time = time.time()  # Update timestamp when new data arrives
        except queue.Empty:
            pass

        # Calibration sequencing
        if state == "CALIBRATING":
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
                        state = "READY"
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
                            gp.calibrate_result_summary()
                            start_calibration._last_result_check = elapsed
                    
                    # Check if calibration has been running for too long (timeout after 60 seconds)
                    if elapsed > 60.0:
                        set_info_msg("Overlay calibration timeout - please try again", dur=3.0)
                        gp.calibrate_show(False)
                        using_overlay_calib = False
                        # If LED calibration is also disabled, abort
                        if not using_led_calib:
                            current_calib_override = None
                            state = "READY"
                            calib_status = "red"
                            calib_quality = "failed"
            
            # Handle LED-based calibration (if enabled) - uses Gazepoint server-side calibration
            led_complete = False
            if using_led_calib:
                # Control hardware LEDs during calibration based on Gazepoint's calibration point progression
                # Note: We can't directly know which point Gazepoint is on, so we cycle through LEDs
                # This is a simplification - in practice, Gazepoint manages the calibration sequence
                # We just provide visual targets with LEDs
                # Calculate estimated calibration point based on elapsed time
                elapsed = time.time() - calib_step_start
                total_time_per_point = (CALIB_DELAY + CALIB_DWELL) * 5  # Assume 5 points default
                estimated_point = int((elapsed % total_time_per_point) / (CALIB_DELAY + CALIB_DWELL))
                # Update calib_step for on-screen LED display
                if estimated_point < 4:
                    calib_step = estimated_point
                else:
                    # For 5th point or beyond, set to -1 (no LED highlighted)
                    calib_step = -1
                
                # Control hardware LEDs
                if led_controller is not None:
                    if estimated_point < 4:
                        led_controller.set_led(estimated_point)
                    else:
                        # For 5th point or beyond, cycle back or turn off
                        led_controller.all_off()
                
                # Wait for Gazepoint calibration result (same as overlay calibration)
                calib_result = gp.get_calibration_result()
                if calib_result is not None:
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
                        state = "READY"
                else:
                    # Still calibrating, wait for CALIB_RESULT message from Gazepoint
                    elapsed = time.time() - calib_step_start
                    
                    # If calibration has been running for more than 15 seconds, periodically request result summary
                    if elapsed > 15.0:
                        last_check = getattr(start_calibration, '_last_result_check', 0)
                        if elapsed - last_check >= 3.0:  # Check every 3 seconds
                            gp.calibrate_result_summary()
                            start_calibration._last_result_check = elapsed
                    
                    # Check if calibration has been running for too long (timeout after 60 seconds)
                    if elapsed > 60.0:
                        set_info_msg("Calibration timeout - please try again", dur=3.0)
                        gp.calibrate_show(False)
                        if led_controller is not None:
                            led_controller.all_off()
                        using_led_calib = False
                        # If overlay calibration is also disabled, abort
                        if not using_overlay_calib:
                            current_calib_override = None
                            state = "READY"
                            calib_status = "red"
                            calib_quality = "failed"
            
            # If both calibrations are complete, finalize
            if (overlay_complete or not using_overlay_calib) and (led_complete or not using_led_calib):
                if state == "CALIBRATING":
                    # Both are done, finalize
                    current_calib_override = None
                    state = "READY"

        # Draw
        screen.fill((0, 0, 0))
        draw_status_header()

        # On-screen calibration NeoPixel hints (only for LED-based calibration)
        if state == "CALIBRATING" and GPIO_LED_CALIBRATION_DISPLAY and using_led_calib:
            led_pos = [
                (int(WIDTH * 0.1), int(HEIGHT * 0.15)),
                (int(WIDTH * 0.9), int(HEIGHT * 0.15)),
                (int(WIDTH * 0.9), int(HEIGHT * 0.85)),
                (int(WIDTH * 0.1), int(HEIGHT * 0.85)),
            ]
            for i, p in enumerate(led_pos):
                # Use white (255, 255, 255) for active NeoPixel to match hardware default
                # Use dark gray for inactive pixels
                color = (255, 255, 255) if i == calib_step else (60, 60, 60)
                pygame.draw.circle(screen, color, p, 8)
        
        # Hardware LED control during LED-based calibration
        # (LED control during calibration is handled in the calibration loop above)
        if led_controller is not None:
            if state != "CALIBRATING" or not using_led_calib:
                # Turn off LEDs when not calibrating or when not using LED-based calibration
                if state != "CALIBRATING" or calib_step < 0 or calib_step >= 4:
                    led_controller.all_off()

        if state == "READY":
            # Message logic based on connection and calibration
            now = time.time()
            if info_msg and now < info_msg_until:
                msg = info_msg
            else:
                info_msg = None
                if not gp.connected:
                    msg = "Connect Gazepoint"
                else:
                    if calib_quality == "ok":
                        msg = "Ready"
                    elif calib_quality == "low":
                        msg = "Ready, low quality calibration"
                    elif calib_quality == "failed":
                        msg = "Calibration failed, try again"
                    else:
                        msg = "Start calibration"
            txt = big.render(msg, True, (255, 255, 255))
            
            # Show gaze preview after successful calibration
            if calib_quality in ("ok", "low") and last_calib_gaze is not None:
                # Draw preview square below the message
                preview_y = HEIGHT // 2 + 40
                sq = min(200, WIDTH - 40)
                cx = WIDTH // 2
                rect = pygame.Rect(cx - sq // 2, preview_y, sq, sq)
                pygame.draw.rect(screen, (30, 30, 30), rect, border_radius=6)
                
                # Draw gaze position
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
                
                # Show message above preview
                screen.blit(txt, (WIDTH // 2 - txt.get_width() // 2, preview_y - 60))
            else:
                # Show message in center when no preview
                screen.blit(txt, (WIDTH // 2 - txt.get_width() // 2, HEIGHT // 2 - 20))
        elif state == "CALIBRATING":
            # Only show calibration indicators, not the preview/list squares
            txt = big.render("Calibrating…", True, (255, 255, 255))
            screen.blit(txt, (WIDTH // 2 - txt.get_width() // 2, 70))
        elif state == "COLLECTING":
            # Show collecting label and live marker list on right half
            txt = big.render("Collecting…", True, (255, 255, 255))
            screen.blit(txt, (WIDTH // 2 - txt.get_width() // 2, 70))
            # reuse preview pane for live gaze
            draw_preview_and_markers()
        elif state == "ANALYZING":
            txt = big.render("Calculating…", True, (255, 255, 255))
            screen.blit(txt, (WIDTH // 2 - txt.get_width() // 2, HEIGHT // 2 - 60))
            # progress bar
            bar_w, bar_h = int(WIDTH * 0.7), 18
            bx = WIDTH // 2 - bar_w // 2
            by = HEIGHT // 2
            pygame.draw.rect(screen, (40, 40, 40), (bx, by, bar_w, bar_h), border_radius=6)
            pr = min(1.0, (time.time() - analyze_t0) / 1.5)
            pygame.draw.rect(screen, (80, 180, 80), (bx, by, int(bar_w * pr), bar_h), border_radius=6)
        elif state == "RESULTS":
            txt = big.render(f"Global: {global_score:.3f}", True, (255, 255, 255))
            screen.blit(txt, (WIDTH // 2 - txt.get_width() // 2, 70))
            # Per-task list: only loop if too many to fit; slower loop speed
            y0 = 120
            lines = [f"{k}: {v:.3f}" for k, v in sorted(per_task_scores.items(), key=lambda kv: int(kv[0][1:]))]
            if lines:
                line_h = font.get_height() + 4
                avail_h = HEIGHT - y0 - 20
                visible = max(1, avail_h // line_h)
                if len(lines) > visible:
                    results_scroll = (results_scroll + 0.05) % len(lines)
                    start = int(results_scroll)
                    count = visible
                else:
                    start = 0
                    count = len(lines)
                for i in range(count):
                    line = lines[(start + i) % len(lines)]
                    surf = font.render(line, True, (230, 230, 230))
                    screen.blit(surf, (WIDTH // 2 - 120, y0 + i * line_h))

        # Draw eye view if active (overlay on top of everything)
        if eye_view_active:
            # Draw semi-transparent overlay
            overlay = pygame.Surface((WIDTH, HEIGHT))
            overlay.set_alpha(200)
            overlay.fill((0, 0, 0))
            screen.blit(overlay, (0, 0))
            # Draw eye view
            draw_eye_view(screen, last_eye_data, last_eye_data_time, font, small, big)
        
        # Button feedback and key overlay drawn last
        draw_button_feedback()
        draw_key_overlay()
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

def save_results_logs(per_task_scores, global_score, session_t0):
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
            
            # Write per-task scores
            for task_key in sorted(per_task_scores.keys(), key=lambda k: int(k[1:])):
                writer.writerow([task_key, f"{per_task_scores[task_key]:.6f}"])
    except Exception as e:
        print(f"Warning: Failed to save results logs: {e}", file=sys.stderr)


# Global model storage
_xgb_model = None
_xgb_loaded = False

def load_xgb_models():
    """Load XGBoost model from disk. Model outputs a vector: [global_score, T1, T2, ..., T10]."""
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
    
    # Task duration (from events)
    task_duration = 0.0
    if events and session_t0:
        if len(events) >= 2:
            last_event_time = events[-1][0] / 1000.0  # Convert ms to seconds
            task_duration = last_event_time
    
    total_samples = float(len(gaze_samples))
    
    # Build feature vector (20 features)
    features = np.array([
        mean_gaze_x, mean_gaze_y, gaze_variance_x, gaze_variance_y,
        blink_count, fixation_duration, saccade_rate, task_duration,
        gaze_std_x, gaze_std_y, pupil_mean, pupil_std,
        validity_rate, gaze_range_x, gaze_range_y, gaze_velocity_mean,
        gaze_velocity_std, fixation_count, saccade_count, total_samples
    ], dtype=np.float32)
    
    return features

def run_xgb_results(collected, aff=None, session_t0=None):
    """
    Run XGBoost inference on collected data.
    Model outputs a vector: [global_score, T1, T2, ..., T10]
    Returns (per_task_dict, global_score) where per_task_dict maps "T1", "T2", etc. to scores.
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
    
    per_task = {}
    
    # Get task IDs from events
    tasks = set()
    for _, _, _, lab in events:
        if lab.endswith("_START") or lab.endswith("_END"):
            task_id = int(lab.split("_")[0][1:])  # Extract number from "T1_START"
            tasks.add(task_id)
    
    # Predict using the single model that outputs a vector
    if _xgb_model is not None and _xgb_loaded:
        try:
            # Model outputs: [global_score, T1, T2, ..., T10]
            predictions = _xgb_model.predict(features_2d)[0]  # Get first (and only) prediction
            
            # Verify output vector has expected length (11: 1 global + 10 tasks)
            if len(predictions) < 11:
                raise ValueError(f"Expected 11 outputs, got {len(predictions)}")
            
            # Parse the output vector
            # predictions[0] = global_score
            # predictions[1:] = [T1, T2, ..., T10]
            global_score = float(max(0.0, min(1.0, predictions[0])))  # Clamp to [0, 1]
            
            # Extract per-task scores for tasks that exist in events
            for task_id in sorted(tasks):
                if task_id >= 1 and task_id <= 10:  # Valid task range
                    key = f"T{task_id}"
                    # predictions[task_id] corresponds to T{task_id} (since index 0 is global)
                    task_score = float(max(0.0, min(1.0, predictions[task_id])))
                    per_task[key] = task_score
        except Exception as e:
            print(f"Warning: Model prediction failed: {e}", file=sys.stderr)
            # Fallback to random values
            for task_id in sorted(tasks):
                key = f"T{task_id}"
                per_task[key] = np.random.rand()
            global_score = np.random.rand() if not per_task else float(np.mean(list(per_task.values())))
    else:
        # Fallback to random values if model not available
        for task_id in sorted(tasks):
            key = f"T{task_id}"
            per_task[key] = np.random.rand()
        global_score = np.random.rand() if not per_task else float(np.mean(list(per_task.values())))
    
    return per_task, global_score


if __name__ == "__main__":
    main()
