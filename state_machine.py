import time
from typing import Protocol, Optional, List, Dict, Any

class AppInterface(Protocol):
    # Screen and UI
    def set_screen(self, screen_name: str) -> None: ...
    def oled_set_str(self, var_name: str, value: str) -> None: ...
    def oled_set_bool(self, var_name: str, value: bool) -> None: ...
    def oled_set_u8(self, var_name: str, value: int) -> None: ...
    def set_info_msg(self, msg: str, dur: float) -> None: ...
    
    # Calibration
    def check_existing_calibration(self) -> None: ...
    def start_calibration(self, override: Optional[str] = None) -> None: ...
    
    # Recording / Events
    def start_collection(self) -> None: ...
    def stop_collection(self) -> None: ...
    def marker_toggle(self) -> None: ...
    
    # App State Resets
    def reset_app_state(self) -> None: ...
    
    # Getters for current state
    def get_position_status(self) -> str: ...
    def get_calib_quality(self) -> str: ...
    def is_calib_running(self) -> bool: ...
    def get_session_time(self) -> Optional[float]: ...
    def get_event_time(self) -> Optional[float]: ...
    def is_event_open(self) -> bool: ...
    def get_next_event_index(self) -> int: ...
    def get_eye_data(self) -> Dict[str, Any]: ...
    def get_calib_gaze(self) -> List[float]: ...
    
    # Inference
    def get_analysis_progress(self) -> tuple[int, int, float]: ... # done, total, sec_per_val
    
    # Results
    def get_results_pages(self) -> List[Dict[str, Any]]: ...
    def get_results_page_index(self) -> int: ...
    def set_results_page_index(self, index: int) -> None: ...


class State:
    def __init__(self, app: AppInterface, manager: 'StateMachineManager'):
        self.app = app
        self.manager = manager

    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    def on_button(self, btn: str) -> None:
        pass

    def on_update(self) -> None:
        pass


class BootState(State):
    def on_enter(self):
        self.app.set_screen("BOOT")

    def on_button(self, btn: str):
        if btn == "BTN_RIGHT":
            self.manager.transition_to("FIND_POSITION")


class FindPositionState(State):
    def on_enter(self):
        self.app.set_screen("FIND_POSITION")

    def on_button(self, btn: str):
        if btn == "BTN_RIGHT":
            pos = self.app.get_position_status()
            if pos == "Good":
                self.manager.transition_to("IN_POSITION")
            elif pos == "Near":
                self.manager.transition_to("MOVE_FARTHER")
            else:
                self.manager.transition_to("MOVE_CLOSER")


class MoveCloserState(State):
    def on_enter(self):
        self.app.set_screen("MOVE_CLOSER")

    def on_button(self, btn: str):
        if btn == "BTN_RIGHT":
            pos = self.app.get_position_status()
            if pos == "Good":
                self.manager.transition_to("CALIBRATION")
            else:
                self.app.set_info_msg("Not in position yet", 1.0)

    def on_update(self):
        pos = self.app.get_position_status()
        if pos == "Good":
            self.manager.transition_to("IN_POSITION")
        elif pos == "Near":
            self.manager.transition_to("MOVE_FARTHER")


class MoveFartherState(State):
    def on_enter(self):
        self.app.set_screen("MOVE_FARTHER")

    def on_button(self, btn: str):
        if btn == "BTN_RIGHT":
            pos = self.app.get_position_status()
            if pos == "Good":
                self.manager.transition_to("CALIBRATION")
            else:
                self.app.set_info_msg("Not in position yet", 1.0)

    def on_update(self):
        pos = self.app.get_position_status()
        if pos == "Good":
            self.manager.transition_to("IN_POSITION")
        elif pos != "Near":
            self.manager.transition_to("MOVE_CLOSER")


class InPositionState(State):
    def on_enter(self):
        self.app.set_screen("IN_POSITION")

    def on_button(self, btn: str):
        if btn == "BTN_RIGHT":
            pos = self.app.get_position_status()
            if pos == "Good":
                self.manager.transition_to("CALIBRATION")
            else:
                self.app.set_info_msg("Not in position yet", 1.0)

    def on_update(self):
        pos = self.app.get_position_status()
        if pos == "Near":
            self.manager.transition_to("MOVE_FARTHER")
        elif pos != "Good":
            self.manager.transition_to("MOVE_CLOSER")


class CalibrationState(State):
    def on_enter(self):
        self.app.set_screen("CALIBRATION")
        if self.app.get_calib_quality() == "none":
            self.app.check_existing_calibration()

    def on_button(self, btn: str):
        running_now = self.app.is_calib_running()
        calib_quality = self.app.get_calib_quality()
        done_now = (not running_now) and (calib_quality in ("ok", "low", "failed"))

        if btn == "BTN_RIGHT":
            if (not running_now) and calib_quality == "none":
                self.app.start_calibration()
            elif done_now and calib_quality in ("ok", "low"):
                self.manager.transition_to("RECORD_CONFIRMATION")
        elif btn == "BTN_LEFT":
            if done_now:
                self.app.start_calibration()


class RecordConfirmationState(State):
    def on_enter(self):
        self.app.set_screen("RECORD_CONFIRMATION")

    def on_button(self, btn: str):
        if btn == "BTN_RIGHT":
            self.app.start_collection()


class Recording1State(State):
    def on_enter(self):
        self.app.set_screen("RECORDING_1")

    def on_button(self, btn: str):
        if btn == "BTN_A":
            self.app.marker_toggle()
        elif btn == "BTN_DOWN":
            pos = self.app.get_position_status()
            if pos == "Good":
                self.manager.transition_to("RECORDING_2_IN_POS")
            elif pos == "Near":
                self.manager.transition_to("RECORDING_2_FARTHER")
            else:
                self.manager.transition_to("RECORDING_2_CLOSER")


class Recording2InPosState(State):
    def on_enter(self):
        self.app.set_screen("RECORDING_2_IN_POS")

    def on_button(self, btn: str):
        if btn == "BTN_UP":
            self.manager.transition_to("RECORDING_1")
        elif btn == "BTN_DOWN":
            self.manager.transition_to("RECORDING_3")

    def on_update(self):
        pos = self.app.get_position_status()
        if pos == "Near":
            self.manager.transition_to("RECORDING_2_FARTHER")
        elif pos != "Good":
            self.manager.transition_to("RECORDING_2_CLOSER")


class Recording2CloserState(State):
    def on_enter(self):
        self.app.set_screen("RECORDING_2_CLOSER")

    def on_button(self, btn: str):
        if btn == "BTN_UP":
            self.manager.transition_to("RECORDING_1")
        elif btn == "BTN_DOWN":
            self.manager.transition_to("RECORDING_3")

    def on_update(self):
        pos = self.app.get_position_status()
        if pos == "Good":
            self.manager.transition_to("RECORDING_2_IN_POS")
        elif pos == "Near":
            self.manager.transition_to("RECORDING_2_FARTHER")


class Recording2FartherState(State):
    def on_enter(self):
        self.app.set_screen("RECORDING_2_FARTHER")

    def on_button(self, btn: str):
        if btn == "BTN_UP":
            self.manager.transition_to("RECORDING_1")
        elif btn == "BTN_DOWN":
            self.manager.transition_to("RECORDING_3")

    def on_update(self):
        pos = self.app.get_position_status()
        if pos == "Good":
            self.manager.transition_to("RECORDING_2_IN_POS")
        elif pos != "Near":
            self.manager.transition_to("RECORDING_2_CLOSER")


class Recording3State(State):
    def on_enter(self):
        self.app.set_screen("RECORDING_3")

    def on_button(self, btn: str):
        if btn == "BTN_UP":
            pos = self.app.get_position_status()
            if pos == "Good":
                self.manager.transition_to("RECORDING_2_IN_POS")
            elif pos == "Near":
                self.manager.transition_to("RECORDING_2_FARTHER")
            else:
                self.manager.transition_to("RECORDING_2_CLOSER")
        elif btn == "BTN_RIGHT":
            self.manager.transition_to("STOP_RECORD")


class StopRecordState(State):
    def on_enter(self):
        self.app.set_screen("STOP_RECORD")

    def on_button(self, btn: str):
        if btn == "BTN_RIGHT":
            self.app.stop_collection()
        elif btn == "BTN_LEFT":
            self.manager.transition_to("RECORDING_1")


class InferenceLoadingState(State):
    def on_enter(self):
        self.app.set_screen("INFERENCE_LOADING")

    def on_button(self, btn: str):
        # No buttons active during loading
        pass


class ResultsState(State):
    def on_enter(self):
        self.app.set_screen("RESULTS")

    def on_button(self, btn: str):
        pages = self.app.get_results_pages()
        idx = self.app.get_results_page_index()
        
        if btn == "BTN_RIGHT":
            if pages and idx < len(pages) - 1:
                self.app.set_results_page_index(idx + 1)
        elif btn == "BTN_LEFT":
            if pages and idx > 0:
                self.app.set_results_page_index(idx - 1)


class StateMachineManager:
    def __init__(self, app: AppInterface):
        self.app = app
        self.states: Dict[str, State] = {
            "BOOT": BootState(app, self),
            "FIND_POSITION": FindPositionState(app, self),
            "MOVE_CLOSER": MoveCloserState(app, self),
            "MOVE_FARTHER": MoveFartherState(app, self),
            "IN_POSITION": InPositionState(app, self),
            "CALIBRATION": CalibrationState(app, self),
            "RECORD_CONFIRMATION": RecordConfirmationState(app, self),
            "RECORDING_1": Recording1State(app, self),
            "RECORDING_2_IN_POS": Recording2InPosState(app, self),
            "RECORDING_2_CLOSER": Recording2CloserState(app, self),
            "RECORDING_2_FARTHER": Recording2FartherState(app, self),
            "RECORDING_3": Recording3State(app, self),
            "STOP_RECORD": StopRecordState(app, self),
            "INFERENCE_LOADING": InferenceLoadingState(app, self),
            "RESULTS": ResultsState(app, self),
        }
        self.current_state_name: str = "BOOT"
        self.current_state: State = self.states["BOOT"]

    def transition_to(self, state_name: str) -> None:
        if state_name not in self.states:
            print(f"Warning: Attempted to transition to unknown state '{state_name}'")
            return
            
        if self.current_state_name != state_name:
            self.current_state.on_exit()
            self.current_state_name = state_name
            self.current_state = self.states[state_name]
            self.current_state.on_enter()

    def on_button(self, btn: str) -> None:
        btn = (btn or "").upper()
        
        # Global reset button
        if btn == "BTN_CENTER":
            self.app.reset_app_state()
            self.transition_to("BOOT")
            return
            
        # BTN_B is currently unused
        if btn == "BTN_B":
            return
            
        self.current_state.on_button(btn)

    def on_update(self) -> None:
        self.current_state.on_update()
