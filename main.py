import ctypes
import logging
import os
import subprocess
import time
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple
import json
import os
import click
import cv2
import mss
import mss.tools
import numpy as np
import win32api
import win32con
import win32gui
from win32com.client import Dispatch

# change them if something not working
BUTTON_ASSETS = {
    "vortex_dl": ["VortexDownloadButton.png", "VortexDownloadButton2.png", "VortexDownloadButton3.png"], #vortex download button
    "web_dl": ["WebsiteDownloadButton.png", "WebsiteDownloadButton2.png", "WebsiteDownloadButton3.png"], #slow download button in nexus site
    "click_here": ["ClickHereButton.png", "ClickHereButton2.png", "ClickHereButton3.png"], #click here button in nexus site (just for sure)
    "vortex_cont": ["VortexContinueButton.png", "VortexContinueButton2.png", "VortexContinueButton3.png"], #continue button for a case when vortex asks if it ned to redownload mod
    "understood": ["UnderstoodButton.png", "UnderstoodButton2.png", "UnderstoodButton3.png"], 
    "staging": ["StagingButton.png", "StagingButton2.png", "StagingButton3.png"]
}
ASSET_DIRECTORY = "assets"


# leave as is
DEFAULT_MATCH_THRESHOLD = 0.9
VORTEX_DL_MATCH_THRESHOLD: float = 0.9 #vortex download button
VORTEX_CONT_MATCH_THRESHOLD: float = 0.9 #slow download button in nexus site
WEB_DL_MATCH_THRESHOLD: float = 0.8 #click here button in nexus site (just for sure)
CLICK_HERE_MATCH_THRESHOLD: float = 0.9 #continue button for a case when vortex asks if it ned to redownload mod
UNDERSTOOD_MATCH_THRESHOLD: float = 0.9
STAGING_MATCH_THRESHOLD: float = 0.9

# Timeouts (seconds)
WAIT_TIMEOUT_VORTEX: float = 7.0 # idk but it works
WAIT_TIMEOUT_WEB: float = 4.0 # same
WAIT_TIMEOUT_CLICK_HERE: float = 6.0 #same
# Scan Intervals (seconds)
SCAN_INTERVAL_VORTEX: float = 0.2
SCAN_INTERVAL_WEB: float = 0.5
SCAN_INTERVAL_CLICK_HERE: float = 0.5
# Delay after final click before restarting scan
POST_CLICK_DELAY: float = 2.0

VORTEX_WINDOW_TITLE = "Vortex"
USER32 = ctypes.windll.user32


class ScanState(Enum):
    INIT = auto()
    WAIT_FOR_VORTEX_OR_CONTINUE = auto()
    CLICK_VORTEX = auto()
    CLICK_CONTINUE = auto()
    CLICK_UNDERSTOOD = auto()
    CLICK_STAGING = auto()
    WAIT_FOR_WEB = auto()
    CLICK_WEB = auto()
    WAIT_FOR_CLICK_HERE = auto()
    CLICK_NEXT = auto()
    PROCESS_COMPLETE = auto()


class System:
    def __init__(self, browser: Optional[str] = None, vortex: bool = False, verbose: bool = False, force_primary: bool = False):
        self.browser = browser.lower()
        self.browser_closed = True
        log_level = logging.INFO if verbose else logging.WARNING
        logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')

        logging.info("Initializing system...")
        logging.info(f"Arguments: browser={browser}, vortex={vortex}, verbose={verbose}, force_primary={force_primary}")

        self.monitors = self._get_monitors()
        if not self.monitors:
            logging.error("No monitors found. Exiting.")
            raise RuntimeError("Could not detect any display monitors.")

        if force_primary:
            self.monitors = [m for m in self.monitors if m['is_primary']]
            if not self.monitors:
                 self.monitors = [self._get_monitors()[0]]
            logging.info("Forcing primary monitor only.")
        else:
            self.monitors = sorted(self.monitors, key=lambda m: (m['left'], m['top']))

        logging.info(f"Using {len(self.monitors)} monitors: {self.monitors}")

        self._calculate_monitor_geometry()

        try:
            self.button_templates: Dict[str, List[np.ndarray]] = self._load_assets(BUTTON_ASSETS, ASSET_DIRECTORY)
            logging.info("Loaded button assets.")
            if not self.button_templates:
                 raise RuntimeError("No button assets were loaded. Check configuration and asset files.")
        except (FileNotFoundError, IOError, RuntimeError) as e:
            logging.error(f"Asset loading failed: {e}")
            raise

        self.screen_capturer = mss.mss()
        self.capture_area = self._define_capture_area()
        logging.info(f"Screen capture area set to: {self.capture_area}")

        if browser:
            self._prepare_browser()
        if vortex:
            self._prepare_vortex()

        self.use_vortex_logic = vortex
        self.verbose = verbose

        self.current_state = ScanState.INIT
        self.state_transition_time = time.monotonic()
        self.last_click_location: Optional[Tuple[int, int]] = None

        self.match_thresholds = {
            "vortex_dl": VORTEX_DL_MATCH_THRESHOLD,
            "web_dl": WEB_DL_MATCH_THRESHOLD,
            "click_here": CLICK_HERE_MATCH_THRESHOLD,
            "vortex_cont": VORTEX_CONT_MATCH_THRESHOLD,
            "understood": UNDERSTOOD_MATCH_THRESHOLD,
            "staging": STAGING_MATCH_THRESHOLD,
        }

        logging.info("System initialization complete.")

    def _get_monitors(self) -> List[dict]:
        monitors_raw = win32api.EnumDisplayMonitors(None, None)
        monitor_details = []
        primary_monitor_found = False
        if not monitors_raw:
             return []

        for i, monitor in enumerate(monitors_raw):
            try:
                monitor_info = win32api.GetMonitorInfo(monitor[0].handle)
                rect = monitor[2]
                is_primary = monitor_info.get("Flags") == win32con.MONITORINFOF_PRIMARY
                details = {
                    "handle": monitor[0].handle,
                    "device": monitor_info.get("Device", f"Unknown_{i}"),
                    "left": rect[0],
                    "top": rect[1],
                    "width": rect[2] - rect[0],
                    "height": rect[3] - rect[1],
                    "is_primary": is_primary
                }
                monitor_details.append(details)
                if is_primary:
                    primary_monitor_found = True
            except Exception as e:
                 logging.error(f"Could not get info for monitor {i}: {e}")

        if not primary_monitor_found and monitor_details:
             monitor_details[0]['is_primary'] = True # Fallback

        monitor_details.sort(key=lambda m: not m['is_primary']) # Primary first
        return monitor_details

    def _calculate_monitor_geometry(self) -> None:
        if not self.monitors:
            raise RuntimeError("Cannot calculate geometry without monitors.")

        self.min_left = min(m['left'] for m in self.monitors)
        self.min_top = min(m['top'] for m in self.monitors)
        self.max_right = max(m['left'] + m['width'] for m in self.monitors)
        self.max_bottom = max(m['top'] + m['height'] for m in self.monitors)

        self.full_width = self.max_right - self.min_left
        self.full_height = self.max_bottom - self.min_top

        self.offset_x = -self.min_left
        self.offset_y = -self.min_top

        logging.info(f"Combined screen geometry: L={self.min_left}, T={self.min_top}, W={self.full_width}, H={self.full_height}")
        logging.info(f"Coordinate offsets: X={self.offset_x}, Y={self.offset_y}")

    def _define_capture_area(self) -> dict:
        return {
            "top": self.min_top,
            "left": self.min_left,
            "width": self.full_width,
            "height": self.full_height,
            "mon": 0,
        }

    def _load_assets(self, asset_config: Dict[str, List[str]], asset_dir: str) -> Dict[str, List[np.ndarray]]:
        loaded_templates: Dict[str, List[np.ndarray]] = {}
        total_loaded = 0
        for btn_key, filenames in asset_config.items():
            loaded_templates[btn_key] = []
            if not filenames:
                 logging.warning(f"No filenames specified for button key '{btn_key}'.")
                 continue
            for filename in filenames:
                path = os.path.join(asset_dir, filename)
                if not os.path.isfile(path):
                    logging.warning(f"Asset file not found, skipping: {path} (for key '{btn_key}')")
                    continue
                img = cv2.imread(path, cv2.IMREAD_COLOR)
                if img is None:
                    logging.warning(f"Could not load image, skipping: {path} (for key '{btn_key}')")
                    continue
                loaded_templates[btn_key].append(img)
                total_loaded += 1
                logging.info(f"Loaded asset: {filename} (shape: {img.shape}) for key '{btn_key}'")
            if not loaded_templates[btn_key]:
                 logging.error(f"Failed to load any assets for button key '{btn_key}'. Check filenames/paths in config. Everything will be broken!")
        logging.info(f"Total assets loaded: {total_loaded}")
        return loaded_templates


    def capture_screen(self) -> np.ndarray:
        sct_img = self.screen_capturer.grab(self.capture_area)
        img = cv2.cvtColor(np.array(sct_img), cv2.COLOR_BGRA2BGR)
        return img

    @staticmethod
    def _click(x: int, y: int) -> None:
        try:
            original_pos = win32api.GetCursorPos()
            win32api.SetCursorPos((x, y))
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, x, y, 0, 0)
            time.sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, x, y, 0, 0)
            time.sleep(0.05)
            win32api.SetCursorPos(original_pos)
            logging.info(f"Clicked at screen coordinates: ({x}, {y})")
        except Exception as e:
            logging.error(f"Failed to perform click at ({x}, {y}): {e}")

    def _detect_single_template(self,
                                screen_img: np.ndarray,
                                template_img: np.ndarray,
                                threshold: float,
                                search_bbox_screen: Optional[Tuple[int, int, int, int]] = None
                               ) -> Optional[Tuple[float, Tuple[int, int]]]:
        template_h, template_w = template_img.shape[:2]

        search_region = screen_img
        offset_x, offset_y = 0, 0

        if search_bbox_screen:
            img_x1, img_y1 = self.screen_coords_to_img_coords(search_bbox_screen[0], search_bbox_screen[1])
            img_x2, img_y2 = self.screen_coords_to_img_coords(search_bbox_screen[2], search_bbox_screen[3])
            img_x1, img_y1 = max(0, img_x1), max(0, img_y1)
            img_x2, img_y2 = min(screen_img.shape[1], img_x2), min(screen_img.shape[0], img_y2)

            if img_x1 >= img_x2 or img_y1 >= img_y2: return None
            search_region = screen_img[img_y1:img_y2, img_x1:img_x2]
            offset_x, offset_y = img_x1, img_y1
            if search_region.shape[0] < template_h or search_region.shape[1] < template_w: return None

        try:
             result = cv2.matchTemplate(search_region, template_img, cv2.TM_CCOEFF_NORMED)
        except cv2.error as e:
             logging.warning(f"cv2.matchTemplate failed: {e}. Search shape: {search_region.shape}, Template shape: {template_img.shape}")
             return None

        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        if max_val >= 60: logging.info(max_val)
        if max_val >= threshold:
            center_x_img = offset_x + max_loc[0] + template_w // 2
            center_y_img = offset_y + max_loc[1] + template_h // 2
            screen_x, screen_y = self.img_coords_to_screen_coords(center_x_img, center_y_img)
            return max_val, (screen_x, screen_y)
        else:
            return None


    def detect_button_alternatives(self,
                                   screen_img: np.ndarray,
                                   button_key: str,
                                   search_bbox_screen: Optional[Tuple[int, int, int, int]] = None
                                  ) -> Optional[Tuple[int, int]]:
        templates = self.button_templates.get(button_key)
        threshold = self.match_thresholds.get(button_key, DEFAULT_MATCH_THRESHOLD)

        if not templates:
            return None

        best_match_score = -1.0
        best_match_location = None

        for i, template_img in enumerate(templates):
            match_result = self._detect_single_template(screen_img, template_img, threshold, search_bbox_screen)

            if match_result:
                score, location = match_result
                if score > best_match_score:
                    best_match_score = score
                    best_match_location = location

        if best_match_location:
            return best_match_location
        else:
            return None


    def get_vortex_bbox_screen(self) -> Optional[Tuple[int, int, int, int]]:
        try:
            hwnd = USER32.FindWindowW(None, VORTEX_WINDOW_TITLE)
            if hwnd == 0: return None
            rect = win32gui.GetWindowRect(hwnd)
            return rect
        except Exception as e:
            logging.error(f"Error getting Vortex window rect: {e}")
            return None

    def img_coords_to_screen_coords(self, img_x: int, img_y: int) -> Tuple[int, int]:
        return img_x - self.offset_x, img_y - self.offset_y

    def screen_coords_to_img_coords(self, screen_x: int, screen_y: int) -> Tuple[int, int]:
        return screen_x + self.offset_x, screen_y + self.offset_y

    def _prepare_browser(self) -> None:
        commands = {
            "chrome": r'start chrome --new-window about:blank',
            "firefox": r'start firefox -new-window about:blank',
            "edge": r'start msedge --new-window about:blank'
        }
        window_titles = {"chrome": "New Tab - Google Chrome", "firefox": "Mozilla Firefox", "edge": "New tab - Microsoft​ Edge"}
        fallback_titles = {"chrome": "Google Chrome", "firefox": "Mozilla Firefox", "edge": "Microsoft Edge"}
        
        if self.browser not in commands: logging.warning(f"Browser '{self.browser}' not recognized."); return
        logging.info(f"Preparing browser: {self.browser}")
        try:
            subprocess.Popen(commands[self.browser], shell=True); time.sleep(1.5)
        except:
            pass
        self._find_browser_hwnd()

    def _find_browser_hwnd(self):
        window_titles = {"chrome": "New Tab - Google Chrome", "firefox": "Mozilla Firefox", "edge": "New tab - Microsoft​ Edge"}
        fallback_titles = {"chrome": "Google Chrome", "firefox": "Mozilla Firefox", "edge": "Microsoft Edge"}

        try:
            hwnd = USER32.FindWindowW(None, window_titles.get(self.browser))
            if not hwnd: hwnd = USER32.FindWindowW(None, fallback_titles.get(self.browser))
            if not hwnd:
                class_names = {"chrome": "Chrome_WidgetWin_1", "firefox": "MozillaWindowClass", "edge": "Chrome_WidgetWin_1"}
                hwnd = USER32.FindWindowW(class_names.get(self.browser), None)

            if hwnd and len(self.monitors) > 0:
                primary_monitor = self.monitors[0]
                x, y = primary_monitor['left'], primary_monitor['top']
                win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, x, y, 0, 0, win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
            if hwnd: self.browser_hwnd = hwnd
        except Exception as e: logging.error(f"Failed to prepare browser '{self.browser}': {e}")


    def _prepare_vortex(self) -> None:
        if len(self.monitors) <= 1: logging.info("Single monitor, skipping Vortex positioning."); return
        logging.info("Attempting to position Vortex window...")
        try:
            hwnd = USER32.FindWindowW(None, VORTEX_WINDOW_TITLE)
            if hwnd == 0: logging.warning(f"Vortex window ('{VORTEX_WINDOW_TITLE}') not found for positioning."); return
            target_monitor = self.monitors[1] if len(self.monitors) > 1 else self.monitors[0]
            x, y = target_monitor['left'] + 50, target_monitor['top'] + 50
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, x, y, 0, 0, win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
            logging.info(f"Positioned Vortex window (HWND: {hwnd}) on monitor: {target_monitor.get('device', 'Unknown')}")
        except Exception as e: logging.error(f"Failed to position Vortex window: {e}")


    def _transition_state(self, next_state: ScanState):
        if self.current_state != next_state:
            logging.info(f"Transitioning from {self.current_state.name} to {next_state.name}")
            self.current_state = next_state
            self.state_transition_time = time.monotonic()


    def run_state_machine(self) -> None:
        now = time.monotonic()
        elapsed_state_time = now - self.state_transition_time

        timeout = None
        if self.current_state == ScanState.WAIT_FOR_VORTEX_OR_CONTINUE: timeout = WAIT_TIMEOUT_VORTEX
        elif self.current_state == ScanState.WAIT_FOR_WEB: timeout = WAIT_TIMEOUT_WEB
        elif self.current_state == ScanState.WAIT_FOR_CLICK_HERE: timeout = WAIT_TIMEOUT_CLICK_HERE

        if timeout is not None and elapsed_state_time > timeout:
            logging.warning(f"Timeout in state {self.current_state.name}. Resetting.")
            self._transition_state(ScanState.INIT)
            return

        screen_img = None
        capture_needed_states = [
             ScanState.WAIT_FOR_VORTEX_OR_CONTINUE,
             ScanState.WAIT_FOR_WEB,
             ScanState.WAIT_FOR_CLICK_HERE
        ]
        if self.current_state in capture_needed_states:
             screen_img = self.capture_screen()
             if screen_img is None:
                 logging.error("Failed to capture screen.")
                 time.sleep(1)
                 return

        if self.current_state == ScanState.INIT:
            logging.info("Starting scan cycle...")
            self._transition_state(ScanState.WAIT_FOR_VORTEX_OR_CONTINUE)
            time.sleep(0.1)

        elif self.current_state == ScanState.WAIT_FOR_VORTEX_OR_CONTINUE:
            if screen_img is None: return

            understood_loc = self.detect_button_alternatives(screen_img, "understood") # not sure
            if understood_loc:
                logging.info(f"'Understood' button found at {understood_loc}.")
                self.last_click_location = understood_loc
                self._transition_state(ScanState.CLICK_UNDERSTOOD)
                return

            staging_loc = self.detect_button_alternatives(screen_img, "staging") # not sure 
            if staging_loc:
                logging.info(f"'Staging' button found at {staging_loc}.")
                self.last_click_location = staging_loc
                self._transition_state(ScanState.CLICK_STAGING)
                return

            continue_loc = self.detect_button_alternatives(screen_img, "vortex_cont")
            if continue_loc:
                logging.info(f"Vortex 'Continue' button found at {continue_loc}.")
                self.last_click_location = continue_loc
                self._transition_state(ScanState.CLICK_CONTINUE)
                return

            vortex_bbox = self.get_vortex_bbox_screen() if self.use_vortex_logic else None
            vortex_dl_loc = self.detect_button_alternatives(screen_img, "vortex_dl", search_bbox_screen=vortex_bbox)
            if vortex_dl_loc:
                logging.info(f"Vortex 'Download' button found at {vortex_dl_loc}.")
                if vortex_dl_loc:
                    if self.browser_hwnd and not self.browser_closed: #try to close current browser tab just before clicking download in vertex (or vortex icr)    
                        try:
                            self._find_browser_hwnd()
                            win32gui.ShowWindow(self.browser_hwnd, win32con.SW_RESTORE)
                            win32api.keybd_event(win32con.VK_MENU,             0, 0, 0)
                            time.sleep(0.2)
                            win32gui.SetForegroundWindow(self.browser_hwnd)
                            win32api.keybd_event(win32con.VK_MENU,             0, win32con.KEYEVENTF_KEYUP, 0)
                            

                            time.sleep(0.05)
                            win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
                            win32api.keybd_event(ord('W'),             0, 0, 0)
                            time.sleep(0.05)
                            win32api.keybd_event(ord('W'),             0, win32con.KEYEVENTF_KEYUP, 0)
                            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)

                            self.browser_closed = True
                        except:
                            pass

                self.last_click_location = vortex_dl_loc
                self._transition_state(ScanState.CLICK_VORTEX)
                return

            time.sleep(SCAN_INTERVAL_VORTEX)


        elif self.current_state == ScanState.WAIT_FOR_WEB:
            if screen_img is None: return

            understood_loc = self.detect_button_alternatives(screen_img, "understood") #not sure at all
            if understood_loc:
                logging.info(f"'Understood' button found at {understood_loc}.")
                self.last_click_location = understood_loc
                self._transition_state(ScanState.CLICK_UNDERSTOOD)
                return

            staging_loc = self.detect_button_alternatives(screen_img, "staging") #not sure
            if staging_loc:
                logging.info(f"'Staging' button found at {staging_loc}.")
                self.last_click_location = staging_loc
                self._transition_state(ScanState.CLICK_STAGING)
                return

            web_loc = self.detect_button_alternatives(screen_img, "web_dl")
            if web_loc:
                 logging.info(f"Web Download button found at {web_loc}.")
                 self.last_click_location = web_loc
                 self._transition_state(ScanState.CLICK_WEB)
                 self.browser_closed = False
                 return

            time.sleep(SCAN_INTERVAL_WEB)


        elif self.current_state == ScanState.WAIT_FOR_CLICK_HERE:
             if screen_img is None: return

             click_here_loc = self.detect_button_alternatives(screen_img, "click_here")
             if click_here_loc:
                 logging.info(f"'Click Here' button found at {click_here_loc}.")
                 self.last_click_location = click_here_loc
                 self._transition_state(ScanState.CLICK_NEXT)
                 return

             time.sleep(SCAN_INTERVAL_CLICK_HERE)


        elif self.current_state in [ScanState.CLICK_VORTEX, ScanState.CLICK_CONTINUE,
                                    ScanState.CLICK_WEB, ScanState.CLICK_NEXT,
                                    ScanState.CLICK_UNDERSTOOD, ScanState.CLICK_STAGING]:
            if self.last_click_location:
                self._click(*self.last_click_location)
                if self.current_state in [ScanState.CLICK_VORTEX, ScanState.CLICK_CONTINUE]:
                    self._transition_state(ScanState.WAIT_FOR_WEB)
                elif self.current_state == ScanState.CLICK_WEB:
                    self._transition_state(ScanState.WAIT_FOR_CLICK_HERE)
                elif self.current_state == ScanState.CLICK_NEXT:
                     self._transition_state(ScanState.PROCESS_COMPLETE)
                elif self.current_state == ScanState.CLICK_UNDERSTOOD: #yep, still not sure, never seen that
                     logging.info("Clicked 'Understood', re-checking for primary buttons...")
                     self._transition_state(ScanState.WAIT_FOR_VORTEX_OR_CONTINUE)

                elif self.current_state == ScanState.CLICK_STAGING: #same
                     logging.info("Clicked 'Staging', re-checking for primary buttons...")
                     self._transition_state(ScanState.WAIT_FOR_VORTEX_OR_CONTINUE)

            else:
                logging.error(f"State {self.current_state.name} reached without a click location!")
                self._transition_state(ScanState.INIT)

        elif self.current_state == ScanState.PROCESS_COMPLETE:
            logging.info(f"Scan cycle potentially complete. Waiting {POST_CLICK_DELAY}s.")
            time.sleep(POST_CLICK_DELAY)
            self._transition_state(ScanState.INIT)


    def scan_continuously(self) -> None:
        logging.info("Starting continuous scan...")
        try:
            while True:
                self.run_state_machine()
        except KeyboardInterrupt:
            logging.info("Scan interrupted by user (KeyboardInterrupt).")
        except Exception as e:
            logging.exception(f"An unexpected error occurred during scan: {e}")
        finally:
            if hasattr(self, 'screen_capturer') and self.screen_capturer:
                self.screen_capturer.close()
            logging.info("Screen capturer closed. Exiting.")


@click.command()
@click.option('--browser', type=click.Choice(['chrome', 'firefox', 'edge'], case_sensitive=False), default=None, help='Browser to open (optional).')
@click.option('--vortex', is_flag=True, default=False, help='Enable Vortex-specific logic.')
@click.option('--verbose', '-v', is_flag=True, default=False, help='Enable detailed informational logging.')
@click.option('--force-primary', is_flag=True, default=False, help='Only use the primary monitor.')
@click.option('--vortex-dl-match-threshold', type=float, default=VORTEX_DL_MATCH_THRESHOLD, help='Match threshold for Vortex download button.')
@click.option('--vortex-cont-match-threshold', type=float, default=VORTEX_CONT_MATCH_THRESHOLD, help='Match threshold for Vortex continue button.')
@click.option('--web-dl-match-threshold', type=float, default=WEB_DL_MATCH_THRESHOLD, help='Match threshold for web download button.')
@click.option('--click-here-match-threshold', type=float, default=CLICK_HERE_MATCH_THRESHOLD, help='Match threshold for "click here" button.')
@click.option('--understood-match-threshold', type=float, default=UNDERSTOOD_MATCH_THRESHOLD, help='Match threshold for "understood" button.')
@click.option('--staging-match-threshold', type=float, default=STAGING_MATCH_THRESHOLD, help='Match threshold for staging-related button.')
@click.option('--wait-timeout-vortex', type=float, default=WAIT_TIMEOUT_VORTEX, help='Timeout for Vortex-specific waits.')
@click.option('--wait-timeout-web', type=float, default=WAIT_TIMEOUT_WEB, help='Timeout for web-related waits.')
@click.option('--wait-timeout-click-here', type=float, default=WAIT_TIMEOUT_CLICK_HERE, help='Timeout for "click here" waits.')
@click.option('--scan-interval-vortex', type=float, default=SCAN_INTERVAL_VORTEX, help='Scan interval for Vortex actions.')
@click.option('--scan-interval-web', type=float, default=SCAN_INTERVAL_WEB, help='Scan interval for web actions.')
@click.option('--scan-interval-click-here', type=float, default=SCAN_INTERVAL_CLICK_HERE, help='Scan interval for "click here" actions.')
@click.option('--post-click-delay', type=float, default=POST_CLICK_DELAY, help='Delay after final click before restarting scan.')

def main(browser, vortex, verbose, force_primary, vortex_dl_match_threshold, vortex_cont_match_threshold,
         web_dl_match_threshold, click_here_match_threshold, understood_match_threshold,
         staging_match_threshold, wait_timeout_vortex, wait_timeout_web,
         wait_timeout_click_here, scan_interval_vortex, scan_interval_web,
         scan_interval_click_here, post_click_delay):
    global VORTEX_DL_MATCH_THRESHOLD, VORTEX_CONT_MATCH_THRESHOLD, WEB_DL_MATCH_THRESHOLD
    global CLICK_HERE_MATCH_THRESHOLD, UNDERSTOOD_MATCH_THRESHOLD, STAGING_MATCH_THRESHOLD
    global WAIT_TIMEOUT_VORTEX, WAIT_TIMEOUT_WEB, WAIT_TIMEOUT_CLICK_HERE
    global SCAN_INTERVAL_VORTEX, SCAN_INTERVAL_WEB, SCAN_INTERVAL_CLICK_HERE
    global POST_CLICK_DELAY

    VORTEX_DL_MATCH_THRESHOLD = vortex_dl_match_threshold
    VORTEX_CONT_MATCH_THRESHOLD = vortex_cont_match_threshold
    WEB_DL_MATCH_THRESHOLD = web_dl_match_threshold
    CLICK_HERE_MATCH_THRESHOLD = click_here_match_threshold
    UNDERSTOOD_MATCH_THRESHOLD = understood_match_threshold
    STAGING_MATCH_THRESHOLD = staging_match_threshold
    WAIT_TIMEOUT_VORTEX = wait_timeout_vortex
    WAIT_TIMEOUT_WEB = wait_timeout_web
    WAIT_TIMEOUT_CLICK_HERE = wait_timeout_click_here
    SCAN_INTERVAL_VORTEX = scan_interval_vortex
    SCAN_INTERVAL_WEB = scan_interval_web
    SCAN_INTERVAL_CLICK_HERE = scan_interval_click_here
    POST_CLICK_DELAY = post_click_delay

    log_level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')

    try:
        agent = System(browser=browser, vortex=vortex, verbose=verbose, force_primary=force_primary)
        agent.scan_continuously()
    except (RuntimeError, FileNotFoundError, IOError) as e:
        logging.error(f"Initialization or runtime error: {e}")
    except Exception as e:
        logging.exception(f"An unexpected critical error occurred: {e}")


if __name__ == "__main__":
    main()