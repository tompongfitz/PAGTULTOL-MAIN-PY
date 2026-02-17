# 1. SETUP CONFIG FIRST (Must be at the very top)
import os
from kivy.config import Config
# This ensures the window opens in fullscreen immediately
Config.set('graphics', 'show cursor', '1')
Config.set('graphics', 'fullscreen', 'auto')
Config.set('graphics', 'window_state', 'maximized')
# Prevent mouse emulation issues (sometimes causes double events)
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')


import json
import threading
import requests
import re
import time
import sys
import serial
import subprocess
import platform
from datetime import datetime
from functools import partial

from kivy.uix.vkeyboard import VKeyboard
from kivy.app import App
from kivy.lang import Builder
from kivy.clock import Clock, mainthread
from kivy.animation import Animation
from kivy.factory import Factory
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
from kivy.core.window import Window
from kivy.properties import StringProperty, BooleanProperty
from kivy.graphics import Color, RoundedRectangle


# --- CONFIGURATION ---
ALARM_FILE = "alarms.json"
LOG_FILE = "patient_logs.txt"   # Name of the file where vital signs are saved
CHAT_FILE = "chat_history.json" # Name of the file where chat history is saved
TARGET_PHONE_NUMBER = "+639171234567" # REPLACE THIS WITH THE DOCTOR/GUARDIAN NUMBER


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# Load KV file
Builder.load_file(resource_path("new design.kv"))


# Ollama settings
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "deepseek-v3.1:671b-cloud"


def clean_response(text):
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'`(.*?)`', r'\1', text)
    text = re.sub(r'#+ ', '', text)
    return text.strip()
   
   
   
class BlackScreen(Screen):
    def on_enter(self):
        Clock.schedule_once(lambda dt: self.switch_to_welcome(), 1.5)


    def switch_to_welcome(self):
        self.manager.current = "welcome"



class WelcomeScreen(Screen):
    pass



class MenuScreen(Screen):
    _last_click = 0
    clock_event = None
    wifi_check_event = None

    def go_to_settings(self):
        if time.time() - self._last_click < 0.05: return
        self._last_click = time.time()
        self.manager.current = "settings"


    def on_enter(self):
        # Trigger an immediate update
        self.update_clock(0)
        # Schedule updates every 1 second
        self.clock_event = Clock.schedule_interval(self.update_clock, 1)
       
        # Check Wifi immediately then every 5 seconds
        self.check_wifi_status(0)
        self.wifi_check_event = Clock.schedule_interval(self.check_wifi_status, 5)


    def on_leave(self):
        if self.clock_event:
            self.clock_event.cancel()
            self.clock_event = None
        if self.wifi_check_event:
            self.wifi_check_event.cancel()
            self.wifi_check_event = None


    def update_clock(self, dt):
        # Get current time (System time, synced with DS3231 via OS)
        now = datetime.now()
        time_str = now.strftime("%I:%M:%S %p")
        date_str = now.strftime("%b %d, %Y")
       
        try:
            self.ids.menu_clock.text = time_str
            self.ids.menu_date.text = date_str
        except KeyError:
            print("ERROR: Clock IDs not found in MenuScreen. Check .kv file.")
        except AttributeError:
             print("ERROR: Attribute Error on Clock Update.")
   
    def check_wifi_status(self, dt):
        threading.Thread(target=self._perform_wifi_check, daemon=True).start()


    def _perform_wifi_check(self):
        is_connected = False
        try:
            if platform.system() == "Windows":
                # Simple check for Windows with timeout
                try:
                    output = subprocess.check_output("netsh wlan show interfaces", shell=True, timeout=3).decode(errors='ignore')
                    if "State" in output and "connected" in output:
                        is_connected = True
                except: pass
            else:
                # Linux / nmcli with timeout
                try:
                    # Check for any active connection on wifi device using nmcli
                    output = subprocess.check_output(["sudo", "/usr/bin/nmcli", "-t", "-f", "DEVICE,STATE", "dev"], timeout=3).decode('utf-8', errors='ignore')
                    for line in output.splitlines():
                        if "wlan" in line or "wifi" in line:
                             if ":connected" in line:
                                 is_connected = True
                                 break
                except: pass
        except Exception as e:
            print(f"Wifi Check Error: {e}")
        finally:
            # Always update UI, even if check failed
            Clock.schedule_once(partial(self._update_wifi_button, is_connected), 0)


    def _update_wifi_button(self, is_connected, dt):
        # Update Wifi Button
        status_text = "CONNECTED" if is_connected else "NOT CONNECTED"
        color_hex = "00FF00" if is_connected else "FF5555" # Green / Red
       
        if self.ids.get("wifi_btn"):
            self.ids.wifi_btn.text = f"[size=18][b]WI-FI SETTINGS[/b][/size]\n[size=12]Network Configuration\nStatus: [color={color_hex}]{status_text}[/color][/size]"


        # Update AI Button
        ai_status = "ONLINE" if is_connected else "OFFLINE"
        ai_color = "AAFFAA" if is_connected else "FF5555"
        if self.ids.get("ai_btn"):
            self.ids.ai_btn.text = f"[size=18][b]AI ASSISTANT[/b][/size]\n[size=12]Interactive Chat Module\nSystem Status: [color={ai_color}]{ai_status}[/color][/size]"


    def go_to_chat(self):
        if time.time() - self._last_click < 0.05: return
        self._last_click = time.time()
        self.manager.current = "chat"


    def go_to_vitals(self):
        if time.time() - self._last_click < 0.05: return
        self._last_click = time.time()
        self.manager.current = "vitals"
       
    def go_to_wifi(self):
        if time.time() - self._last_click < 0.05: return
        self._last_click = time.time()
        self.manager.current = "wifi"


    def show_power_options(self):
        # --- DEBOUNCE LOGIC ---
        if time.time() - self._last_click < 0.5:
            return
        self._last_click = time.time()


        # --- OPEN POPUP ---
        content = Factory.PowerPopup()
        self._power_popup = Popup(
            title="MAINTENANCE",  # Short, professional title
            content=content,
            size_hint=(0.7, 0.5), # Slightly taller for better spacing
            auto_dismiss=True,
            title_size="14sp",
            title_color=(0.2, 0.6, 1, 1), # Medical Blue Title
            separator_color=(0.9, 0.9, 0.9, 1), # Very subtle separator
            background_color=(0.95, 0.95, 0.95, 1) # Match popup bg
        )


        content.ids.btn_shutdown.bind(on_release=self.exec_shutdown)
        content.ids.btn_reboot.bind(on_release=self.exec_reboot)
        content.ids.btn_cancel.bind(on_release=self._power_popup.dismiss)
        self._power_popup.open()


    def exec_shutdown(self, instance):
        self._power_popup.dismiss()
        if platform.system() == "Windows":
            print("Simulating Shutdown...")
            App.get_running_app().stop()
        else:
            threading.Thread(target=lambda: os.system("sudo shutdown now")).start()


    def exec_reboot(self, instance):
        self._power_popup.dismiss()
        if platform.system() == "Windows":
            print("Simulating Reboot...")
        else:
            threading.Thread(target=lambda: os.system("sudo reboot")).start()



class WifiScreen(Screen):
    scanning = False
    # Keyboard Attributes
    caps_enabled = False
    shift_enabled = False
    keyboard_page = 0
    _last_key_down = None # Track last key name
    _last_key_time = 0.0
    selected_ssid = ""
   
    # Network State
    cached_networks = []  # List of dicts: {'ssid': str, 'active': bool}
    expanded_ssid = None  # Tracks which SSID is currently "expanded" in the UI

    def __init__(self, **kwargs):
        super(WifiScreen, self).__init__(**kwargs)
        self.selected_ssid = ""

	
	
    def on_enter(self):
        # Ensure we start on the list view
        self.ids.wifi_sm.current = "list"
        # Check if switch is active before scanning
        if self.ids.wifi_switch.active:
            self.scan_wifi()
        else:
            self.ids.wifi_status.text = "Wi-Fi is disabled."
            self.ids.wifi_list_layout.clear_widgets()


    def go_back_menu(self):
        self.manager.current = "menu"


    # --- TOGGLE WIFI ---
    def toggle_wifi_state(self, is_active):
        if is_active:
            self.ids.wifi_status.text = "Enabling Wi-Fi..."
            self._set_system_wifi(True)
            self.scan_wifi()
        else:
            self.ids.wifi_status.text = "Wi-Fi is turned off."
            self.ids.wifi_list_layout.clear_widgets()
            self._set_system_wifi(False)
            self.scanning = False


    def _set_system_wifi(self, turn_on):
        """ Attempts to turn system wifi on/off via nmcli on Linux """
        if platform.system() != "Windows":
            state = "on" if turn_on else "off"
            try:
                subprocess.run(["sudo", "/usr/bin/nmcli", "radio", "wifi", state])
            except Exception:
                pass


    # --- SCANNING LOGIC ---
    def scan_wifi(self):
        if self.scanning: return
        # Don't scan if switch is off
        if not self.ids.wifi_switch.active:
            self.ids.wifi_status.text = "Wi-Fi is off. Enable to scan."
            return


        self.scanning = True
        self.expanded_ssid = None # Reset expansion on scan
        self.ids.wifi_status.text = "Scanning for networks..."
        self.ids.wifi_list_layout.clear_widgets()
        threading.Thread(target=self._perform_scan, daemon=True).start()


    def _perform_scan(self):
        networks_data = [] # List of {'ssid': name, 'active': bool}
        found_ssids = set()
        system = platform.system()
       
        try:
            if system == "Windows":
                # Windows logic with timeout
                try:
                    cmd = subprocess.check_output("netsh wlan show networks mode=bssid", shell=True, timeout=5)
                    decoded = cmd.decode('utf-8', errors='ignore')
                    for line in decoded.split('\n'):
                        if "SSID" in line and ":" in line:
                            parts = line.split(":", 1)
                            ssid = parts[1].strip()
                            if ssid and ssid not in found_ssids:
                                networks_data.append({'ssid': ssid, 'active': False})
                                found_ssids.add(ssid)
                except subprocess.TimeoutExpired:
                    print("Windows scan timed out")

            else:
                # Linux/Pi: Get ACTIVE status + SSID
                # 1. Try to rescan first (refresh list)
                try:
                    subprocess.run(["sudo", "/usr/bin/nmcli", "device", "wifi", "rescan"], timeout=5)
                except Exception:
                    pass
               
                # 2. Get list with timeout
                try:
                    cmd = subprocess.check_output(["sudo", "/usr/bin/nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi", "list"], timeout=10)
                    decoded = cmd.decode('utf-8', errors='ignore')
                    for line in decoded.split('\n'):
                        if ":" in line:
                            active_str, ssid = line.split(":", 1)
                            ssid = ssid.strip()
                            is_active = (active_str.lower() == 'yes')
                           
                            if ssid and ssid not in found_ssids and "--" not in ssid:
                                networks_data.append({'ssid': ssid, 'active': is_active})
                                found_ssids.add(ssid)
                except subprocess.TimeoutExpired:
                    print("Linux scan timed out")
                           
        except Exception as e:
            print(f"Scan Error: {e}")
            Clock.schedule_once(lambda dt: self._update_status(f"Scan Error"), 0)
            self.scanning = False
            return

        # Sort: Active first, then Alphabetical
        networks_data.sort(key=lambda x: (not x['active'], x['ssid']))
       
        self.cached_networks = networks_data
        Clock.schedule_once(lambda dt: self._render_network_list(), 0)



        networks_data = [] # List of {'ssid': name, 'active': bool}
        found_ssids = set()
        system = platform.system()
       
        try:
            if system == "Windows":
                cmd = subprocess.check_output("netsh wlan show networks mode=bssid", shell=True)
                decoded = cmd.decode('utf-8', errors='ignore')
                for line in decoded.split('\n'):
                    if "SSID" in line and ":" in line:
                        parts = line.split(":", 1)
                        ssid = parts[1].strip()
                        if ssid and ssid not in found_ssids:
                            # Basic Windows logic (assuming not active for now or simple list)
                            networks_data.append({'ssid': ssid, 'active': False})
                            found_ssids.add(ssid)
            else:
                # Linux/Pi: Get ACTIVE status + SSID
                # Try to rescan first
                try: subprocess.run(["sudo", "/usr/bin/nmcli", "device", "wifi", "rescan"], timeout=5)
                except: pass
               
                cmd = subprocess.check_output(["sudo", "/usr/bin/nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi", "list"])
                decoded = cmd.decode('utf-8', errors='ignore')
                for line in decoded.split('\n'):
                    if ":" in line:
                        active_str, ssid = line.split(":", 1)
                        ssid = ssid.strip()
                        is_active = (active_str.lower() == 'yes')
                       
                        if ssid and ssid not in found_ssids and "--" not in ssid:
                            # If duplicate SSIDs exist, prioritize the active one or first one
                            networks_data.append({'ssid': ssid, 'active': is_active})
                            found_ssids.add(ssid)
                           
        except Exception as e:
            Clock.schedule_once(lambda dt: self._update_status(f"Scan Error or Wi-Fi Off"), 0)
            self.scanning = False
            return


        # Sort: Active first, then Alphabetical
        networks_data.sort(key=lambda x: (not x['active'], x['ssid']))
       
        self.cached_networks = networks_data
        Clock.schedule_once(lambda dt: self._render_network_list(), 0)


    def _update_status(self, text):
        self.ids.wifi_status.text = text


    def _render_network_list(self):
        """ Renders the list of networks from self.cached_networks """
        self.ids.wifi_list_layout.clear_widgets()
        self.scanning = False
       
        if not self.ids.wifi_switch.active:
            self.ids.wifi_status.text = "Wi-Fi is turned off."
            return


        if not self.cached_networks:
            self.ids.wifi_status.text = "No networks found."
            return


        self.ids.wifi_status.text = f"Found {len(self.cached_networks)} networks."
       
        for net in self.cached_networks:
            ssid = net['ssid']
            is_active = net['active']
           
            # --- EXPANDED VIEW LOGIC (STRETCHED BOX) ---
            if self.expanded_ssid == ssid:
                # Create Container (The "Stretched" Box)
                box = BoxLayout(orientation='vertical', size_hint_y=None, height="110dp", spacing=0)
               
                # Add a background to the whole box to make it look like one unit
                with box.canvas.before:
                    Color(0.9, 1, 0.9, 1) # Light green background
                    RoundedRectangle(pos=box.pos, size=box.size, radius=[6,])
               
                # Bind size/pos updates for the canvas to work on a layout created in python
                def update_canvas(instance, value):
                    instance.canvas.before.clear()
                    with instance.canvas.before:
                        Color(0.9, 1, 0.9, 1)
                        RoundedRectangle(pos=instance.pos, size=instance.size, radius=[6,])
                box.bind(pos=update_canvas, size=update_canvas)


                # Top: The SSID Name (Click to collapse)
                btn_top = Button(
                    text=f"{ssid} (Connected)",
                    background_normal='',
                    background_color=(0,0,0,0), # Transparent, letting box background show
                    color=(0, 0.6, 0.2, 1),
                    bold=True,
                    font_size=14,
                    size_hint_y=0.6
                )
                btn_top.bind(on_release=lambda x, s=ssid: self.toggle_expand(s))


               
                # Bottom: Disconnect Button
                # We put this in a padding box to make it look nicer and centered
                btn_container = BoxLayout(padding=[40, 5, 40, 10], size_hint_y=0.4)
                btn_action = Button(
                    text="DISCONNECT",
                    background_normal='',
                    background_color=(0.8, 0.3, 0.3, 1), # Red
                    color=(1, 1, 1, 1),
                    bold=True,
                    font_size=12
                )
                btn_action.bind(on_release=lambda x, s=ssid: self.disconnect_wifi(s))
               
                btn_container.add_widget(btn_action)
                box.add_widget(btn_top)
                box.add_widget(btn_container)
               
                self.ids.wifi_list_layout.add_widget(box)


            else:
                # --- STANDARD BUTTON LOGIC ---
                # Active network gets green text, others gray
                text_col = (0, 0.6, 0.2, 1) if is_active else (0.2, 0.2, 0.2, 1)
                bg_col = (0.9, 1, 0.9, 1) if is_active else (0.95, 0.95, 0.95, 1)
                label_text = f"{ssid} (Connected)" if is_active else ssid


                btn = Button(
                    text=label_text,
                    size_hint_y=None,
                    height="45dp",
                    background_normal='',
                    background_color=bg_col,
                    color=text_col,
                    bold=is_active,
                    font_size=12
                )
               
                if is_active:
                    # If connected, click triggers expansion
                    btn.bind(on_release=lambda x, s=ssid: self.toggle_expand(s))
                else:
                    # If not connected, click triggers password/connect logic
                    btn.bind(on_release=partial(self.prepare_connection, ssid))
               
                self.ids.wifi_list_layout.add_widget(btn)


    def toggle_expand(self, ssid):
        """ Toggles the expansion of the connected network box """
        if self.expanded_ssid == ssid:
            self.expanded_ssid = None # Collapse
        else:
            self.expanded_ssid = ssid # Expand
       
        # Re-render list with new state
        self._render_network_list()


    def disconnect_wifi(self, ssid):
        """ Runs command to disconnect the wifi """
        self.ids.wifi_status.text = f"Disconnecting {ssid}..."
        threading.Thread(target=self._perform_disconnect, args=(ssid,), daemon=True).start()


    def _perform_disconnect(self, ssid):
        if platform.system() != "Windows":
            # Linux: nmcli connection down id <ssid>
            try:
                subprocess.run(["sudo", "/usr/bin/nmcli", "connection", "down", "id", ssid], capture_output=True, timeout=10)
            except Exception as e:
                print(f"Disconnect Error: {e}")
       
        # After disconnect, rescan to update UI
        Clock.schedule_once(lambda dt: self.scan_wifi(), 1.0)



        if platform.system() != "Windows":
            # Linux: nmcli connection down <id>
            try:
                subprocess.run(["sudo", "/usr/bin/nmcli", "connection", "down", ssid], capture_output=True)
            except Exception:
                pass
       
        # After disconnect, rescan to update UI
        Clock.schedule_once(lambda dt: self.scan_wifi(), 1.0)




    # --- PASSWORD & KEYBOARD LOGIC ---
   
    def has_saved_profile(self, ssid):
        """ Checks if a connection profile exists for this SSID using nmcli """
        if platform.system() == "Windows":
            return False # Windows management is complex, skipping logic
        try:
            # nmcli -g NAME connection show lists all connection names
            output = subprocess.check_output(["sudo", "/usr/bin/nmcli", "-g", "NAME", "connection", "show"], timeout=2).decode('utf-8')
            profiles = output.strip().split('\n')
            return ssid in profiles
        except:
            return False


    def prepare_connection(self, ssid, instance):
        # 1. Check for saved profile first
        if self.has_saved_profile(ssid):
            self.ids.wifi_status.text = f"Connecting to saved network: {ssid}..."
            # Try to connect without password first
            threading.Thread(target=self._perform_saved_connection, args=(ssid,), daemon=True).start()
            return


        # 2. If no profile, go to password screen
        self._show_password_screen(ssid)


    def _show_password_screen(self, ssid):
        self.selected_ssid = ssid
        self.ids.pass_prompt.text = f"Enter Password for: {ssid}"
        self.ids.pass_input.text = ""
        self.ids.wifi_sm.current = "password"
       
        # Reset Keyboard
        self.caps_enabled = False
        self.shift_enabled = False
        self.keyboard_page = 0
        self.build_keyboard()


    def _perform_saved_connection(self, ssid):
        success = False
        try:
            # Try to bring up connection using existing profile with "id" flag
            res = subprocess.run(["sudo", "/usr/bin/nmcli", "connection", "up", "id", ssid], capture_output=True, timeout=15)
            if res.returncode == 0:
                success = True
        except Exception as e:
            print(f"Saved connection error: {e}")
       
        if success:
            Clock.schedule_once(lambda dt: self.scan_wifi(), 2.0)
        else:
            # Fallback to password screen if saved connection fails
            Clock.schedule_once(lambda dt: self._prompt_password_fallback(ssid), 0)



        success = False
        try:
            # Try to bring up connection using existing profile
            # nmcli connection up <ssid>
            res = subprocess.run(["sudo", "/usr/bin/nmcli", "connection", "up", ssid], capture_output=True)
            if res.returncode == 0:
                success = True
        except:
            pass
       
        if success:
            Clock.schedule_once(lambda dt: self.scan_wifi(), 2.0)
        else:
            # Fallback to password screen if saved connection fails
            Clock.schedule_once(lambda dt: self._prompt_password_fallback(ssid), 0)


    def _prompt_password_fallback(self, ssid, dt=None):
        self.ids.wifi_status.text = "Saved connection failed. Please re-enter password."
        self._show_password_screen(ssid)


    def cancel_password(self):
        self.ids.wifi_sm.current = "list"
        self.ids.pass_input.text = ""


    def connect_wifi(self):
        ssid = self.selected_ssid
        password = self.ids.pass_input.text
        self.ids.wifi_sm.current = "list"
        self.ids.wifi_status.text = f"Connecting to {ssid}..."
        threading.Thread(target=self._perform_connection, args=(ssid, password), daemon=True).start()


    def _perform_connection(self, ssid, password):
        system = platform.system()
        success = False
        try:
            if system == "Windows":
                Clock.schedule_once(lambda dt: self._update_status("Windows: Connect manually."), 0)
                return
            else:
                # 1. Clear any old saved profile for this SSID so the new password works
                try:
                    subprocess.run(["sudo", "/usr/bin/nmcli", "connection", "delete", "id", ssid], capture_output=True, timeout=5)
                except subprocess.TimeoutExpired:
                    pass

                # 2. Connect with a timeout to prevent thread freezing
                cmd = ["sudo", "/usr/bin/nmcli", "device", "wifi", "connect", ssid, "password", password]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
               
                # Debugging logs
                print(f"NMCLI Return Code: {result.returncode}")
                print(f"NMCLI Output: {result.stdout}")
                print(f"NMCLI Error: {result.stderr}")

                if result.returncode == 0:
                    success = True
        except Exception as e:
            print(f"Connection Error: {e}")
            pass
        
        # Rescan to show connected status
        Clock.schedule_once(lambda dt: self.scan_wifi(), 2.0)



        system = platform.system()
        success = False
        try:
            if system == "Windows":
                # Placeholder for Windows logic
                Clock.schedule_once(lambda dt: self._update_status("Windows: Connect manually."), 0)
                return
            else:
                # Linux/Pi Connection
                # NOTE: Removed the 'nmcli connection delete' line here.
                # We want nmcli to save the profile if connection succeeds.


                # 2. Connect
                cmd = ["sudo", "/usr/bin/nmcli", "device", "wifi", "connect", ssid, "password", password]
                result = subprocess.run(cmd, capture_output=True, text=True)
               
                # Debugging logs (Check console if connection fails)
                print(f"NMCLI Return Code: {result.returncode}")
                print(f"NMCLI Output: {result.stdout}")
                print(f"NMCLI Error: {result.stderr}")


                if result.returncode == 0:
                    success = True
        except Exception as e:
            print(f"Connection Error: {e}")
            pass
        # Rescan to show connected status
        Clock.schedule_once(lambda dt: self.scan_wifi(), 2.0)


    def _finish_connection(self, success, ssid):
        pass


    # --- KEYBOARD BUILDER (Copied & Adapted for Wifi) ---
    def build_keyboard(self, dt=None):
        layout = self.ids.wifi_keyboard
        layout.clear_widgets()
       
        if self.keyboard_page == 0:
            rows = [
                ["q","w","e","r","t","y","u","i","o","p"],
                ["a","s","d","f","g","h","j","k","l"],
                ["SHIFT","z","x","c","v","b","n","m","CAPS"],
                ["MORE","CLEAR","SPACE","BACK"]
            ]
        else:
            rows = [
                ["1","2","3","4","5","6","7","8","9","0"],
                ["-","/",":",";","(",")","$","&","@","\""],
                [".",",","?","!","'","\"","+","=","_","*"],
                ["MAIN","CLEAR","SPACE","BACK"]
            ]
       
        key_bg = (0.9, 0.9, 0.9, 1)
        for row_keys in rows:
            row = BoxLayout(spacing=4, padding=(2,0))
            for key in row_keys:
                display_text = key
                current_bg = list(key_bg)
                is_capitalized = self.caps_enabled or self.shift_enabled
                if self.keyboard_page == 0 and key.isalpha():
                    display_text = key.upper() if is_capitalized else key.lower()
               
                if key == "SHIFT":
                    if self.shift_enabled: current_bg = [0.0, 0.6, 0.6, 1]
                elif key == "CAPS":
                    if self.caps_enabled: current_bg = [0.0, 0.6, 0.6, 1]


                w_hint = 1.0
                if key == "SPACE": w_hint = 2.5
                elif key in ["SHIFT", "CAPS", "MORE", "MAIN", "BACK", "CLEAR"]: w_hint = 1.3
               
                text_col = (0.2, 0.2, 0.2, 1)
                if current_bg[0] < 0.5: text_col = (1,1,1,1)


                btn = Button(
                    text=display_text, font_size=12, size_hint_x=w_hint,
                    background_normal='', background_color=current_bg, color=text_col
                )
                btn.bind(on_release=partial(self.on_key_press, key, btn))
                row.add_widget(btn)
                if key=="SHIFT": self.shift_button = btn
                if key=="CAPS": self.caps_button = btn
            layout.add_widget(row)


    def on_key_press(self, key_name, instance, *args):
        now = time.time()
       
        # --- FIXED DEBOUNCE LOGIC (Consistent with ChatScreen) ---
        # 1. Global Debounce (fast, for noise)
        if now - self._last_key_time < 0.1:
            return


        # 2. Same Key Debounce (prevent double taps)
        if key_name == getattr(self, '_last_key_down', None):
            if now - self._last_key_time < 0.3:
                return


        self._last_key_down = key_name
        self._last_key_time = now
       
        orig_color = instance.background_color
        instance.background_color = (0.0, 0.8, 0.8, 1)
        if key_name not in ["SHIFT", "CAPS"] or not (self.shift_enabled or self.caps_enabled):
             Clock.schedule_once(lambda dt: setattr(instance, 'background_color', orig_color), 0.1)
       
        key = key_name
        ti = self.ids.pass_input
       
        if key=="SPACE": ti.text+=" "; return
        if key=="BACK": ti.text=ti.text[:-1]; return
        if key=="CLEAR": ti.text=""; return
        if key=="CAPS":
            self.caps_enabled = not self.caps_enabled
            self.build_keyboard()
            return
        if key=="SHIFT":
            self.shift_enabled = not self.shift_enabled
            self.build_keyboard()
            return
        if key=="MORE": self.keyboard_page=1; self.build_keyboard(); return
        if key=="MAIN": self.keyboard_page=0; self.build_keyboard(); return
       
        if len(key) == 1:
            is_capitalized = (self.caps_enabled or self.shift_enabled) and self.keyboard_page == 0
            ch = instance.text if key.isalpha() else key
            ti.text += ch
            if self.shift_enabled and not self.caps_enabled:
                self.shift_enabled = False
                self.build_keyboard()



class VitalSignsScreen(Screen):
    # Initialize variables
    bp_sys = 0
    bp_dia = 0
    bp_bpm = 0
   
    current_temp_value = 0
    current_dia_value = 0
    current_bpm_value = 0
    is_monitoring = False
    has_unsaved_data = False
    _last_click = 0
    ser = None


    def on_enter(self):
        self.stop_thread = False
       
        # SAFETY: Ensure buttons are enabled when entering screen
        self.ids.btn_scan.disabled = False
        self._set_exit_buttons_state(disabled=False)
       
        if self.has_unsaved_data:
            # Restore the "Green" Record Button
            self.ids.btn_scan.text = "RECORD\nREADING"
            self.ids.btn_scan.background_color = (0.1, 0.7, 0.2, 1) # Green
           
            self.ids.vitals_status.text = "DATA RESTORED - RECORD TO SAVE"
            self.ids.vitals_status.color = (0, 0.7, 0, 1)
           
            # Restore numbers
            self.update_labels(self.bp_sys, self.bp_dia, self.bp_bpm, 0)
           
        else:
            # Standard Reset
            self.is_monitoring = False
            self.ids.vitals_status.text = "STANDBY - PRESS START"
            self.ids.vitals_status.color = (0.5, 0.5, 0.5, 1)
           
            self.ids.btn_scan.text = "START\nMONITORING"
            self.ids.btn_scan.background_color = (0.2, 0.6, 1, 1) # Blue
           
            self.ids.vitals_temp.text = "-SYSTOLIC-"
            self.ids.vitals_dia.text = "-DIASTOLIC-"
            self.ids.vitals_bpm.text = "-HEART RATE-"
            self.ids.classification.text = "----"
            self.ids.classification.color = (0, 0, 0, 1)


        threading.Thread(target=self.read_arduino_data, daemon=True).start()


    def on_leave(self):
        self.stop_thread = True
        self.is_monitoring = False
       
        # Close connection silently (No STOP command sent to Arduino)
        if self.ser and self.ser.is_open:
            self.ser.close()


    def _set_exit_buttons_state(self, disabled):
        """
        Helper to visually fade the exit button.
        Targeting 'btn_back' from your KV file.
        """
        opacity = 0.3 if disabled else 1.0
       
        if "btn_back" in self.ids:
            self.ids.btn_back.disabled = disabled
            self.ids.btn_back.opacity = opacity


    def go_back_menu(self):
        # BLOCK EXIT WHILE MONITORING
        if self.is_monitoring:
            return


        if time.time() - self._last_click < 0.05: return
        self._last_click = time.time()
        self.manager.current = "menu"


    def toggle_monitoring(self):
        if time.time() - self._last_click < 0.3: return
        self._last_click = time.time()


        # Disable main button for 3 seconds
        self.ids.btn_scan.disabled = True
        Clock.schedule_once(self.enable_button, 3)


        if self.has_unsaved_data:
            self.save_reading()
            return


        if self.is_monitoring:
            self.stop_scanning_manual()
        else:
            self.start_scanning()


    def enable_button(self, dt):
        """ Re-enables the button after the 3-second timer """
        self.ids.btn_scan.disabled = False


    def start_scanning(self):
        self.is_monitoring = True
        self.has_unsaved_data = False
       
        # --- DISABLE EXIT BUTTON (FADE OUT) ---
        self._set_exit_buttons_state(disabled=True)
       
        self.ids.btn_scan.text = "STOP\nMONITORING"
        self.ids.btn_scan.background_color = (0.8, 0.3, 0.3, 1) # Red
       
        self.ids.vitals_status.text = "SCANNING..."
        self.ids.vitals_status.color = (0, 0.7, 0, 1)
       
        self.ids.vitals_temp.text = "-SYSTOLIC-"
        self.ids.vitals_dia.text = "-DIASTOLIC-"
        self.ids.vitals_bpm.text = "-HEART RATE-"
        self.ids.classification.text = "----"
       
        if self.ser and self.ser.is_open:
            try: self.ser.write(b"START\n")
            except Exception as e: print(f"Serial Write Error: {e}")


    def stop_scanning_manual(self):
        self.is_monitoring = False
        self.has_unsaved_data = False
       
        # --- ENABLE EXIT BUTTON (RESTORE OPACITY) ---
        self._set_exit_buttons_state(disabled=False)
       
        if self.ser and self.ser.is_open:
            try: self.ser.write(b"STOP\n")
            except Exception as e: print(f"Serial Write Error: {e}")
           
        self.ids.btn_scan.text = "START\nMONITORING"
        self.ids.btn_scan.background_color = (0.2, 0.6, 1, 1) # Blue
       
        self.ids.vitals_status.text = "STANDBY - ABORTED"
        self.ids.vitals_status.color = (0.5, 0.5, 0.5, 1)


    def transition_to_record_mode(self, dt):
        """ Called automatically when values arrive """
        self.is_monitoring = False
        self.has_unsaved_data = True
       
        # --- ENABLE EXIT BUTTON (User can leave now if they want) ---
        self._set_exit_buttons_state(disabled=False)
       
        # Stop Arduino when values arrive
        # if self.ser and self.ser.is_open:
            # try: self.ser.write(b"STOP\n")
            # except: pass


        self.ids.btn_scan.text = "RECORD\nREADING"
        self.ids.btn_scan.background_color = (0.1, 0.7, 0.2, 1) # Green
       
        self.ids.vitals_status.text = "SCAN COMPLETE - PRESS RECORD"
        self.ids.vitals_status.color = (0, 0.7, 0, 1)


    def read_arduino_data(self):
        try:
            self.ser = serial.Serial('/dev/ttyACM0', 9600, timeout=1)
            time.sleep(2)


            while not self.stop_thread:
                if self.ser.in_waiting > 0:
                    try:
                        line = self.ser.readline().decode('utf-8').strip()
                        if line and line != "Err":
                            try:
                                self.bp_sys, self.bp_dia, self.bp_bpm = line.split("=")
                                if self.is_monitoring:
                                    Clock.schedule_once(partial(self.update_labels, self.bp_sys, self.bp_dia, self.bp_bpm), 0)
                            except ValueError:
                                pass
                    except Exception:
                        pass
                time.sleep(0.1)


        except Exception as e:
            Clock.schedule_once(partial(self.update_labels, "Err", "Err", "Err"), 0)


    def update_labels(self, temp_val, temp_dia, temp_bpm, dt):
        if temp_val == "Err" or temp_dia == "Err" or temp_bpm == "Err":
            self.ids.vitals_temp.text = "Error"
            self.ids.vitals_dia.text = "Error"
            self.ids.vitals_bpm.text = "Error"
        else:
            self.ids.vitals_temp.text = f"{temp_val}"
            self.ids.vitals_dia.text = f"{temp_dia}"
            self.ids.vitals_bpm.text = f"{temp_bpm}"
           
            try:
                sys = int(temp_val)
                dia = int(temp_dia)
                if sys < 120 and dia < 80:
                    self.ids.classification.text = "Optimal"
                    self.ids.classification.color = (0.07, 0.5, 0.17, 1)
                elif 120 <= sys <= 129 or 80 <= dia <= 84:
                    self.ids.classification.text = "Normal"
                    self.ids.classification.color = (0.07, 0.5, 0.17, 1)
                elif 130 <= sys <= 139 or 85 <= dia <= 89:
                    self.ids.classification.text = "High Normal"
                    self.ids.classification.color = (0.07, 0.5, 0.17, 1)
                elif 140 <= sys <= 159 or 90 <= dia <= 99:
                    self.ids.classification.text = "Grade 1 Hypertension"
                    self.ids.classification.color = (0.8, 0.3, 0.3, 1)
                elif 160 <= sys <= 179 or 100 <= dia <= 109:
                    self.ids.classification.text = "Grade 2 Hypertension"
                    self.ids.classification.color = (0.8, 0.3, 0.3, 1)
                elif sys > 180 or dia > 110:
                    self.ids.classification.text = "Grade 3 Hypertension"
                    self.ids.classification.color = (0.8, 0.3, 0.3, 1)
                elif sys > 140 and dia < 90:
                    self.ids.classification.text = "Isolated Systolic Hypertension"
                    self.ids.classification.color = (0.8, 0.3, 0.3, 1)
            except ValueError:
                pass


            if self.is_monitoring:
                Clock.schedule_once(self.transition_to_record_mode, 0.2)


    def save_reading(self):
        if self.ids.vitals_temp.text == "Error" or self.ids.vitals_temp.text == "-SYSTOLIC-":
            self.ids.vitals_status.text = "ERROR: NO DATA TO SAVE"
            self.ids.vitals_status.color = (1, 0, 0, 1)
            Clock.schedule_once(self.return_to_standby_status, 1.5)
            self.has_unsaved_data = False
            return


        # 1. Prepare Data
        temp_val = self.bp_sys
        dia_val = self.bp_dia
        bpm_val = self.bp_bpm
        now = datetime.now()        
        timestamp = now.strftime("%Y-%m-%d  %I:%M %p")
        entry = f"[{timestamp}]       Blood Pressure: {temp_val}/{dia_val}mmHg       Heart Rate:  {bpm_val}bpm"
       
        # 2. Save Data
        app = App.get_running_app()
        app.saved_history.insert(0, entry)
       
        try:
            with open(LOG_FILE, "a") as f:
                f.write(entry + "\n")
        except Exception as e:
            print(f"Error saving to file: {e}")


        # 3. Send SMS/LoRa
        if self.ser and self.ser.is_open:
            try:
                self.ser.write(b"SEND\n")
                sms_cmd = f"SMS:{TARGET_PHONE_NUMBER}:{temp_val}/{dia_val} BP {bpm_val} BPM\n"
                self.ser.write(sms_cmd.encode('utf-8'))
            except Exception as e:
                print(f"Error sending Serial commands: {e}")


        self.is_monitoring = False
        self.has_unsaved_data = False


        self.ids.vitals_status.text = "SAVED! CONSULTING AI..."
        self.ids.vitals_status.color = (0.07, 0.5, 0.17, 1)
        self.ids.btn_scan.text = "SAVED"
       
        Clock.schedule_once(partial(self.redirect_to_ai, temp_val, dia_val, bpm_val), 1.0)


    def redirect_to_ai(self, temp_val, dia_val, bpm_val, dt):
        self.manager.current = "chat"
        chat_screen = self.manager.get_screen("chat")
        query = f"I just measured a blood pressure of {temp_val}/{dia_val} mmHg with a heart rate of {bpm_val} bpm. Is this blood pressure normal? Should I be worried?"
        Clock.schedule_once(lambda dt: chat_screen.trigger_automated_query(query), 0.5)



class HistoryRow(BoxLayout):
    text_content = StringProperty("")
   
    def __init__(self, text_content="", **kwargs):
        super().__init__(**kwargs)
        self.text_content = text_content



class HistoryScreen(Screen):
    _last_click = 0 # New attribute for debounce logic




    def on_enter(self):
        app = App.get_running_app()
        self.ids.history_grid.clear_widgets()
       
        if not app.saved_history:
            # Show "No records" message if empty
            lbl = Label(
                text="No patient records found.",
                color=(0.5, 0.5, 0.5, 1),
                size_hint_y=None,
                height="50dp",
                font_size="16sp"
            )
            self.ids.history_grid.add_widget(lbl)
            if "btn_clear_db" in self.ids: self.ids.btn_clear_db.disabled = True
            return




        # Enable Clear DB button
        if "btn_clear_db" in self.ids: self.ids.btn_clear_db.disabled = False
       
        # Populate the grid with row widgets
        for record in app.saved_history:
            row = HistoryRow(text_content=record)
            self.ids.history_grid.add_widget(row)




    def delete_record(self, row_widget):
        app = App.get_running_app()
        text_to_delete = row_widget.text_content
       
        # 1. Remove from RAM
        if text_to_delete in app.saved_history:
            app.saved_history.remove(text_to_delete)
           
        # 2. Remove from UI
        self.ids.history_grid.remove_widget(row_widget)
       
        # 3. Rewrite File (Overwrite with updated list)
        try:
            with open(LOG_FILE, "w") as f:
                # saved_history is Newest -> Oldest
                # File needs Oldest -> Newest (to append correctly later)
                for line in reversed(app.saved_history):
                    f.write(line + "\n")
        except Exception as e:
            print(f"Error updating file: {e}")
           
        # 4. Handle Empty State
        if not app.saved_history:
            lbl = Label(
                text="No patient records found.",
                color=(0.5, 0.5, 0.5, 1),
                size_hint_y=None,
                height="50dp",
                font_size="16sp"
            )
            self.ids.history_grid.add_widget(lbl)
            if "btn_clear_db" in self.ids: self.ids.btn_clear_db.disabled = True




    def clear_history(self):
        # Debounce to prevent accidental double clicks (1 second wait)
        if time.time() - self._last_click < 1.0: return
        self._last_click = time.time()




        app = App.get_running_app()
        if not app.saved_history: return




        content = Factory.ConfirmPopup()
        content.ids.confirm_msg.text = "Are you sure you want to\ndelete ALL patient logs?"
        content.ids.confirm_button.text = "YES, DELETE ALL"
        content.ids.confirm_button.background_color = (0.8, 0, 0, 1)
       
        self.popup = Popup(
            title="CONFIRM DELETION",
            content=content,
            size_hint=(0.8, 0.45),
            auto_dismiss=False,
            title_size="18sp",
            separator_color=(0.8, 0, 0, 1)
        )
        content.ids.cancel_button.bind(on_release=self.popup.dismiss)
        content.ids.confirm_button.bind(on_release=self.execute_clear_history)
        self.popup.open()




    def execute_clear_history(self, instance):
        self.popup.dismiss()
        app = App.get_running_app()
       
        # 1. Clear RAM
        app.saved_history.clear()
       
        # 2. Clear File
        try:
            with open(LOG_FILE, "w") as f:
                f.write("")
        except Exception:
            pass




        # 3. Clear Widgets and show empty message
        self.ids.history_grid.clear_widgets()
        lbl = Label(
            text="No patient records found.",
            color=(0.5, 0.5, 0.5, 1),
            size_hint_y=None,
            height="50dp",
            font_size="16sp"
        )
        self.ids.history_grid.add_widget(lbl)
       
        if "btn_clear_db" in self.ids:
            self.ids.btn_clear_db.disabled = True



class WindowManager(ScreenManager):
    pass
   
   
   
class ChatScreen(Screen):
    # Attributes for keyboard logic
    debounce_active = False
    caps_enabled = False
    shift_enabled = False
    keyboard_page = 0
    _last_key_down = None # Track last key name
    _last_key_time = 0.0
    shift_button = None
    caps_button = None
    thinking_event = None
    type_event = None
    current_ai_text_accumulator = ""




    def on_enter(self):
        # 1. Clear previous chat widgets to prevent duplicates if returning
        self.ids.messages_layout.clear_widgets()
       
        # 2. Init Keyboard & Styling
        self.build_keyboard()
        Clock.schedule_once(self.force_input_style, 0.1)
       
        # 3. Load History
        self.load_saved_messages()
       
        # 4. Greeting if empty
        app = App.get_running_app()
        if not app.chat_history:
            self.add_medical_greeting()
       
        # 5. Check Online Status (NEW)
        self.check_online_status()




    def on_leave(self):
        # Stop background events when leaving screen
        if self.thinking_event:
            self.thinking_event.cancel()
            self.thinking_event = None
        if self.type_event:
            self.type_event.cancel()
            self.type_event = None




    def check_online_status(self):
        if "ai_status_label" in self.ids:
            self.ids.ai_status_label.text = "Checking connection..."
        threading.Thread(target=self._check_wifi_thread, daemon=True).start()




    def _check_wifi_thread(self):
        is_connected = False
        try:
            if platform.system() == "Windows":
                 # Windows check
                 try:
                    output = subprocess.check_output("netsh wlan show interfaces", shell=True, timeout=2).decode(errors='ignore')
                    if "State" in output and "connected" in output:
                        is_connected = True
                 except: pass
            else:
                # Linux check
                try:
                    output = subprocess.check_output(["sudo", "/usr/bin/nmcli", "-t", "-f", "DEVICE,STATE", "dev"], timeout=2).decode('utf-8', errors='ignore')
                    for line in output.splitlines():
                        if "wlan" in line or "wifi" in line:
                             if ":connected" in line:
                                 is_connected = True
                                 break
                except: pass
        except: pass
        Clock.schedule_once(partial(self._update_status_label, is_connected), 0)




    def _update_status_label(self, is_connected, dt):
        lbl = self.ids.get("ai_status_label")
        if lbl:
            if is_connected:
                lbl.text = "ONLINE • deepseek-v3.1:671b-cloud"
                lbl.color = (0.0, 0.65, 0.6, 1)
            else:
                lbl.text = "OFFLINE • Wi-Fi Disconnected"
                lbl.color = (0.8, 0.3, 0.3, 1)




    def force_input_style(self, dt):
        ti = getattr(self.ids, "input_field", None)
        if ti:
            ti.foreground_color = (0, 0, 0, 1) # Force Black Text
            ti.cursor_color = (0, 0, 0, 1)     # Force Black Cursor
            ti.padding = [10, 4, 10, 4]      
            ti.font_size = "14sp"
            ti.background_normal = ''
            ti.background_active = ''
            ti.background_color = (0, 0, 0, 0)




    def add_medical_greeting(self):
        greeting = "Hello. I am Kairos.\nHow can I help you check your vitals today?"
        self.add_assistant_bubble_static(greeting)




    def clear_chat_history(self):
        self.ids.messages_layout.clear_widgets()
        App.get_running_app().clear_chat_data()
        self.add_medical_greeting()
   
    def go_back_menu(self):
        self.manager.current = "menu"




    def _create_label_for_bubble(self, bubble, text, color=(0, 0, 0, 1)):
        from kivy.uix.label import Label
        lbl = Label(
            text=text, font_size=14, size_hint_y=None,
            halign="left", valign="top", color=color
        )
        lbl.bind(texture_size=lambda inst, size: setattr(inst, 'height', size[1] + 6))
        bubble.bind(width=lambda *a: setattr(lbl, 'text_size', (max(bubble.width - 30, 20), None)))
        lbl.bind(height=lambda inst, h: setattr(bubble, 'height', h + 25))
        return lbl




    def load_saved_messages(self):
        app = App.get_running_app()
        for msg in app.chat_history:
            if msg['role'] == 'user':
                self.add_user_message(msg['text'], save=False)
            else:
                self.add_assistant_bubble_static(msg['text'])




    def add_assistant_bubble_static(self, text):
        from kivy.factory import Factory
        try: bubble = Factory.ChatBubble()
        except Exception:
            from kivy.uix.boxlayout import BoxLayout
            bubble = BoxLayout(size_hint_y=None, padding=10)
       
        lbl = self._create_label_for_bubble(bubble, text, color=(0.2, 0.2, 0.2, 1))
        bubble.add_widget(lbl)
        self.ids.messages_layout.add_widget(bubble)
        Clock.schedule_once(lambda dt: self.scroll_to_bottom(), 0.02)




    def add_user_message(self, text, save=True):
        from kivy.factory import Factory
        try: bubble = Factory.UserBubble()
        except Exception:
            from kivy.uix.boxlayout import BoxLayout
            bubble = BoxLayout(size_hint_y=None, padding=10)
       
        display_text = f"{text}"
        lbl = self._create_label_for_bubble(bubble, display_text, color=(0.1, 0.2, 0.4, 1))
        bubble.add_widget(lbl)
        self.ids.messages_layout.add_widget(bubble)
        Clock.schedule_once(lambda dt: self.scroll_to_bottom(), 0.02)
       
        if save:
            App.get_running_app().save_chat_message("user", text)




    def add_assistant_placeholder(self):
        from kivy.factory import Factory
        try: bubble = Factory.ChatBubble()
        except Exception:
            from kivy.uix.boxlayout import BoxLayout
            bubble = BoxLayout(size_hint_y=None, padding=10)
       
        lbl = self._create_label_for_bubble(bubble, "Analyzing input.", color=(0.4, 0.4, 0.4, 1))
        bubble.add_widget(lbl)
        self.ids.messages_layout.add_widget(bubble)
        Clock.schedule_once(lambda dt: self.scroll_to_bottom(), 0.02)
        return bubble, lbl




    def send_message(self):
        prompt = getattr(self.ids, "input_field", None)
        if not prompt or not prompt.text.strip():
            return
           
        text = prompt.text.strip()
        self.trigger_automated_query(text)
        prompt.text = ""




    def trigger_automated_query(self, text):
        """ Handles both user typed messages and automated system queries """
        self.add_user_message(text, save=True)
       
        self.assistant_bubble, self.assistant_label = self.add_assistant_placeholder()
       
        self.is_thinking = True
        self.thinking_dots = 0
        self.current_ai_text_accumulator = ""
       
        if self.thinking_event: self.thinking_event.cancel()
        self.thinking_event = Clock.schedule_interval(self._thinking_step, 0.5)
       
        threading.Thread(target=self._query_ollama, args=(text,), daemon=True).start()




    def _thinking_step(self, dt):
        self.thinking_dots = (self.thinking_dots + 1) % 4
        if hasattr(self, "assistant_label"):
            self.assistant_label.text = "Analyzing input" + "." * self.thinking_dots
            self.assistant_label.texture_update()
        Clock.schedule_once(lambda dt: self.scroll_to_bottom(), 0)
        return True




    def _query_ollama(self, prompt):
        medical_prompt = f"You are a helpful AI Assistant. Your name is Kairos. Answer concisely and professionally. User asks: {prompt}"
        payload = {"model": MODEL, "prompt": medical_prompt, "stream": True}
       
        try:
            with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=60) as resp:
                if resp.status_code == 200:
                    for line in resp.iter_lines():
                        if line:
                            try:
                                body = json.loads(line.decode('utf-8'))
                                token = body.get("response", "")
                                done = body.get("done", False)
                               
                                if token:
                                    Clock.schedule_once(partial(self._process_stream_chunk, token, False), 0)
                               
                                if done:
                                    Clock.schedule_once(partial(self._process_stream_chunk, "", True), 0)
                                    break
                            except Exception as e:
                                print(f"JSON Parse Error: {e}")
                else:
                    err_msg = f"System Error: {resp.status_code}"
                    Clock.schedule_once(partial(self._process_stream_chunk, err_msg, True), 0)




        except Exception as e:
            err_msg = f"Network Error. Please check connection."
            Clock.schedule_once(partial(self._process_stream_chunk, err_msg, True), 0)




    def _process_stream_chunk(self, token, is_done, dt):
        if self.is_thinking:
            if self.thinking_event:
                self.thinking_event.cancel()
                self.thinking_event = None
           
            self.assistant_label.text = ""
            self.is_thinking = False




        self.assistant_label.text += token
        self.current_ai_text_accumulator += token
       
        Clock.schedule_once(lambda dt: self.scroll_to_bottom(), 0)
       
        if is_done:
            clean_text = self.current_ai_text_accumulator
            App.get_running_app().save_chat_message("assistant", clean_text)




    def scroll_to_bottom(self):
        sv = getattr(self.ids, "messages_scroll", None)
        layout = getattr(self.ids, "messages_layout", None)
        if sv and layout and layout.children:
            sv.scroll_to(layout.children[0])




    def build_keyboard(self, dt=None):
        layout = getattr(self.ids, "keyboard_layout", None)
        if not layout: return
        layout.clear_widgets()
        self.shift_button = None
        self.caps_button = None
       
        if self.keyboard_page == 0:
            rows = [
                ["q","w","e","r","t","y","u","i","o","p"],
                ["a","s","d","f","g","h","j","k","l"],
                ["SHIFT","z","x","c","v","b","n","m","CAPS"],
                ["MORE","CLEAR","SPACE","BACK"]
            ]
        else:
            rows = [
                ["1","2","3","4","5","6","7","8","9","0"],
                ["-","/",":",";","(",")","$","&","@","\""],
                [".",",","?","!","'","\"","+","=","_","*"],
                ["MAIN","CLEAR","SPACE","BACK"]
            ]
       
        key_bg = (0.9, 0.9, 0.9, 1) # UPDATED: Matches WifiScreen (was 0.95)
        for row_keys in rows:
            row = BoxLayout(spacing=4, padding=(2,0))
            for key in row_keys:
                display_text = key
                current_bg = list(key_bg)
                is_capitalized = self.caps_enabled or self.shift_enabled
                if self.keyboard_page == 0 and key.isalpha():
                    display_text = key.upper() if is_capitalized else key.lower()
               
                if key == "SHIFT":
                    if self.shift_enabled: current_bg = [0.0, 0.6, 0.6, 1]
                elif key == "CAPS":
                    if self.caps_enabled: current_bg = [0.0, 0.6, 0.6, 1]




                w_hint = 1.0
                if key == "SPACE": w_hint = 2.5
                elif key in ["SHIFT", "CAPS", "MORE", "MAIN", "BACK", "CLEAR"]: w_hint = 1.3
               
                text_col = (0.2, 0.2, 0.2, 1)
                if current_bg[0] < 0.5: text_col = (1,1,1,1)




                btn = Button(
                    text=display_text, font_size=12, size_hint_x=w_hint,
                    background_normal='', background_color=current_bg, color=text_col
                )
                btn.bind(on_release=partial(self.on_key_press, key, btn))
                row.add_widget(btn)
                if key=="SHIFT": self.shift_button = btn
                if key=="CAPS": self.caps_button = btn
            layout.add_widget(row)




    def on_key_press(self, key_name, instance, *args):
        now = time.time()
        debounce_active = False
       
        if self.debounce_active:
            return
        self.debounce_active = True
        Clock.schedule_once(self.enable_button, 0.2)
       
        self._last_key_down = key_name
        self._last_key_time = now
       
        orig_color = instance.background_color
        instance.background_color = (0.0, 0.8, 0.8, 1)
        if key_name not in ["SHIFT", "CAPS"] or not (self.shift_enabled or self.caps_enabled):
             Clock.schedule_once(lambda dt: setattr(instance, 'background_color', orig_color), 0.1)
       
        key = key_name
        ti = getattr(self.ids, "input_field", None)
        if not ti: return
           
        if key=="SPACE": ti.text+=" "; return
        if key=="BACK": ti.text=ti.text[:-1]; return
        if key=="CLEAR": ti.text=""; return
        if key=="CAPS":
            self.caps_enabled = not self.caps_enabled
            self.build_keyboard() # UPDATED: Direct call
            return
        if key=="SHIFT":
            self.shift_enabled = not self.shift_enabled
            self.build_keyboard() # UPDATED: Direct call
            return
        if key=="MORE": self.keyboard_page=1; self.build_keyboard(); return
        if key=="MAIN": self.keyboard_page=0; self.build_keyboard(); return
       
        if len(key) == 1:
            is_capitalized = (self.caps_enabled or self.shift_enabled) and self.keyboard_page == 0
            ch = instance.text if key.isalpha() else key
            ti.text += ch
            if self.shift_enabled and not self.caps_enabled:
                self.shift_enabled = False
                self.build_keyboard() # UPDATED: Direct call


    def enable_button(self, dt):
        self.debounce_active = False



class SettingsScreen(Screen):
    _last_click = 0

    def go_back_menu(self):
        if time.time() - self._last_click < 0.05: return
        self._last_click = time.time()
        self.manager.current = "menu"

    def open_alarm_settings(self):
        if time.time() - self._last_click < 0.2: return
        self._last_click = time.time()
        self.manager.current = "alarm"  # <--- Update this line




    def open_datetime_settings(self):
        # Debounce to prevent double opening
        if time.time() - self._last_click < 0.2: return
        self._last_click = time.time()
        self.manager.current = "datetime"



class DateTimeScreen(Screen):
    display_hour = StringProperty("12")
    display_minute = StringProperty("00")
    display_ampm = StringProperty("AM")
    display_month = StringProperty("01")
    display_day = StringProperty("01")
    display_year = StringProperty("2025")
    
    # Track the last click time
    _last_click = 0

    def on_enter(self):
        # Update the time display variables
        now = datetime.now()
        self.display_hour = now.strftime("%I")
        self.display_minute = now.strftime("%M")
        self.display_ampm = now.strftime("%p")
        self.display_month = now.strftime("%m")
        self.display_day = now.strftime("%d")
        self.display_year = now.strftime("%Y")

    def adjust_time(self, field, amount):
        # --- DEBOUNCE FIX ---
        if time.time() - self._last_click < 0.05:
            return
        self._last_click = time.time()

        if field == "hour":
            val = int(self.display_hour) + amount
            if val > 12: val = 1
            if val < 1: val = 12
            self.display_hour = f"{val:02d}"
            
        elif field == "minute":
            val = int(self.display_minute) + amount
            if val > 59: val = 0
            if val < 0: val = 59
            self.display_minute = f"{val:02d}"

        elif field == "ampm":
            self.display_ampm = "PM" if self.display_ampm == "AM" else "AM"

        elif field == "month":
            val = int(self.display_month) + amount
            if val > 12: val = 1
            if val < 1: val = 12
            self.display_month = f"{val:02d}"

        elif field == "day":
            val = int(self.display_day) + amount
            if val > 31: val = 1
            if val < 1: val = 31
            self.display_day = f"{val:02d}"

        elif field == "year":
            val = int(self.display_year) + amount
            self.display_year = str(val)

    def save_datetime(self):
        # Longer debounce for the save button (0.5s)
        if time.time() - self._last_click < 0.5: return
        self._last_click = time.time()

        hour_int = int(self.display_hour)
        if self.display_ampm == "PM" and hour_int != 12:
            hour_int += 12
        elif self.display_ampm == "AM" and hour_int == 12:
            hour_int = 0
            
        time_str = f"{hour_int:02d}:{self.display_minute}:00"
        date_str = f"{self.display_year}-{self.display_month}-{self.display_day}"
        new_datetime = f"{date_str} {time_str}"
        
        print(f"Setting System Time to: {new_datetime}")

        if platform.system() == "Linux":
            try:
                cmd = f"sudo date -s '{new_datetime}'"
                os.system(cmd)
                os.system("sudo hwclock -w") 
            except Exception as e:
                print(f"Error setting time: {e}")
        
        self.manager.current = "settings"

    def cancel(self):
        if time.time() - self._last_click < 0.2: return
        self._last_click = time.time()
        self.manager.current = "settings"



class AddAlarmPopup(BoxLayout):
    _last_click = 0

    def adjust_time(self, field, amount):
        # 0.05s debounce to filter out "ghost" double-clicks from hardware
        if time.time() - self._last_click < 0.05: 
            return
        self._last_click = time.time()

        if field == "hour":
            lbl = self.ids.lbl_hour
            val = int(lbl.text) + amount
            if val > 12: val = 1
            if val < 1: val = 12
            lbl.text = f"{val:02d}"

        elif field == "minute":
            lbl = self.ids.lbl_minute
            val = int(lbl.text) + amount
            if val > 59: val = 0
            if val < 0: val = 59
            lbl.text = f"{val:02d}"

        # --- ADDED AM/PM DEBOUNCE LOGIC ---
        elif field == "ampm":
            lbl = self.ids.lbl_ampm
            lbl.text = "PM" if lbl.text == "AM" else "AM"



class AlarmScreen(Screen):
    alarm_list = []
    _last_click = 0
    is_processing = False  # The Safety Lock

    def on_enter(self):
        self.is_processing = False # Reset lock
        self.load_alarms()
        self.render_alarms()


    def go_back_settings(self):
        if time.time() - self._last_click < 0.1: return
        self._last_click = time.time()
        self.manager.current = "settings"

    def load_alarms(self):
        if os.path.exists(ALARM_FILE):
            try:
                with open(ALARM_FILE, "r") as f:
                    self.alarm_list = json.load(f)
            except:
                self.alarm_list = []
        else:
            self.alarm_list = []

    def save_alarms(self):
        try:
            with open(ALARM_FILE, "w") as f:
                json.dump(self.alarm_list, f, indent=4)
        except Exception as e:
            print(f"Error saving alarms: {e}")

    def render_alarms(self):
        grid = self.ids.alarm_grid
        grid.clear_widgets()

        if not self.alarm_list:
            lbl = Label(text="No alarms set.", color=(0.5, 0.5, 0.5, 1), font_size="14sp")
            grid.add_widget(lbl)
            return

        for index, alarm in enumerate(self.alarm_list):
            row = BoxLayout(size_hint_y=None, height="50dp", spacing="10dp")
            
            time_lbl = Label(
                text=alarm['time'], 
                font_size="20sp", 
                bold=True, 
                color=(0.1, 0.2, 0.4, 1),
                size_hint_x=0.6,
                halign="left",
                valign="middle"
            )
            time_lbl.bind(size=time_lbl.setter('text_size'))

            del_btn = Button(
                text="DELETE",
                size_hint_x=0.4,
                background_normal='',
                background_color=(0.8, 0.3, 0.3, 1),
                font_size="12sp",
                bold=True
            )
            del_btn.bind(on_release=partial(self.delete_alarm, index))

            row.add_widget(time_lbl)
            row.add_widget(del_btn)
            grid.add_widget(row)

    def delete_alarm(self, index, instance):
        if time.time() - self._last_click < 0.2: return
        self._last_click = time.time()
        
        if 0 <= index < len(self.alarm_list):
            del self.alarm_list[index]
            self.save_alarms()
            self.render_alarms()

    def show_add_alarm_popup(self):
        if time.time() - self._last_click < 0.3: return
        self._last_click = time.time()
        
        self.is_processing = False # Ensure lock is open
        content = AddAlarmPopup()
        self._popup = Popup(
            title="SET CLINICAL SCHEDULE",
            content=content,
            size_hint=(0.9, 1),
            auto_dismiss=False
        )
        
        content.ids.btn_cancel.bind(on_release=self._popup.dismiss)
        
        # --- THE FIX: Bind the save function here ---
        content.ids.btn_save.bind(on_release=self.execute_one_shot_save)
        
        self._popup.open()

    def execute_one_shot_save(self, instance):
        """ This function is now a 'One-Shot' killer for duplicates """
        
        # 1. IMMEDIATE LOCK: Check if we are already processing
        if self.is_processing:
            return
        self.is_processing = True

        # 2. PHYSICAL UNBIND: Tell the button to forget this function immediately
        instance.unbind(on_release=self.execute_one_shot_save)
        instance.disabled = True
        instance.text = "SAVING..."

        # 3. COLLECT DATA
        content = self._popup.content
        h = content.ids.lbl_hour.text
        m = content.ids.lbl_minute.text
        p = content.ids.lbl_ampm.text
        
        time_str = f"{h}:{m} {p}"
        
        # 4. SAVE AND REFRESH
        self.alarm_list.append({
            "time": time_str, 
            "active": True,
            "label": "Medical Alert" 
        })
        
        self.save_alarms()
        self.render_alarms()
        
        # 5. CLOSE POPUP
        self._popup.dismiss()



class PagtultolApp(App):
    # --- SYSTEM VARIABLES ---
    saved_history = []
    chat_history = []
    
    
    # Track the last alert so we don't spam the user
    last_triggered_time = "" 

    def build(self):
        # 1. Load Patient Logs
        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, "r") as f:
                    lines = [line.strip() for line in f.readlines() if line.strip()]
                    self.saved_history = lines[::-1]
            except Exception as e:
                print(f"Error loading logs: {e}")

        # 2. Load Chat History
        if os.path.exists(CHAT_FILE):
            try:
                with open(CHAT_FILE, "r") as f:
                    self.chat_history = json.load(f)
            except Exception as e:
                self.chat_history = []

        # 3. Setup Screen Manager
        sm = WindowManager(transition=FadeTransition(duration=0.1))
        return sm 

    def on_start(self):
        """
        Starts the internal clock to check for alarms.
        """
        print("[SYSTEM] Medical Alarm Service: ONLINE (800x480 Mode)")
        Clock.schedule_interval(self.service_alarm_check, 1)

    def service_alarm_check(self, dt):
        """
        Runs every 1 second. Checks System Time vs Alarms.json.
        """
        # Get current time (e.g., "08:30 PM")
        now_time = datetime.now().strftime("%I:%M %p").strip().upper()
        
        if not os.path.exists(ALARM_FILE):
            return

        try:
            with open(ALARM_FILE, "r") as f:
                alarms = json.load(f)
            
            if not alarms:
                return

            for alarm in alarms:
                target_time = alarm.get('time', "").strip().upper()
                
                # Check for time match
                if target_time == now_time:
                    # Debounce: Only trigger if we haven't triggered this minute yet
                    if self.last_triggered_time != now_time:
                        print(f"!!! ALARM TRIGGERED: {target_time} !!!")
                        self.last_triggered_time = now_time
                        
                        # Launch the 800x480 Optimized GUI
                        self.trigger_medical_alert(target_time)
                    break 

        except Exception as e:
            print(f"Error in alarm service: {e}")

    def trigger_medical_alert(self, alarm_time):
        """
        Creates a clean medical popup tuned for 800x480 screens.
        """
        
        # Local imports
        # from kivy.graphics import Color, RoundedRectangle

        # --- 1. SETUP THE WHITE CARD BACKGROUND ---
        def update_bg(instance, value):
            instance.canvas.before.clear()
            with instance.canvas.before:
                Color(1, 1, 1, 1)  # Pure White Background
                # Rounded corners (Radius 15 is smoother on smaller screens)
                RoundedRectangle(pos=instance.pos, size=instance.size, radius=[15])
                
            

        # COMPACT PADDING: Reduced from 30dp to 15dp to save space
        content = BoxLayout(orientation='vertical', padding='15dp', spacing='5dp')
        content.bind(pos=update_bg, size=update_bg)

        # --- 2. HEADER (Medical Icon) ---
        # FIXED: Changed from special '✚' to standard '+' so it doesn't show a box
        header_icon = Label(
            text="[b][color=ff3b30]+[/color][/b]", # Standard Plus symbol
            markup=True,
            font_size='60sp', # Made it slightly larger to look like an icon
            size_hint_y=None,
            height='50dp'
        )
        




        # --- 3. STATUS TEXT ---
        # Height: 25dp | Font: 14sp
        status_lbl = Label(
            text="URGENT MEDICAL ALERT",
            font_size='14sp',
            bold=True,
            color=(0.5, 0.5, 0.5, 1),
            size_hint_y=None,
            height='25dp'
        )

        # --- 4. TIME DISPLAY ---
        # Height: 80dp | Font: 55sp (Big enough to read, small enough to fit)
        time_lbl = Label(
            text=alarm_time,
            font_size='55sp', 
            bold=True,
            color=(0.1, 0.1, 0.1, 1),
            size_hint_y=None,
            height='80dp'
        )

        # --- 5. INSTRUCTION ---
        # Takes remaining space | Font: 16sp
        msg_lbl = Label(
            text="Scheduled protocol requires attention.\nPlease verify patient status.",
            halign='center',
            valign='middle',
            font_size='16sp',
            color=(0.3, 0.3, 0.3, 1)
        )
        msg_lbl.bind(size=lambda s, w: setattr(msg_lbl, 'text_size', (w[0], None)))

        # --- 6. ACTION BUTTON ---
        # Height: 60dp | Font: 18sp
        # 60dp is a good touch target size on 480px screens
        ack_btn = Button(
            text="ACKNOWLEDGE",
            size_hint_y=None,
            height='60dp', 
            background_normal='', 
            background_color=(0.0, 0.48, 1.0, 1), # Clinical Blue
            color=(1, 1, 1, 1),
            bold=True,
            font_size='18sp'
        )

        # Add widgets
        content.add_widget(header_icon)
        content.add_widget(status_lbl)
        content.add_widget(time_lbl)
        content.add_widget(msg_lbl)
        content.add_widget(ack_btn)

        # --- 7. CREATE POPUP ---
        # Size Hint: 0.85 Width, 0.9 Height (Maximizes vertical space on 480px)
        popup = Popup(
            title="",
            separator_height=0,
            content=content,
            size_hint=(0.85, 0.9), 
            auto_dismiss=False,
            background_color=(0,0,0,0.7)
        )

        ack_btn.bind(on_release=popup.dismiss)
        popup.open()
        
        

    def save_chat_message(self, role, text):
        """Saves messages to the history file."""
        message_data = {"role": role, "text": text, "timestamp": str(datetime.now())}
        self.chat_history.append(message_data)
        try:
            with open(CHAT_FILE, "w") as f:
                json.dump(self.chat_history, f, indent=4)
        except: pass

    def clear_chat_data(self):
        """Clears the chat storage."""
        self.chat_history = []
        try:
            with open(CHAT_FILE, "w") as f:
                json.dump([], f)
        except: pass



if __name__ == "__main__":
    PagtultolApp().run()


