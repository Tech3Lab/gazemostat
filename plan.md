# Technical Plan — Pygame + Gazepoint + GPIO App (Windows 11)

Goal: A minimal Python/Pygame application that integrates Gazepoint Open API eye-tracking, GPIO-style buttons and LEDs (backed by a simple serial microcontroller on Windows 11), runs an XGBoost model for analysis, and displays status/results on a fixed 480×800 window. In development mode, physical inputs/LEDs are simulated by keyboard and on‑screen indicators.

## 1) Requirements & Constraints
- Runtime: Python 3.9+ (CPython) on Windows 11
- UI: `pygame` with fixed window 480×800, portrait layout
- Eye tracker: Gazepoint Open API (TCP, default host: `127.0.0.1`, port: `4242`) — Windows supported
- GPIO/LEDs on Windows 11: via a simple USB serial microcontroller (e.g., Arduino) acting as a GPIO bridge; when GPIO simulation is enabled, use keyboard + on‑screen LED simulation
- ML: `xgboost` to load a pre‑trained model (binary on disk)
- Dependencies: `pygame`, `numpy`, `xgboost`, `pyserial` (for serial GPIO backend)
- Assets: `logo.jpg` displayed while loading
- Keep code surface small and clear; prefer a single file or a few tiny modules
 - Simulation toggles (independent, top-of-file in `main.py`):
   - `SIM_GPIO = True`  → simulate GPIO via keyboard and on‑screen LEDs
   - `SIM_GAZE = True`  → simulate Gazepoint connection/stream and data
   - `SHOW_KEYS = True` → display on-screen overlay of enabled keyboard inputs as they are pressed

## 2) High‑Level UX Flow
- Boot screen: show `logo.jpg` centered while initializing subsystems (Gazepoint connection, model load).
- Main screen: status header + center content area.
  - Status circles (always visible):
    - Connection (Gazepoint): red=disconnected, orange=connecting, green=connected
    - Calibration: red=not calibrated, orange=in progress, green=calibrated
  - Center text: shows current state, initially “Ready”.
- Actions:
  - Start calibration: First GPIO pin OR `Z` (when GPIO simulation is on) → transitions to Calibration.
  - Start collection session: Second GPIO pin OR `X` (when GPIO simulation is on) → transitions to Collection.
  - Task events: Only a Marker button exists. Each press toggles tasks: first press → `T1_START`, second press → `T1_END`, third → `T2_START`, fourth → `T2_END`, etc.
  - Keyboard (when GPIO simulation on): `N` acts as the Marker toggle. Utility: Stop Collection (`B`) which ends data capture and starts analysis, End session (`M`).
  - Stop collection button (hardware or `B`): immediately stops Gazepoint data capture, transitions to ANALYZING, shows a progress bar labeled “Calculating…”, then displays RESULTS.
  - Main message logic (READY state):
    - If Gazepoint disconnected: "Connect Gazepoint"
    - If connected and not calibrated: "Start calibration"
    - If calibration failed: "Calibration failed, try again"
    - If calibration low quality: "Ready, low quality calibration" (still allows collection)
    - If calibration OK: "Ready"
  - Guarded actions:
    - Starting calibration or collection is blocked when Gazepoint is disconnected → transient message "Connect Gazepoint first"
    - Starting collection before calibration is ready (no OK/low) → transient message "Calibrate first"
- Results: After collection+analysis, render model outputs in center area with concise summary.

## 3) States & Transitions (Minimal FSM)
- BOOT → READY
  - On subsystem init complete, show “Ready”.
- READY → CALIBRATING
  - Trigger: Start Calibration input (GPIO1 or `Z`). Calibration status becomes orange.
- CALIBRATING → READY
  - After 4‑point LED calibration completes, update calibration status to green.
- READY → COLLECTING
  - Trigger: Start Collection input (GPIO2 or `X`). Begin streaming/recording gaze and task events.
- COLLECTING → ANALYZING
  - Trigger: End Session (`M` or dedicated GPIO) or timeout/criteria met.
- ANALYZING → RESULTS → READY
  - Run XGBoost inference; display results; auto‑return to READY or wait for input.
- Any state → ERROR
  - On fatal issues (e.g., model missing). Show overlay with hint, allow return to READY.

Minimalism: One central loop drives rendering; a few background threads handle Gazepoint I/O and (optionally) GPIO callbacks. The FSM is a small enum/int with explicit transitions.

## 4) I/O Backends (Windows 11)
Provide defaults via `config.yaml` (or top‑level constants). Two backends keep code minimal and portable:

- DevKeyboardBackend (no hardware):
  - Inputs: `Z` start calibration, `X` start collection, `N` marker toggle (interprets START/END), `B` stop collection (begin analysis), `M` end session, `R` reset app state
  - LEDs: 4 on‑screen circles (corners) simulate the calibration LEDs

- SerialGPIOBackend (Windows 11 + microcontroller over COM):
  - Hardware: any Arduino‑class board with 7 buttons and 4 LEDs wired; board connects via USB serial
  - Protocol (ASCII, newline‑delimited):
    - PC→MCU: `LED:<idx>:<0|1>` (e.g., `LED:1:1` to turn LED1 on)
    - MCU→PC: `BTN:<name>:<DOWN|UP>` (e.g., `BTN:CALIB:DOWN`)
    - Optional handshake: MCU sends `HELLO <id>` on boot; PC replies `HELLO`
  - Button name mapping: `CALIB`, `COLLECT`, `MARK`, `STOP`, `END` (no separate TASK_START/TASK_END — MARK toggles START/END; `STOP` triggers analysis)
  - LED mapping: indices 1..4 corresponding to calibration corners TL/TR/BR/BL
  - Debounce on MCU; send state changes only
  - PC auto‑detects COM port by scanning for `HELLO` line for a short timeout; fallback to GPIO simulation if not found (when allowed)

Note: This design avoids OS‑specific GPIO libraries on Windows while preserving the physical button/LED requirements.

## 5) Gazepoint Open API Integration
- Connection: TCP to `host:port` (default `127.0.0.1:4242`).
- Protocol: XML messages per line; send `<SET>` to enable streams (e.g., `<SET ID="ENABLE_SEND_DATA" STATE="1"/>`).
- Stream parse: Read loop in a background thread with small queue for decoded samples.
- Automatic connection detection: When `sim_gaze` is `false`, the app continuously attempts to connect to Gazepoint hardware. It will retry every 1 second until a connection is established, allowing the app to automatically detect when Gazepoint Control software becomes available.
- Reconnect: On socket error or connection loss, the app automatically attempts to reconnect every 1 second. Connection status is shown in real-time: red=disconnected, green=connected.
- Data captured: timestamp, gaze X/Y (display‑norm or device coords), pupil, validity flags.
- Thread safety: push to `queue.Queue(maxsize=N)`; drop old samples if full to keep UI responsive.

### Gazepoint Simulation (keyboard)
- Enabled when `SIM_GAZE = True`.
- Default state: Disconnected and not streaming; press `1` to connect, then `3` to toggle Receiving Data.
- Extra dev shortcuts (call the same calibration routine with a simulated outcome parameter):
  - `4` → Start calibration with override result = failed (shows "Calibration failed, try again")
  - `5` → Start calibration with override result = low (shows "Ready, low quality calibration" and keeps calibration circle orange)
- Keyboard shortcuts (avoid clash with Z/X/C/V/B/N/M):
  - `1` → Set connection = Connected (status circle green)
  - `2` → Set connection = Disconnected (status circle red; stop data)
  - `3` → Toggle Receiving Data on/off when connected (pulse/inner dot when on)
- Reset functionality:
  - `R` → Reset app state: returns to READY state, clears all calibration data, collection sessions, events, gaze samples, and analysis results. Useful for quickly restarting a session without closing the app.
- Simulated data generator:
  - Background thread pushes ~60 Hz samples into the same queue API as the real client
  - Fields: timestamp `t`, gaze `gx, gy`, `pupil`, `valid`
  - Normal: `gx, gy` follow a slow screen path (e.g., Lissajous) + small noise
  - During calibration: target current LED corner with noise for realistic centroiding
  - Random brief invalid samples to mimic blinks; slight `pupil` variance
  - Optionally apply a fixed linear transform to produce pseudo-raw coords the calibration can recover

## 6) Calibration (4‑point LED)
- Sequence (about 1s per point):
  1) Turn on LED1 (top‑left), show on‑screen marker when GPIO simulation is on.
  2) Collect gaze samples for window (e.g., 500–1000 ms), average robustly (median/mean w/ validity check).
  3) Repeat for LED2 (top‑right), LED3 (bottom‑right), LED4 (bottom‑left).
- On start: clear previous calibration state — reset transform to identity, set status to orange, set quality to none, and clear any stored calibration samples.
- Compute mapping:
  - Use 2D affine transform from raw gaze coords → screen coords: solve least squares using the 4 pairs.
  - Store coefficients and set calibration status=green.
- Visual feedback: calibration status circle orange during collection, green on completion; on error/insufficient data, flash red and revert to READY.

Calibration UI extras (side-by-side):
- Left half: Instant preview in a square region showing current gaze overlay (e.g., a dot) and optional trace within the square.
- Right half: A live list of Marker button interpretations in the exact format:
  - `XX:XX:XX:XXXms for HH:MM:SS:MS : T1_START`
  - `XX:XX:XX:XXXms for HH:MM:SS:MS : T1_END`
  - `XX:XX:XX:XXXms for HH:MM:SS:MS : TN_START`
  - `XX:XX:XX:XXXms for HH:MM:SS:MS : TN_END`
  Where N increments per task. The first time component is elapsed since the beginning of the current session (calibration), the second is wall clock time. Milliseconds are shown using three digits.

## 7) Collection & Analysis
- Collection:
  - On start collection, clear buffers and begin logging gaze samples and task event timestamps.
  - Buttons: Only `Marker` input exists. Maintain `next_task_id` (start at 1) and `task_open=False`:
    - If `task_open=False` on Marker press: emit `T{next_task_id}_START`, set `task_open=True`.
    - Else: emit `T{next_task_id}_END`, set `task_open=False`, then increment `next_task_id += 1`.
  - Keyboard `N` mirrors the Marker input when GPIO simulation is enabled.
  - Event line formatting for on-screen list (and optionally logs): `ELAPSED for WALL : LABEL` where
    - `ELAPSED = HH:MM:SS:ms` since session start, also shown as `XX:XX:XX:XXXms`
    - `WALL = HH:MM:SS:ms` local time
    - `LABEL ∈ {T1_START, T1_END, T2_START, ...}`
  - Stop collection: on `STOP` (hardware) or `B` (keyboard), end capture and transition to ANALYZING.
    - While ANALYZING, show a centered progress bar with the label "Calculating…" and animate it until results are ready.
- Feature extraction (minimal):
  - Sliding window stats (e.g., last 1–2 seconds): mean/var of calibrated X/Y, blink count (if available), dispersion, saccade rate (basic threshold), fixation duration.
  - Create a fixed‑length vector that matches the model’s expected features.
- XGBoost model:
  - Load at startup from `models/model.xgb` (Booster or sklearn `XGBClassifier`).
  - Development results mode: when `SIM_XGB` (aka `developpement_xg_boost`) is True, generate deterministic fake outputs for a global score and per‑task scores.
  - Real model stub: implement a placeholder function that receives collected data and returns per‑task scores and a global score. Example signature:
    - `def run_xgb_results(collected) -> tuple[dict[str, float], float]: ...`
    - Returns `(per_task, global_score)` where `per_task` maps `T1`,`T2`,... to scores.
  - Display: After analysis completes, transition to RESULTS: show a large Global Score and an auto‑scrolling list of per‑task scores (one line per task) in order of occurrence.
- Output:
  - Optional CSV per session under `data/sessions/` with timestamps, events, features, predictions.

## 8) UI Layout (480×800)
- Header bar (top ~60 px):
  - Left circle: Gazepoint connection (red/orange/green)
  - Right circle: Calibration status (red/orange/green)
  - Streaming hint (dev or real): small inner pulse/dot overlay on the connection circle when data is being received
  - Labels: text under circles — "Connection" and "Calibration"
  - While collecting: add a blinking red circle with label "Collecting" centered between the two
- Body:
  - Centered text: state label (“Ready”, “Calibrating…”, “Collecting…”, “Analyzing…”, results)
  - During CALIBRATING: do not show the preview/list squares; only show calibration indicators and title
  - During COLLECTING: two squares stacked vertically in the center:
    - Top square: live gaze preview (dot/trace)
    - Bottom square: marker list panel with required timestamp format
  - When GPIO simulation is on during calibration: additionally show 4 LED circles at corners
  - During ANALYZING: centered progress bar with the caption "Calculating…", animated fill
  - During RESULTS: show Global Score prominently and a vertically auto‑scrolling list of per‑task scores (`Tn: value`) below
  - Footer overlay (when `SHOW_KEYS`): always-visible cheat-sheet listing all enabled development keyboard shortcuts with descriptions (e.g., `Z — Start calibration`, `X — Start collection`, `N — Marker (toggle)`, `B — Stop/Analyze`, `1/2/3 — Gaze connect/disconnect/toggle stream`). Optionally include a compact "Last:" line with recent keys.
- Footer (optional, small text): key hints when simulations are enabled

## 9) Minimal Project Structure
- Option A (fewest files):
  - `main.py` — entrypoint, pygame loop, FSM, rendering, dev keys, serial backend, calibration, analysis
  - `assets/logo.jpg` — splash image
- Option B (still small, clearer separation):
  - `main.py` — entrypoint, UI + FSM
  - `gp_client.py` — Gazepoint TCP client thread (connect, subscribe, parse, queue)
  - `io_serial.py` — SerialGPIOBackend (COM discover, protocol)
  - `analysis.py` — XGBoost load/infer + feature extraction
  - `config.yaml` — host/port, model path, dev flag, serial port hint

Recommendation: Start with Option A to minimize code; split later if needed.

## 10) Minimal Code Sketch (illustrative only)
```python
import pygame, threading, queue, time

WIDTH, HEIGHT = 480, 800

class Status:
    CONNECT = 'red'     # 'orange'|'green'
    CALIB   = 'red'

def draw_circle(screen, color, pos, r=12):
    pygame.draw.circle(screen, {
        'red': (220,50,47), 'orange': (203,75,22), 'green': (38,139,210)
    }[color], pos, r)

def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    font = pygame.font.SysFont(None, 36)
    # show logo while loading...
    # load model, start gp thread (set Status.CONNECT accordingly)
    # SIM flags at top-of-file control behavior:
    # SIM_GPIO -> enable Z/X/B/N/M (marker toggles tasks)
    # SIM_GAZE -> enable 1/2/3 and data generator
    # SIM_XGB  -> fake XGBoost results during ANALYZING
    state = 'READY'  # READY|CALIBRATING|COLLECTING|ANALYZING|RESULTS
    running = True
    clock = pygame.time.Clock()
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT: running=False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_z and state=='READY':
                    state='CALIBRATING'
                # Gazepoint simulation hotkeys (active when SIM_GAZE)
                elif ev.key == pygame.K_1:
                    Status.CONNECT = 'green'   # connected
                elif ev.key == pygame.K_2:
                    Status.CONNECT = 'red'     # disconnected
                elif ev.key == pygame.K_3:
                    pass  # toggle streaming flag in dev client
                elif ev.key == pygame.K_x and state=='READY':
                    state='COLLECTING'
                elif ev.key == pygame.K_b and state=='COLLECTING':
                    state='ANALYZING'  # stop capture, show progress, then RESULTS
        screen.fill((0,0,0))
        # header circles
        draw_circle(screen, Status.CONNECT, (30,30))
        draw_circle(screen, Status.CALIB, (WIDTH-30,30))
        # center text
        txt = font.render('Ready' if state=='READY' else state.title(), True, (255,255,255))
        screen.blit(txt, (WIDTH//2 - txt.get_width()//2, HEIGHT//2 - 20))
    pygame.display.flip()
    clock.tick(30)
  pygame.quit()

if __name__ == '__main__':
    main()
```

Note: Real code adds keyboard/serial abstraction, calibration routine, gp_client thread, and analysis calls, but stays close to this minimal structure.

## 11) Calibration Routine Details (Minimal)
- LED order: TL → TR → BR → BL; positions map to screen corners with 5–10% inset.
- Each step:
  - Activate corresponding GPIO LED (or highlight on‑screen circle in dev mode)
  - Delay 200 ms for settle, then sample 500–1000 ms of gaze
  - Aggregate robustly and store pair (raw gaze coord, target screen coord)
- Solve 2D affine transform A (6 params) via least squares:
  - `[[x y 1 0 0 0], [0 0 0 x y 1]]` stacked for 4 points → solve for `ax, bx, cx, ay, by, cy`
- Save A in memory; set calibration status=green; turn off all LEDs
 - Dev gaze note: the simulator centers samples on the active target and can apply a known linear transform so the solver recovers it.

## 12) Error Handling & Robustness
- Gazepoint reconnect: When `sim_gaze` is `false`, the app automatically attempts to reconnect every 1 second if the connection fails or is lost. This allows automatic detection when Gazepoint Control software becomes available.
- Serial backend optional: if COM device not found or protocol handshake fails, optionally enable GPIO simulation (if allowed by config)
- Guard missing `logo.jpg` (fallback to solid color)
- Model missing/corrupt: show ERROR, keep app running; allow retry
- Debounce hardware buttons (e.g., 50–100 ms) and ignore repeats
- If real Gazepoint TCP connection fails:
  - When `SIM_GAZE` is True, keep the simulator active so flows remain testable
  - Optionally auto‑enable `SIM_GAZE` on failure (configurable) to keep the app usable
- Reset functionality: Press `R` at any time to reset the app state to READY, clearing all calibration, collection, and analysis data. Useful for quickly restarting without closing the app.

## 13) Configuration
- `config.yaml` keys:
  - `sim_gpio: true|false`
  - `sim_gaze: true|false`
  - `developpement_xg_boost: true|false` (simulate XGBoost results)
  - `dev_show_keys: true|false` (show on-screen keyboard input overlay)
  - `gp_host: 127.0.0.1`
  - `gp_port: 4242`
  - `serial_port: COM3` (optional hint; empty for auto‑discover)
  - `model_path: models/model.xgb`
  - `feature_window_ms: 1500`
Notes:
- Top‑of‑file booleans in `main.py` override config individually:
  - `SIM_GPIO = True|False`
  - `SIM_GAZE = True|False`
  - `SIM_XGB = True|False` (alias for config `developpement_xg_boost`)
  - `SHOW_KEYS = True|False`

## 14) Logging (Optional, Minimal)
- Write CSV per session in `data/sessions/<timestamp>/events.csv`
  - Columns: `elapsed_ms, wall_time, event` where `event` is `Tn_START`/`Tn_END`, `CALIB_START`, `CALIB_END`, `SESSION_START`, `SESSION_END`, `PREDICT:<label>`
  - Gaze traces saved sparsely or based on need to limit size
 - Write predictions in `data/sessions/<timestamp>/results.csv`
   - Columns: `label, value` where `label` is `GLOBAL` or `Tn`

## 15) Acceptance Criteria
- Fixed 480×800 window; shows `logo.jpg` while loading
- Status circles reflect Gazepoint connection and calibration state in real time
- Start calibration via physical button from serial backend or `Z` when GPIO simulation is enabled; 4 LEDs controlled via serial or on‑screen when GPIO simulation is enabled
- Session/task controls via physical buttons or `X/B/N/M/R` when GPIO simulation is enabled; `N` toggles task start/end; `B` stops collection to analyze; `R` resets app state
- Automatic Gazepoint connection detection when `sim_gaze` is `false`; app continuously attempts to connect until successful
- XGBoost model loads and produces a visible result after a collection; result displayed
- ANALYZING shows a "Calculating…" progress bar; RESULTS shows a global score and an auto‑scrolling per‑task score list
- Minimal code footprint with clear structure and graceful fallback when no serial device is present
- Independent simulation toggles:
  - GPIO simulation (keyboard + on‑screen LEDs)
  - Gazepoint simulation (Connected/Disconnected/Receiving Data + gaze samples)
  - XGBoost results simulation (fake per‑task and global values when enabled)
  - Keyboard overlay (when enabled) shows all available dev shortcuts with what they do, plus recent keys

## 16) Windows 11 Specifics
- Installation: `pip install pygame numpy xgboost pyserial`
- COM ports: use `pyserial` to list ports; allow user override via `config.yaml`
- HiDPI: disable scaling if text appears blurry (set `SDL_VIDEO_HIGHDPI=1` if needed)
- Packaging (optional): use `pyinstaller --noconsole --onefile main.py` and include `assets/logo.jpg`

## 17) Next Steps
1) Create `config.yaml` with default pins and flags (sim_gpio, sim_gaze, developpement_xg_boost)
2) Implement Gazepoint client (connect/parse/queue) — ~100 lines (inline or module) + simulator gated by `SIM_GAZE`
3) Implement minimal `main.py` with FSM, status render, dev keys, serial backend, calibration routine, and STOP→ANALYZING→RESULTS flow — ~250–330 lines
4) Add analysis stub and simulator: `run_xgb_results(collected)` and fake generator gated by `SIM_XGB` — ~100–130 lines
5) Implement progress bar UI in ANALYZING state and results view with global + auto‑scrolling per‑task scores
6) Smoke test with simulations; then test with Gazepoint and a simple Arduino serial sketch for buttons/LEDs
