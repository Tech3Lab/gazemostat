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
SIM_GPIO = True      # Keyboard + on-screen LEDs instead of hardware
SIM_GAZE = True      # Keyboard + synthetic gaze stream
SIM_XGB  = True      # Fake XGBoost results
SHOW_KEYS = True     # Show on-screen overlay of pressed keyboard inputs

WIDTH, HEIGHT = 480, 800
FPS = 30
GP_HOST, GP_PORT = "127.0.0.1", 4242
MODEL_PATH = "models/model.xgb"
FEATURE_WINDOW_MS = 1500
CALIB_OK_THRESHOLD = 1.0  # Maximum average error for OK calibration
CALIB_LOW_THRESHOLD = 2.0  # Maximum average error for low quality calibration

# Load config.yaml if it exists
def load_config():
    global SIM_GPIO, SIM_GAZE, SIM_XGB, SHOW_KEYS, GP_HOST, GP_PORT, MODEL_PATH, FEATURE_WINDOW_MS
    global CALIB_OK_THRESHOLD, CALIB_LOW_THRESHOLD
    if yaml is None:
        return
    config_path = "config.yaml"
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                if config:
                    SIM_GPIO = config.get('sim_gpio', SIM_GPIO)
                    SIM_GAZE = config.get('sim_gaze', SIM_GAZE)
                    SIM_XGB = config.get('developpement_xg_boost', SIM_XGB)
                    SHOW_KEYS = config.get('dev_show_keys', SHOW_KEYS)
                    GP_HOST = config.get('gp_host', GP_HOST)
                    GP_PORT = config.get('gp_port', GP_PORT)
                    MODEL_PATH = config.get('model_path', MODEL_PATH)
                    FEATURE_WINDOW_MS = config.get('feature_window_ms', FEATURE_WINDOW_MS)
                    CALIB_OK_THRESHOLD = config.get('calibration_ok_threshold', CALIB_OK_THRESHOLD)
                    CALIB_LOW_THRESHOLD = config.get('calibration_low_threshold', CALIB_LOW_THRESHOLD)
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
        
        with self._sock_lock:
            if self._sock is None:
                if wait_for_ack:
                    with self._ack_lock:
                        self._ack_events.pop(wait_for_ack, None)
                return False
            try:
                self._sock.sendall(cmd.encode('utf-8') + b'\r\n')
                if wait_for_ack and ack_received:
                    # Wait for ACK message
                    if ack_received.wait(timeout=timeout):
                        with self._ack_lock:
                            self._ack_events.pop(wait_for_ack, None)
                        return True
                    else:
                        with self._ack_lock:
                            self._ack_events.pop(wait_for_ack, None)
                        print(f"DEBUG: Timeout waiting for ACK {wait_for_ack}")
                        return False
                return True
            except Exception as e:
                if wait_for_ack:
                    with self._ack_lock:
                        self._ack_events.pop(wait_for_ack, None)
                print(f"DEBUG: Exception sending command: {e}")
                return False

    def calibrate_show(self, show=True):
        """Show or hide the calibration graphical window"""
        state = "1" if show else "0"
        return self._send_command(f'<SET ID="CALIBRATE_SHOW" STATE="{state}"/>', wait_for_ack="CALIBRATE_SHOW")

    def calibrate_clear(self):
        """Clear the internal list of calibration points"""
        return self._send_command('<SET ID="CALIBRATE_CLEAR" STATE="1"/>')

    def calibrate_reset(self):
        """Reset the internal list of calibration points to default values"""
        return self._send_command('<SET ID="CALIBRATE_RESET" STATE="1"/>')

    def calibrate_timeout(self, timeout_ms=1000):
        """Set the duration of each calibration point in milliseconds"""
        # Try without STATE attribute - some versions use direct value
        return self._send_command(f'<SET ID="CALIBRATE_TIMEOUT" VALUE="{timeout_ms}"/>')

    def calibrate_delay(self, delay_ms=200):
        """Set the duration of the animation before calibration at each point begins (milliseconds)"""
        # Try without STATE attribute - some versions use direct value
        return self._send_command(f'<SET ID="CALIBRATE_DELAY" VALUE="{delay_ms}"/>')

    def calibrate_result_summary(self):
        """Request calibration result summary"""
        return self._send_command('<GET ID="CALIBRATE_RESULT_SUMMARY" />')
    
    def calibrate_start(self):
        """Start the calibration sequence"""
        return self._send_command('<SET ID="CALIBRATE_START" STATE="1"/>', wait_for_ack="CALIBRATE_START")

    def get_calibration_result(self):
        """Get the latest calibration result summary"""
        with self.calib_result_lock:
            return self.calib_result

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
                # Use _send_command to wait for ACK
                enable_sent = False
                with self._sock_lock:
                    if self._sock is not None:
                        try:
                            enable_cmd = b'<SET ID="ENABLE_SEND_DATA" STATE="1"/>\r\n'
                            self._sock.sendall(enable_cmd)
                            enable_sent = True
                        except Exception:
                            pass
                if enable_sent:
                    # Wait a bit for ACK (it will be handled by ACK parser)
                    time.sleep(0.2)
                
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
                            
                            # Debug: log all CAL and ACK messages
                            if b'<CAL' in line or b'<ACK' in line:
                                print(f"DEBUG: Raw message: {line_str}")
                            
                            # Log REC messages to see if gaze data is flowing
                            if b'<REC' in line:
                                self._rec_count += 1
                                # Log first 3 REC messages with full raw content to see format
                                if self._rec_count <= 3:
                                    print(f"DEBUG: Raw REC message #{self._rec_count}: {line_str[:300]}")  # First 300 chars
                                # Log every 60th message with parsed details
                                elif self._rec_count % 60 == 0:
                                    # Extract validity to see if eyes are being tracked
                                    try:
                                        # Try different possible validity attribute names
                                        valid_val = get_attr(line_str, 'FPOGV', None)
                                        if valid_val is None:
                                            valid_val = get_attr(line_str, 'FPOGV', None)  # Try without quotes
                                        if valid_val is None:
                                            valid_val = get_attr(line_str, 'VALID', None)
                                        gx = get_attr(line_str, 'FPOGX', None)
                                        gy = get_attr(line_str, 'FPOGY', None)
                                        if valid_val is not None:
                                            valid_str = "VALID" if valid_val > 0.5 else "INVALID"
                                            print(f"DEBUG: Receiving gaze data (REC #{self._rec_count}, {valid_str}, gx={gx:.3f}, gy={gy:.3f})")
                                        else:
                                            print(f"DEBUG: Receiving gaze data (REC #{self._rec_count}, gx={gx}, gy={gy}, no validity found)")
                                    except Exception as e:
                                        print(f"DEBUG: Receiving gaze data (REC message #{self._rec_count}, parse error: {e})")
                            
                            # Log any other XML messages we might be missing
                            if line_str.strip().startswith('<') and b'<CAL' not in line and b'<ACK' not in line and b'<REC' not in line:
                                print(f"DEBUG: Other XML message: {line_str[:200]}")  # Limit length to avoid spam
                            
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
                                            # Signal waiting thread if any
                                            with self._ack_lock:
                                                if ack_id in self._ack_events:
                                                    self._ack_events[ack_id].set()
                                            print(f"DEBUG: Received ACK for {ack_id}")
                                except Exception as e:
                                    print(f"DEBUG: Error parsing ACK: {e}")
                            
                            # Parse CAL messages: <CAL ID="CALIB_START_PT" ... />, <CAL ID="CALIB_RESULT_PT" ... />, <CAL ID="CALIB_RESULT" ... />
                            elif b'<CAL' in line:
                                try:
                                    self._cal_count += 1
                                    print(f"DEBUG: CAL message #{self._cal_count}: {line_str}")
                                    # Extract CAL ID (handle possible leading/trailing spaces)
                                    cal_id_start = line_str.find('ID="')
                                    if cal_id_start != -1:
                                        cal_id_start += 4
                                        cal_id_end = line_str.find('"', cal_id_start)
                                        if cal_id_end != -1:
                                            cal_id = line_str[cal_id_start:cal_id_end].strip()
                                            
                                            if cal_id == "CALIB_RESULT":
                                                # Parse final calibration result
                                                print(f"DEBUG: Received CALIB_RESULT: {line_str}")
                                                
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
                                                
                                                print(f"DEBUG: Parsed CALIB_RESULT - valid_points={valid_points}, avg_error={avg_error:.4f}, success={success}")
                                                
                                                # Store calibration result
                                                with self.calib_result_lock:
                                                    self.calib_result = {
                                                        'average_error': avg_error,
                                                        'num_points': valid_points,
                                                        'success': success,
                                                        'calib_data': calib_data
                                                    }
                                            elif cal_id in ("CALIB_START_PT", "CALIB_RESULT_PT"):
                                                # Log calibration point progress
                                                pt = get_attr(line_str, 'PT', None)
                                                calx = get_attr(line_str, 'CALX', None)
                                                caly = get_attr(line_str, 'CALY', None)
                                                if pt is not None:
                                                    print(f"DEBUG: {cal_id} - Point {pt} at ({calx}, {caly})")
                                                else:
                                                    print(f"DEBUG: {cal_id} - Could not parse PT from: {line_str}")
                                            else:
                                                print(f"DEBUG: Unknown CAL ID: {cal_id} in message: {line_str}")
                                except Exception as e:
                                    import traceback
                                    print(f"DEBUG: Error parsing CAL message: {e}")
                                    print(f"DEBUG: Traceback: {traceback.format_exc()}")
                                    print(f"DEBUG: Full message: {line_str}")
                            
                            # Parse REC message: <REC ... FPOGX="..." FPOGY="..." ... />
                            elif b'<REC' in line:
                                self.receiving = True
                                try:
                                    # Extract FPOGX, FPOGY, FPOGV (validity), PUPILDIA (pupil diameter)
                                    gx = get_attr(line_str, 'FPOGX', 0.5)
                                    gy = get_attr(line_str, 'FPOGY', 0.5)
                                    valid = get_attr(line_str, 'FPOGV', 1.0) > 0.5
                                    pupil = get_attr(line_str, 'PUPILDIA', 2.5)
                                    
                                    # Normalize gaze coordinates (Gazepoint uses 0-1 range)
                                    gx = max(0.0, min(1.0, gx))
                                    gy = max(0.0, min(1.0, gy))
                                    
                                    t = time.time()
                                    self._push_sample(t, gx, gy, pupil, valid)
                                except Exception:
                                    # Fallback on parse error
                                    t = time.time()
                                    self._push_sample(t, 0.5, 0.5, 2.5, True)
                            
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
                self._push_sample(now, gx, gy, pupil, valid)
                time.sleep(1.0 / 60.0)
            else:
                self.receiving = False
                time.sleep(0.05)

    def _push_sample(self, t, gx, gy, pupil, valid):
        try:
            self.q.put_nowait({"t": t, "gx": gx, "gy": gy, "pupil": pupil, "valid": valid})
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


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
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
    CALIB_DWELL = 0.9
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

    # Dev defaults for gaze sim: start disconnected, user can press '1' to connect

    def start_calibration(override=None):
        nonlocal state, calib_status, calib_step, calib_step_start, calib_points, target_points, calib_quality, aff, current_calib_override, calib_avg_error
        if not gp.connected:
            set_info_msg("Connect Gazepoint first")
            return
        state = "CALIBRATING"
        calib_status = "orange"
        calib_quality = "none"
        # Record override result for this calibration session (dev simulation)
        current_calib_override = override
        
        # Use OpenGaze API v2 calibration if not in simulation mode
        if not SIM_GAZE:
            # Ensure gaze data streaming is enabled (required for calibration)
            # This should already be enabled on connection, but verify
            gp._send_command('<SET ID="ENABLE_SEND_DATA" STATE="1"/>')
            time.sleep(0.1)
            
            # Clear previous calibration
            gp.calibrate_clear()
            time.sleep(0.1)
            # Reset calibration points
            gp.calibrate_reset()
            time.sleep(0.1)
            # Set calibration timeout (1000ms per point)
            gp.calibrate_timeout(1000)
            time.sleep(0.1)
            # Set calibration delay (200ms animation delay)
            gp.calibrate_delay(200)
            time.sleep(0.1)
            # Clear calibration result before starting
            with gp.calib_result_lock:
                gp.calib_result = None
            # Show calibration window and wait for ACK
            if gp.calibrate_show(True):
                print("DEBUG: Calibration window shown, waiting for ACK...")
            else:
                print("DEBUG: Failed to send CALIBRATE_SHOW command")
                set_info_msg("Failed to show calibration window", dur=2.0)
                state = "READY"
                return
            # Start the calibration sequence and wait for ACK
            if gp.calibrate_start():
                print("DEBUG: Calibration started, waiting for ACK...")
                calib_step_start = time.time()  # Record when calibration actually started
                print("DEBUG: Waiting for CALIB_RESULT_PT and subsequent calibration points...")
            else:
                print("DEBUG: Failed to send CALIBRATE_START command")
                set_info_msg("Failed to start calibration", dur=2.0)
                gp.calibrate_show(False)  # Hide calibration window
                state = "READY"
                return
        else:
            # Fallback to client-side calibration in simulation mode
            # Clear previous calibration transform/state
            aff = Affine2D()
            calib_points = []
            target_points = []
            calib_step = 0
            calib_step_start = time.time()

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
        nonlocal task_open, next_task_id
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

    def set_info_msg(msg, dur=2.0):
        nonlocal info_msg, info_msg_until
        info_msg = msg
        info_msg_until = time.time() + dur

    def reset_app_state():
        nonlocal state, calib_status, receiving_hint, aff, calib_points, target_points
        nonlocal calib_step, calib_step_start, calib_quality, calib_avg_error, current_calib_override
        nonlocal session_t0, next_task_id, task_open, events, gaze_samples
        nonlocal analyze_t0, per_task_scores, global_score, results_scroll
        nonlocal info_msg, info_msg_until, last_calib_gaze
        state = "READY"
        calib_status = "red"
        receiving_hint = False
        aff = Affine2D()
        calib_points = []
        target_points = []
        calib_step = -1
        calib_step_start = 0.0
        calib_quality = "none"
        calib_avg_error = None
        current_calib_override = None
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
        set_info_msg("App state reset", dur=2.0)

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
        # Top square: preview
        rect = pygame.Rect(cx - sq // 2, top_y, sq, sq)
        pygame.draw.rect(screen, (30, 30, 30), rect, border_radius=6)
        if last_calib_gaze is not None:
            gx, gy = last_calib_gaze
            dx = rect.left + int(gx * rect.width)
            dy = rect.top + int(gy * rect.height)
            pygame.draw.circle(screen, (0, 200, 255), (dx, dy), 5)
        # Bottom square: marker list
        list_rect = pygame.Rect(cx - sq // 2, rect.bottom + spacing, sq, sq)
        pygame.draw.rect(screen, (20, 20, 20), list_rect, border_radius=6)
        y = list_rect.top + 8
        for i in range(max(0, len(events) - 14), len(events)):
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
        if SIM_GPIO:
            cheat += [
                "Z — Start calibration",
                "X — Start collection",
                "N — Marker (toggle start/end)",
                "B — Stop collection (analyze)",
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

    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if SIM_GPIO and ev.key == pygame.K_z and state == "READY":
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
                elif SIM_GPIO and ev.key == pygame.K_x and state == "READY":
                    log_key("X")
                    start_collection()
                elif SIM_GPIO and ev.key == pygame.K_n and state == "COLLECTING":
                    log_key("N")
                    marker_toggle()
                elif SIM_GPIO and ev.key == pygame.K_b and state == "COLLECTING":
                    log_key("B")
                    stop_collection_begin_analysis()
                elif ev.key == pygame.K_m:
                    if SHOW_KEYS:
                        log_key("M")
                    running = False
                elif ev.key == pygame.K_r:
                    log_key("R")
                    reset_app_state()
                elif ev.key == pygame.K_r:
                    log_key("R")
                    reset_app_state()

        # Pull gaze samples
        # Show red when disconnected, green when connected
        conn_status = "green" if gp.connected else "red"
        receiving_hint = gp.receiving
        try:
            for _ in range(2):
                s = gp.q.get_nowait()
                if state == "COLLECTING":
                    gaze_samples.append(s)
                # Remember last for preview
                last_calib_gaze = (max(0.0, min(1.0, s.get("gx", 0.5))), max(0.0, min(1.0, s.get("gy", 0.5))))
        except queue.Empty:
            pass

        # Calibration sequencing
        if state == "CALIBRATING":
            if not SIM_GAZE:
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
                    # Reset override for next time
                    current_calib_override = None
                    state = "READY"
                else:
                    # Still calibrating, wait for CALIB_RESULT message
                    # The server will send CALIB_START_PT and CALIB_RESULT_PT messages for each point
                    # and finally CALIB_RESULT when calibration completes
                    elapsed = time.time() - calib_step_start
                    
                    # If calibration has been running for more than 15 seconds, periodically request result summary
                    # This is a workaround in case the server isn't sending CAL messages properly
                    if elapsed > 15.0:
                        last_check = getattr(start_calibration, '_last_result_check', 0)
                        if elapsed - last_check >= 3.0:  # Check every 3 seconds
                            print(f"DEBUG: Calibration running for {elapsed:.1f}s, requesting result summary...")
                            gp.calibrate_result_summary()
                            start_calibration._last_result_check = elapsed
                    
                    # Check if calibration has been running for too long (timeout after 60 seconds)
                    if elapsed > 60.0:
                        print(f"DEBUG: Calibration timeout after {elapsed:.1f}s - no CALIB_RESULT received")
                        set_info_msg("Calibration timeout - please try again", dur=3.0)
                        gp.calibrate_show(False)
                        current_calib_override = None
                        state = "READY"
                        calib_status = "red"
                        calib_quality = "failed"
            else:
                # Client-side calibration for simulation mode
                if calib_step == 0:
                    target = (0.1, 0.1)
                elif calib_step == 1:
                    target = (0.9, 0.1)
                elif calib_step == 2:
                    target = (0.9, 0.9)
                elif calib_step == 3:
                    target = (0.1, 0.9)
                else:
                    target = None

                # collect samples during dwell
                if target is not None:
                    tnow = time.time()
                    if tnow - calib_step_start < CALIB_DWELL:
                        if last_calib_gaze is not None:
                            calib_points.append(last_calib_gaze)
                            target_points.append(target)
                    else:
                        calib_step += 1
                        calib_step_start = tnow
                else:
                    # Finalize calibration outcome
                    if current_calib_override == "failed":
                        calib_status = "red"
                        calib_quality = "failed"
                        set_info_msg("Calibration failed, try again", dur=3.0)
                    elif current_calib_override == "low":
                        # Simulate a successful but low-quality calibration regardless of sample count
                        calib_status = "orange"
                        calib_quality = "low"
                    else:
                        if len(calib_points) >= 4:
                            # Fit simple affine raw->screen
                            aff.fit(calib_points[:4], target_points[:4])
                            calib_status = "green"
                            calib_quality = "ok"
                        else:
                            # In development, succeed even without enough samples
                            calib_status = "green"
                            calib_quality = "ok"
                    # Reset override for next time
                    current_calib_override = None
                    state = "READY"

        # Draw
        screen.fill((0, 0, 0))
        draw_status_header()

        # On-screen calibration LED hints in SIM_GPIO
        if state == "CALIBRATING" and SIM_GPIO:
            led_pos = [
                (int(WIDTH * 0.1), int(HEIGHT * 0.15)),
                (int(WIDTH * 0.9), int(HEIGHT * 0.15)),
                (int(WIDTH * 0.9), int(HEIGHT * 0.85)),
                (int(WIDTH * 0.1), int(HEIGHT * 0.85)),
            ]
            for i, p in enumerate(led_pos):
                color = (0, 255, 0) if i == calib_step else (60, 60, 60)
                pygame.draw.circle(screen, color, p, 8)

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

        # Key overlay drawn last
        draw_key_overlay()
        pygame.display.flip()
        clock.tick(FPS)

    gp.stop()
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
    
    # Apply calibration transform if available
    if aff and len(gaze_array) > 0:
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
