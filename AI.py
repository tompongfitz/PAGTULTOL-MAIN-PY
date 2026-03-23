import os
from kivy.config import Config
import json
import threading
import requests
import re
import time
import sys
import serial
import subprocess
import platform
import paho.mqtt.client as mqtt
from time import sleep
import RPi.GPIO as GPIO
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
from kivy.uix.widget import Widget
from kivy.core.window import Window
from kivy.properties import StringProperty, BooleanProperty, NumericProperty
from kivy.network.urlrequest import UrlRequest 
from kivy.graphics import Color, RoundedRectangle

ALARM_FILE = "alarms.json"
LOG_FILE = "patient_logs.txt"   
CHAT_FILE = "chat_history.json" 
INVENTORY_FILE = "inventory.json" 
TARGET_PHONE_NUMBER = "+639171234567" 

Config.set('graphics', 'fullscreen', 'auto')
Config.set('graphics', 'window_state', 'maximized')

  
def send_vitals_to_dashboard(sys, dia, hr, classification):
    data = {
        "systolic": sys,
        "diastolic": dia,
        "heart_rate": hr,
        "classification": classification 
    }
    
    payload = json.dumps(data)
    mqtt_client.publish("vitals/data", payload)
    print(f"Published to Node-RED: {payload}")


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def clean_response(text):
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'`(.*?)`', r'\1', text)
    text = re.sub(r'#+ ', '', text)
    return text.strip()


class WifiSignalIcon(Widget):
    strength = NumericProperty(0)


Builder.load_file(resource_path("new design.kv"))


OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "deepseek-v3.1:671b-cloud"

mqtt_client = mqtt.Client()

try:
    mqtt_client.connect("localhost", 1883, 60)
    mqtt_client.loop_start()
except Exception as e:
    print(f"MQTT Connection Error: {e}")
   
   
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
        self.update_clock(0)
        self.clock_event = Clock.schedule_interval(self.update_clock, 1)
        
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
        now = datetime.now()
        time_str = now.strftime("%I:%M:%S %p")
        date_str = now.strftime("%b %d, %Y")
        
        try:
            self.ids.menu_clock.text = time_str
            self.ids.menu_date.text = date_str
        except Exception:
            pass
   
   
    def check_wifi_status(self, dt):
        threading.Thread(target=self._perform_wifi_check, daemon=True).start()


    def _perform_wifi_check(self):
        is_connected = False
        signal_level = 0
        try:
            if platform.system() == "Windows":
                try:
                    output = subprocess.check_output("netsh wlan show interfaces", shell=True, timeout=3).decode(errors='ignore')
                    if "State" in output and "connected" in output:
                        is_connected = True
                        for line in output.splitlines():
                            if "Signal" in line:
                                sig_str = line.split(":")[-1].strip().replace('%', '')
                                try:
                                    signal_level = int(sig_str)
                                except:
                                    signal_level = 100
                                break
                except: pass
            else:
                try:
                    output = subprocess.check_output(["sudo", "/usr/bin/nmcli", "-t", "-f", "ACTIVE,SIGNAL", "dev", "wifi"], timeout=3).decode('utf-8', errors='ignore')
                    for line in output.splitlines():
                        if line.startswith("yes:"):
                            is_connected = True
                            parts = line.split(":")
                            if len(parts) > 1:
                                try:
                                    signal_level = int(parts[1])
                                except:
                                    signal_level = 100
                            break
                    
                    if not is_connected:
                        output2 = subprocess.check_output(["sudo", "/usr/bin/nmcli", "-t", "-f", "DEVICE,STATE", "dev"], timeout=3).decode('utf-8', errors='ignore')
                        for line in output2.splitlines():
                            if ("wlan" in line or "wifi" in line) and ":connected" in line:
                                is_connected = True
                                signal_level = 75 
                                break
                except: pass
        except Exception as e:
            print(f"Wifi Check Error: {e}")
        finally:
            Clock.schedule_once(partial(self._update_wifi_button, is_connected, signal_level), 0)


    def _update_wifi_button(self, is_connected, signal_level, dt):
        status_text = "CONNECTED" if is_connected else "NOT CONNECTED"
        color_hex = "00FF00" if is_connected else "FF5555"
        
        if self.ids.get("wifi_btn"):
            self.ids.wifi_btn.text = f"[size=18][b]WI-FI SETTINGS[/b][/size]\n[size=12]Network Configuration\nStatus: [color={color_hex}]{status_text}[/color][/size]"

        ai_status = "ONLINE" if is_connected else "OFFLINE"
        ai_color = "AAFFAA" if is_connected else "FF5555"
        if self.ids.get("ai_btn"):
            self.ids.ai_btn.text = f"[size=18][b]AI ASSISTANT[/b][/size]\n[size=12]Interactive Chat Module\nSystem Status: [color={ai_color}]{ai_status}[/color][/size]"

        strength = 0
        if is_connected:
            if signal_level > 80: strength = 4
            elif signal_level > 60: strength = 3
            elif signal_level > 30: strength = 2
            else: strength = 1
            
        if "menu_wifi_icon" in self.ids:
            self.ids.menu_wifi_icon.strength = strength
            
        if "menu_wifi_label" in self.ids:
            self.ids.menu_wifi_label.text = f"{signal_level}%" if is_connected else "Offline"


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
        if time.time() - self._last_click < 0.5:
            return
        self._last_click = time.time()

        content = Factory.PowerPopup()
        self._power_popup = Popup(
            title="MAINTENANCE",  
            content=content,
            size_hint=(0.7, 0.5), 
            auto_dismiss=True,
            title_size="14sp",
            title_color=(0.2, 0.6, 1, 1), 
            separator_color=(0.9, 0.9, 0.9, 1), 
            background_color=(0.95, 0.95, 0.95, 1) 
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
    caps_enabled = False
    shift_enabled = False
    keyboard_page = 0
    _last_key_down = None 
    _last_key_time = 0.0
    _last_click = 0.0
    selected_ssid = ""
    cached_networks = []  
    expanded_ssid = None  


    def __init__(self, **kwargs):
        super(WifiScreen, self).__init__(**kwargs)
        self.selected_ssid = ""

    
    def on_enter(self):
        self.ids.wifi_sm.current = "list"
        if self.ids.wifi_switch.active:
            self.scan_wifi()
        else:
            self.ids.wifi_status.text = "Wi-Fi is disabled."
            self.ids.wifi_list_layout.clear_widgets()


    def go_back_menu(self):
        self.manager.current = "menu"


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
        if platform.system() != "Windows":
            state = "on" if turn_on else "off"
            try:
                subprocess.run(["sudo", "/usr/bin/nmcli", "radio", "wifi", state])
            except Exception:
                pass


    def scan_wifi(self):
        if self.scanning: return
        if not self.ids.wifi_switch.active:
            self.ids.wifi_status.text = "Wi-Fi is off. Enable to scan."
            return

        self.scanning = True
        self.expanded_ssid = None 
        self.ids.wifi_status.text = "Scanning for networks..."
        self.ids.wifi_list_layout.clear_widgets()
        threading.Thread(target=self._perform_scan, daemon=True).start()


    def _perform_scan(self):
        networks_data = []
        found_ssids = set()
        system = platform.system()
        
        try:
            if system == "Windows":
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
                    pass
            else:
                try:
                    subprocess.run(["sudo", "/usr/bin/nmcli", "device", "wifi", "rescan"], timeout=5)
                except Exception:
                    pass
                
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
                    pass
                            
        except Exception as e:
            Clock.schedule_once(lambda dt: self._update_status(f"Scan Error"), 0)
            self.scanning = False
            return

        networks_data.sort(key=lambda x: (not x['active'], x['ssid']))
        self.cached_networks = networks_data
        Clock.schedule_once(lambda dt: self._render_network_list(), 0)


    def _update_status(self, text):
        self.ids.wifi_status.text = text


    def _render_network_list(self):
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
            
            if self.expanded_ssid == ssid:
                box = BoxLayout(orientation='vertical', size_hint_y=None, height="110dp", spacing=0)
                
                with box.canvas.before:
                    Color(0.9, 1, 0.9, 1) 
                    RoundedRectangle(pos=box.pos, size=box.size, radius=[6,])
                
                def update_canvas(instance, value):
                    instance.canvas.before.clear()
                    with instance.canvas.before:
                        Color(0.9, 1, 0.9, 1)
                        RoundedRectangle(pos=instance.pos, size=instance.size, radius=[6,])
                box.bind(pos=update_canvas, size=update_canvas)

                btn_top = Button(
                    text=f"{ssid} (Connected)",
                    background_normal='',
                    background_color=(0,0,0,0), 
                    color=(0, 0.6, 0.2, 1),
                    bold=True,
                    font_size=14,
                    size_hint_y=0.6
                )
                btn_top.bind(on_release=lambda x, s=ssid: self.toggle_expand(s))

                btn_container = BoxLayout(padding=[40, 5, 40, 10], size_hint_y=0.4)
                btn_action = Button(
                    text="DISCONNECT",
                    background_normal='',
                    background_color=(0.8, 0.3, 0.3, 1), 
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
                    btn.bind(on_release=lambda x, s=ssid: self.toggle_expand(s))
                else:
                    btn.bind(on_release=partial(self.prepare_connection, ssid))
                
                self.ids.wifi_list_layout.add_widget(btn)


    def toggle_expand(self, ssid):
        if self.expanded_ssid == ssid:
            self.expanded_ssid = None 
        else:
            self.expanded_ssid = ssid 
        self._render_network_list()


    def disconnect_wifi(self, ssid):
        self.ids.wifi_status.text = f"Disconnecting {ssid}..."
        threading.Thread(target=self._perform_disconnect, args=(ssid,), daemon=True).start()


    def _perform_disconnect(self, ssid):
        if platform.system() != "Windows":
            try:
                subprocess.run(["sudo", "/usr/bin/nmcli", "connection", "down", "id", ssid], capture_output=True, timeout=10)
            except Exception as e:
                pass
        Clock.schedule_once(lambda dt: self.scan_wifi(), 1.0)


    def has_saved_profile(self, ssid):
        if platform.system() == "Windows":
            return False 
        try:
            output = subprocess.check_output(["sudo", "/usr/bin/nmcli", "-g", "NAME", "connection", "show"], timeout=2).decode('utf-8')
            profiles = output.strip().split('\n')
            return ssid in profiles
        except:
            return False


    def prepare_connection(self, ssid, instance):
        if self.has_saved_profile(ssid):
            self.ids.wifi_status.text = f"Connecting to saved network: {ssid}..."
            threading.Thread(target=self._perform_saved_connection, args=(ssid,), daemon=True).start()
            return
        self._show_password_screen(ssid)


    def _show_password_screen(self, ssid):
        self.selected_ssid = ssid
        self.ids.pass_prompt.text = f"Enter Password for: {ssid}"
        self.ids.pass_input.text = ""
        
        self.ids.pass_input.password = True
        if "btn_show_pass" in self.ids:
            self.ids.btn_show_pass.text = "SHOW"
            self.ids.btn_show_pass.background_color = (0.8, 0.8, 0.8, 1)
            self.ids.btn_show_pass.color = (0.2, 0.2, 0.2, 1)

        self.ids.wifi_sm.current = "password"
        
        self.caps_enabled = False
        self.shift_enabled = False
        self.keyboard_page = 0
        self.build_keyboard()


    def toggle_show_password(self):
        if time.time() - getattr(self, '_last_click', 0) < 0.1: return
        self._last_click = time.time()
        
        ti = self.ids.pass_input
        btn = self.ids.btn_show_pass
        
        ti.password = not ti.password
        
        if ti.password:
            btn.text = "SHOW"
            btn.background_color = (0.8, 0.8, 0.8, 1)
            btn.color = (0.2, 0.2, 0.2, 1)
        else:
            btn.text = "HIDE"
            btn.background_color = (0.2, 0.6, 1, 1)
            btn.color = (1, 1, 1, 1)


    def _perform_saved_connection(self, ssid):
        success = False
        try:
            res = subprocess.run(["sudo", "/usr/bin/nmcli", "connection", "up", "id", ssid], capture_output=True, timeout=15)
            if res.returncode == 0:
                success = True
        except Exception as e:
            pass
        
        if success:
            Clock.schedule_once(lambda dt: self.scan_wifi(), 2.0)
        else:
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
                try:
                    subprocess.run(["sudo", "/usr/bin/nmcli", "connection", "delete", "id", ssid], capture_output=True, timeout=5)
                except subprocess.TimeoutExpired:
                    pass

                cmd_add = [
                    "sudo", "/usr/bin/nmcli", "connection", "add",
                    "type", "wifi",
                    "con-name", ssid,
                    "ifname", "wlan0", 
                    "ssid", ssid,
                    "802-11-wireless-security.key-mgmt", "wpa-psk",
                    "802-11-wireless-security.psk", password
                ]
                
                result_add = subprocess.run(cmd_add, capture_output=True, text=True, timeout=15)
                
                if result_add.returncode == 0:
                    cmd_up = ["sudo", "/usr/bin/nmcli", "connection", "up", ssid]
                    result_up = subprocess.run(cmd_up, capture_output=True, text=True, timeout=15)
                    
                    if result_up.returncode == 0:
                        success = True
        except Exception as e:
            pass
        
        Clock.schedule_once(lambda dt: self.scan_wifi(), 2.0)


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
        
        if now - self._last_key_time < 0.1:
            return

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
    
    auto_action_event = None    

    def on_enter(self):
        self.stop_thread = False
        app = App.get_running_app()
        
        if "btn_take_medicine" in self.ids:
            if app.can_take_medicine:
                self.ids.btn_take_medicine.disabled = False
                self.ids.btn_take_medicine.background_color = (0.2, 0.7, 0.5, 1) 
            else:
                self.ids.btn_take_medicine.disabled = True
                self.ids.btn_take_medicine.background_color = (0.3, 0.3, 0.3, 1) 

        self.ids.btn_scan.disabled = False
        self._set_exit_buttons_state(disabled=False)
        
        if self.has_unsaved_data:
            self.ids.btn_scan.text = "RECORD\nREADING"
            self.ids.btn_scan.background_color = (0.1, 0.7, 0.2, 1) 
            self.ids.vitals_status.text = "DATA RESTORED - RECORD TO SAVE"
            self.ids.vitals_status.color = (0, 0.7, 0, 1)
            self.update_labels(self.bp_sys, self.bp_dia, self.bp_bpm, 0)
        else:
            self.is_monitoring = False
            
            if app.medication_pending and not app.can_take_medicine:
                self.ids.vitals_status.text = "TAKE BP FIRST TO UNLOCK MEDICINE"
                self.ids.vitals_status.color = (0.9, 0.6, 0.1, 1) 
            else:
                self.ids.vitals_status.text = "STANDBY - PRESS START"
                self.ids.vitals_status.color = (0.5, 0.5, 0.5, 1)
                
            self.ids.btn_scan.text = "START\nMONITORING"
            self.ids.btn_scan.background_color = (0.2, 0.6, 1, 1) 
            self.ids.vitals_temp.text = "-SYSTOLIC-"
            self.ids.vitals_dia.text = "-DIASTOLIC-"
            self.ids.vitals_bpm.text = "-HEART RATE-"
            self.ids.classification.text = "----"
            self.ids.classification.color = (0, 0, 0, 1)

        threading.Thread(target=self.read_arduino_data, daemon=True).start()

    def on_leave(self):
        self.stop_thread = True
        self.is_monitoring = False
        if self.ser and self.ser.is_open:
            self.ser.close()
        
        if self.auto_action_event:
            self.auto_action_event.cancel()
            self.auto_action_event = None

    def _set_exit_buttons_state(self, disabled):
        opacity = 0.3 if disabled else 1.0
        if "btn_back" in self.ids:
            self.ids.btn_back.disabled = disabled
            self.ids.btn_back.opacity = opacity

    def go_back_menu(self):
        if self.is_monitoring:
            return
        if time.time() - self._last_click < 0.05: return
        self._last_click = time.time()
        self.manager.current = "menu"

    def toggle_monitoring(self):
        if time.time() - self._last_click < 0.3: return
        self._last_click = time.time()

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
        self.ids.btn_scan.disabled = False

    def start_scanning(self):
        if self.auto_action_event:
            self.auto_action_event.cancel()
            self.auto_action_event = None

        self.is_monitoring = True
        self.has_unsaved_data = False
        self._set_exit_buttons_state(disabled=True)
        
        self.ids.btn_scan.text = "STOP\nMONITORING"
        self.ids.btn_scan.background_color = (0.8, 0.3, 0.3, 1)
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
        if self.auto_action_event:
            self.auto_action_event.cancel()
            self.auto_action_event = None

        self.is_monitoring = False
        self.has_unsaved_data = False
        self._set_exit_buttons_state(disabled=False)
        
        if self.ser and self.ser.is_open:
            try: self.ser.write(b"STOP\n")
            except Exception as e: print(f"Serial Write Error: {e}")
            
        self.ids.btn_scan.text = "START\nMONITORING"
        self.ids.btn_scan.background_color = (0.2, 0.6, 1, 1)
        
        app = App.get_running_app()
        if app.medication_pending and not app.can_take_medicine:
            self.ids.vitals_status.text = "TAKE BP FIRST TO UNLOCK MEDICINE"
            self.ids.vitals_status.color = (0.9, 0.6, 0.1, 1)
        else:
            self.ids.vitals_status.text = "STANDBY - ABORTED"
            self.ids.vitals_status.color = (0.5, 0.5, 0.5, 1)

    def trigger_auto_action(self, dt):
        app = App.get_running_app()
        if self.has_unsaved_data:
            self.save_reading()
        
        if app.medication_pending and app.can_take_medicine:
            Clock.schedule_once(lambda x: app.take_medicine_action(), 1.5)
    
    def transition_to_record_mode(self, dt):
        self.is_monitoring = False
        self.has_unsaved_data = True
        self._set_exit_buttons_state(disabled=False)
        
        self.ids.btn_scan.text = "RECORD\nREADING"
        self.ids.btn_scan.background_color = (0.1, 0.7, 0.2, 1)
        
        app = App.get_running_app()
        
        if app.medication_pending:
            self.ids.vitals_status.text = "BP ACQUIRED - AUTO DISPENSE IN 10S"
            self.ids.vitals_status.color = (0.2, 0.7, 0.5, 1)
            app.check_and_unlock_medicine()
        else:
            self.ids.vitals_status.text = "SCAN COMPLETE - AUTO RECORD IN 10S"
            self.ids.vitals_status.color = (0, 0.7, 0, 1)

        if self.auto_action_event:
            self.auto_action_event.cancel()
        self.auto_action_event = Clock.schedule_once(self.trigger_auto_action, 10.0)

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
                elif sys < 0:
                    self.ids.classification.text = "Error. Try Again"
                    self.ids.classification.color = (0.8, 0.3, 0.3, 1)
                    self.ids.vitals_temp.text = "Error"
                    self.ids.vitals_dia.text = "Error"
                    self.ids.vitals_bpm.text = "Error"
            except ValueError:
                pass

            if self.is_monitoring:
                Clock.schedule_once(self.transition_to_record_mode, 0.2)

    def save_reading(self):
        if self.auto_action_event:
            self.auto_action_event.cancel()
            self.auto_action_event = None

        if self.ids.vitals_temp.text == "Error" or self.ids.vitals_temp.text == "-SYSTOLIC-":
            self.ids.vitals_status.text = "ERROR: NO DATA TO SAVE"
            self.ids.vitals_status.color = (1, 0, 0, 1)
            Clock.schedule_once(self.return_to_standby_status, 1.5)
            self.has_unsaved_data = False
            return

        temp_val = self.bp_sys
        dia_val = self.bp_dia
        bpm_val = self.bp_bpm
        now = datetime.now()        
        timestamp = now.strftime("%Y-%m-%d  %I:%M %p")
        entry = f"[{timestamp}]       Blood Pressure: {temp_val}/{dia_val}mmHg       Heart Rate:  {bpm_val}bpm"
        
        app = App.get_running_app()
        app.saved_history.insert(0, entry)
        
        try:
            with open(LOG_FILE, "a") as f:
                f.write(entry + "\n")
        except Exception as e:
            pass

        if self.ser and self.ser.is_open:
            try:
                self.ser.write(b"SEND\n")
                sms_cmd = f"SMS:{TARGET_PHONE_NUMBER}:{temp_val}/{dia_val} BP {bpm_val} BPM\n"
                self.ser.write(sms_cmd.encode('utf-8'))
            except Exception as e:
                pass

        self.is_monitoring = False
        self.has_unsaved_data = False

        self.ids.btn_scan.text = "SAVED"
        
        if app.medication_pending:
            self.ids.vitals_status.text = "SAVED! PLEASE TAKE YOUR MEDICINE."
            self.ids.vitals_status.color = (0.9, 0.6, 0.1, 1)
            send_vitals_to_dashboard(temp_val, dia_val, bpm_val, self.ids.classification.text)
        else:
            self.ids.vitals_status.text = "SAVED! CONSULTING AI..."
            self.ids.vitals_status.color = (0.07, 0.5, 0.17, 1)
            Clock.schedule_once(partial(self.redirect_to_ai, temp_val, dia_val, bpm_val), 1.0)
            send_vitals_to_dashboard(temp_val, dia_val, bpm_val, self.ids.classification.text)

    def return_to_standby_status(self, dt):
        self.ids.vitals_status.text = "STANDBY - PRESS START"
        self.ids.vitals_status.color = (0.5, 0.5, 0.5, 1)
        self.ids.btn_scan.text = "START\nMONITORING"
        self.ids.btn_scan.background_color = (0.2, 0.6, 1, 1)

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
    _last_click = 0 

    def on_enter(self):
        app = App.get_running_app()
        self.ids.history_grid.clear_widgets()
        
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
            return

        if "btn_clear_db" in self.ids: self.ids.btn_clear_db.disabled = False
        
        for record in app.saved_history:
            row = HistoryRow(text_content=record)
            self.ids.history_grid.add_widget(row)

    def delete_record(self, row_widget):
        app = App.get_running_app()
        text_to_delete = row_widget.text_content
        
        if text_to_delete in app.saved_history:
            app.saved_history.remove(text_to_delete)
            
        self.ids.history_grid.remove_widget(row_widget)
        
        try:
            with open(LOG_FILE, "w") as f:
                for line in reversed(app.saved_history):
                    f.write(line + "\n")
        except Exception as e:
            pass
            
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
        
        app.saved_history.clear()
        
        try:
            with open(LOG_FILE, "w") as f:
                f.write("")
        except Exception:
            pass

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
    debounce_active = False
    caps_enabled = False
    shift_enabled = False
    keyboard_page = 0
    _last_key_down = None 
    _last_key_time = 0.0
    shift_button = None
    caps_button = None
    thinking_event = None
    type_event = None
    current_ai_text_accumulator = ""


    def on_enter(self):
        self.ids.messages_layout.clear_widgets()
        self.build_keyboard()
        Clock.schedule_once(self.force_input_style, 0.1)
        self.load_saved_messages()
        
        app = App.get_running_app()
        if not app.chat_history:
            self.add_medical_greeting()
        
        self.check_online_status()

    def on_leave(self):
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
                 try:
                    output = subprocess.check_output("netsh wlan show interfaces", shell=True, timeout=2).decode(errors='ignore')
                    if "State" in output and "connected" in output:
                        is_connected = True
                 except: pass
            else:
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
            ti.foreground_color = (0, 0, 0, 1) 
            ti.cursor_color = (0, 0, 0, 1)      
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
                                pass
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
        if sv:
            sv.scroll_y = 0

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
            self.build_keyboard() 
            return
        if key=="SHIFT":
            self.shift_enabled = not self.shift_enabled
            self.build_keyboard() 
            return
        if key=="MORE": self.keyboard_page=1; self.build_keyboard(); return
        if key=="MAIN": self.keyboard_page=0; self.build_keyboard(); return
        
        if len(key) == 1:
            ch = instance.text if key.isalpha() else key
            ti.text += ch
            if self.shift_enabled and not self.caps_enabled:
                self.shift_enabled = False
                self.build_keyboard() 

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
        self.manager.current = "alarm"  

    def open_datetime_settings(self):
        if time.time() - self._last_click < 0.2: return
        self._last_click = time.time()
        self.manager.current = "datetime"



class PillManagementScreen(Screen):
    pass
    
    
    
class DateTimeScreen(Screen):
    display_hour = StringProperty("12")
    display_minute = StringProperty("00")
    display_ampm = StringProperty("AM")
    display_month = StringProperty("01")
    display_day = StringProperty("01")
    display_year = StringProperty("2025")
    _last_click = 0

    def on_enter(self):
        now = datetime.now()
        self.display_hour = now.strftime("%I")
        self.display_minute = now.strftime("%M")
        self.display_ampm = now.strftime("%p")
        self.display_month = now.strftime("%m")
        self.display_day = now.strftime("%d")
        self.display_year = now.strftime("%Y")

    def adjust_time(self, field, amount):
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
        elif field == "ampm":
            lbl = self.ids.lbl_ampm
            lbl.text = "PM" if lbl.text == "AM" else "AM"



class AlarmScreen(Screen):
    alarm_list = []
    _last_click = 0
    is_processing = False 

    def on_enter(self):
        self.is_processing = False 
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
        
        self.is_processing = False 
        content = AddAlarmPopup()
        self._popup = Popup(
            title="SET CLINICAL SCHEDULE",
            content=content,
            size_hint=(0.9, 1),
            auto_dismiss=False
        )
        content.ids.btn_cancel.bind(on_release=self._popup.dismiss)
        content.ids.btn_save.bind(on_release=self.execute_one_shot_save)
        self._popup.open()

    def execute_one_shot_save(self, instance):
        if self.is_processing:
            return
        self.is_processing = True

        instance.unbind(on_release=self.execute_one_shot_save)
        instance.disabled = True
        instance.text = "SAVING..."

        content = self._popup.content
        h = content.ids.lbl_hour.text
        m = content.ids.lbl_minute.text
        p = content.ids.lbl_ampm.text
        
        time_str = f"{h}:{m} {p}"
        
        self.alarm_list.append({
            "time": time_str, 
            "active": True,
            "label": "Medical Alert" 
        })
        
        self.save_alarms()
        self.render_alarms()
        self._popup.dismiss()


class PagtultolApp(App):
    saved_history = []
    chat_history = []
    _last_click_time = 0.0
    _is_warning_open = False
    last_triggered_time = "" 
    buzzer_event = None
    buzzer_state = False
    _alert_popup = None
    auto_dismiss_event = None 
    pill_count = NumericProperty(1) 
    medication_pending = BooleanProperty(False) 
    can_take_medicine = BooleanProperty(False) 
    arduino_serial = None

    def load_inventory(self):
        if os.path.exists(INVENTORY_FILE):
            try:
                with open(INVENTORY_FILE, "r") as f:
                    data = json.load(f)
                    self.pill_count = data.get("pill_count", 1)
            except Exception as e:
                print(f"Error loading inventory: {e}")

    def save_inventory(self):
        try:
            with open(INVENTORY_FILE, "w") as f:
                json.dump({"pill_count": self.pill_count}, f)
        except Exception as e:
            print(f"Error saving inventory: {e}")

    def check_debounce(self, wait_time=0.5):
        current_time = time.time()
        if current_time - self._last_click_time < wait_time:
            return False 
        self._last_click_time = current_time
        return True 

    def build(self):
        self.load_inventory() 

        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, "r") as f:
                    lines = [line.strip() for line in f.readlines() if line.strip()]
                    self.saved_history = lines[::-1]
            except Exception as e:
                print(f"Error loading logs: {e}")

        if os.path.exists(CHAT_FILE):
            try:
                with open(CHAT_FILE, "r") as f:
                    self.chat_history = json.load(f)
            except Exception as e:
                self.chat_history = []

        sm = WindowManager(transition=FadeTransition(duration=0.1))
        return sm 

    def manual_decrement(self):
        if not self.check_debounce(): return 
        if self.pill_count > 0:
            self.pill_count -= 1
            self.save_inventory()
            print(f"Manual adjust: Pills remaining: {self.pill_count}")

    def manual_increment(self):
        if not self.check_debounce(): return 
        if self.pill_count < 7:
            self.pill_count += 1
            self.save_inventory()
            print(f"Manual adjust: Pills remaining: {self.pill_count}")

    def restock_inventory(self):
        if self.check_debounce():
            self.pill_count = 7
            self.save_inventory()
            print("Inventory Restocked to 7.")

    @mainthread
    def unlock_medicine_button(self):
        self.medication_pending = True
        self.can_take_medicine = False
        if self.root and self.root.has_screen('vitals'):
            vitals_screen = self.root.get_screen('vitals')
            if 'btn_take_medicine' in vitals_screen.ids:
                med_btn = vitals_screen.ids.btn_take_medicine
                med_btn.disabled = True
                med_btn.background_color = (0.3, 0.3, 0.3, 1) 

    @mainthread
    def check_and_unlock_medicine(self):
        if self.medication_pending:
            self.can_take_medicine = True
            if self.root and self.root.has_screen('vitals'):
                vitals_screen = self.root.get_screen('vitals')
                if 'btn_take_medicine' in vitals_screen.ids:
                    med_btn = vitals_screen.ids.btn_take_medicine
                    med_btn.disabled = False
                    med_btn.background_color = (0.2, 0.7, 0.5, 1) 

    def take_medicine_action(self):
        if not self.check_debounce(wait_time=1.0): 
            return

        if self.pill_count <= 0:
            self.show_empty_dispenser_warning()
            return

        is_last_pill = (self.pill_count == 1)
        
        self.pill_count -= 1
        self.save_inventory() 
        self.send_rotate_command()
        
        if self.buzzer_event:
            self.buzzer_event.cancel()
            self.buzzer_event = None
        try: GPIO.output(17, 0)
        except Exception: pass
            
        self.medication_pending = False
        self.can_take_medicine = False
        
        if self.root and self.root.has_screen('vitals'):
            vitals_screen = self.root.get_screen('vitals')
            if 'btn_take_medicine' in vitals_screen.ids:
                med_btn = vitals_screen.ids.btn_take_medicine
                med_btn.disabled = True
                med_btn.background_color = (0.3, 0.3, 0.3, 1)
                
            if vitals_screen.ids.btn_scan.text == "SAVED":
                vitals_screen.ids.vitals_status.text = "MEDICINE DISPENSED! CONSULTING AI..."
                vitals_screen.ids.vitals_status.color = (0.07, 0.5, 0.17, 1)
                Clock.schedule_once(partial(vitals_screen.redirect_to_ai, vitals_screen.bp_sys, vitals_screen.bp_dia, vitals_screen.bp_bpm), 1.5)
            else:
                vitals_screen.ids.vitals_status.text = "MEDICINE DISPENSED! PRESS RECORD."
                vitals_screen.ids.vitals_status.color = (0.2, 0.7, 0.5, 1)

        if is_last_pill:
            Clock.schedule_once(lambda dt: self.show_empty_dispenser_warning(), 2.0)

    def show_empty_dispenser_warning(self):
        if self._is_warning_open:
            return
        self._is_warning_open = True 
        
        content = BoxLayout(orientation='vertical', padding="20dp", spacing="15dp")
        warning_msg = Label(
            text="Medication dispenser is currently empty.\n\nPlease refill the physical chamber and update the system inventory.",
            halign="center", 
            valign="middle",
            font_size="18sp",
            color=(0.2, 0.2, 0.2, 1) 
        )
        warning_msg.bind(size=warning_msg.setter('text_size')) 
        
        close_btn = Button(
            text="ACKNOWLEDGE", 
            size_hint_y=None, 
            height="80dp",
            font_size="20sp",
            bold=True,  
            background_normal='',
            background_color=(0.8, 0.2, 0.2, 1) 
        )
        
        content.add_widget(warning_msg)
        content.add_widget(close_btn)
        
        empty_popup = Popup(
            title="ATTENTION: MEDICATION REFILL REQUIRED",
            content=content,
            size_hint=(0.8, 0.5),
            auto_dismiss=False, 
            title_size="18sp",
            title_color=(0.8, 0.2, 0.2, 1), 
            separator_color=(0.8, 0.2, 0.2, 1), 
            background="",  
            background_color=(1, 1, 1, 1) 
        )
        
        empty_popup.bind(on_dismiss=lambda *x: setattr(self, '_is_warning_open', False))
        close_btn.bind(on_release=empty_popup.dismiss)
        empty_popup.open()


    def on_start(self):
        try:
            self.arduino_serial = serial.Serial('/dev/ttyACM0', baudrate=9600, timeout=1)
        except Exception:
            self.arduino_serial = None
            
        Clock.schedule_interval(self.service_alarm_check, 1)

    def service_alarm_check(self, dt):
        now_time = datetime.now().strftime("%I:%M %p").strip().upper()
        if not os.path.exists(ALARM_FILE): return

        try:
            with open(ALARM_FILE, "r") as f:
                alarms = json.load(f)
            if not alarms: return

            for alarm in alarms:
                target_time = alarm.get('time', "").strip().upper()
                if target_time == now_time:
                    if self.last_triggered_time != now_time:
                        self.last_triggered_time = now_time
                        self.trigger_medical_alert(target_time)
                    break 
        except Exception: pass

    def trigger_medical_alert(self, message="It is time for your scheduled medication."):
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(17, GPIO.OUT)
            GPIO.output(17, 1)  
        except Exception: pass

        content = Factory.MedicalAlertContent()
        content.ids.alert_message.text = message
        if hasattr(content.ids, 'alert_message'):
            content.ids.alert_message.color = (0.2, 0.2, 0.2, 1)

        if hasattr(content.ids, 'btn_vitals'):
            content.ids.btn_vitals.size_hint_y = None
            content.ids.btn_vitals.height = "80dp"
            content.ids.btn_vitals.font_size = "22sp"

        self._alert_popup = Popup(
            title="PATIENT ALERT: MEDICATION DUE",
            content=content,
            size_hint=(0.8, 0.55),
            auto_dismiss=False, 
            title_size="16sp",
            title_color=(0.1, 0.2, 0.4, 1), 
            separator_color=(0.2, 0.6, 0.9, 1), 
            background="",  
            background_color=(1, 1, 1, 1) 
        )

        def on_proceed_click(*args):
            if self.auto_dismiss_event:
                self.auto_dismiss_event.cancel()
                self.auto_dismiss_event = None
                
            self._alert_popup.dismiss()
            if self.buzzer_event:
                self.buzzer_event.cancel()
                self.buzzer_event = None
            try: GPIO.output(17, 0)
            except Exception: pass
            self.unlock_medicine_button()
            if self.root: self.root.current = 'vitals'

        content.ids.btn_vitals.bind(on_release=on_proceed_click)
        Clock.schedule_once(self.show_popup_and_loop, 1.0)
        
        if self.auto_dismiss_event:
            self.auto_dismiss_event.cancel()
        self.auto_dismiss_event = Clock.schedule_once(self.auto_dismiss_alarm, 300.0)

    def auto_dismiss_alarm(self, dt):
        self.auto_dismiss_event = None
        if self._alert_popup:
            self._alert_popup.dismiss()
        
        if self.buzzer_event:
            self.buzzer_event.cancel()
            self.buzzer_event = None
            
        try: GPIO.output(17, 0)
        except Exception: pass
        
        self.send_warning_command()
        print("Alarm automatically dismissed. WARNING sent to Arduino.")

    def send_warning_command(self):
        if self.root and self.root.has_screen('vitals'):
            vitals_screen = self.root.get_screen('vitals')
            if hasattr(vitals_screen, 'ser') and vitals_screen.ser and vitals_screen.ser.is_open:
                try:
                    vitals_screen.ser.write(b"WARNING\n")
                    return
                except Exception: pass

        if self.arduino_serial and self.arduino_serial.is_open:
            try: self.arduino_serial.write(b"WARNING\n")
            except Exception: pass
    
    def show_popup_and_loop(self, dt):
        try: GPIO.output(17, 0)
        except Exception: pass
        if self._alert_popup: self._alert_popup.open()
        self.buzzer_state = False
        self.buzzer_event = Clock.schedule_interval(self.toggle_buzzer, 1.0)

    def toggle_buzzer(self, dt):
        try:
            self.buzzer_state = not self.buzzer_state
            GPIO.output(17, 1 if self.buzzer_state else 0)
        except Exception: pass

    def save_chat_message(self, role, text):
        message_data = {"role": role, "text": text, "timestamp": str(datetime.now())}
        self.chat_history.append(message_data)
        try:
            with open(CHAT_FILE, "w") as f:
                json.dump(self.chat_history, f, indent=4)
        except: pass

    def clear_chat_data(self):
        self.chat_history = []
        try:
            with open(CHAT_FILE, "w") as f:
                json.dump([], f)
        except: pass

    def send_rotate_command(self):
        if self.root and self.root.has_screen('vitals'):
            vitals_screen = self.root.get_screen('vitals')
            if hasattr(vitals_screen, 'ser') and vitals_screen.ser and vitals_screen.ser.is_open:
                try:
                    vitals_screen.ser.write(b"ROTATE\n")
                    return
                except Exception: pass

        if self.arduino_serial and self.arduino_serial.is_open:
            try: self.arduino_serial.write(b"ROTATE\n")
            except Exception: pass

    def on_stop(self):
        if self.arduino_serial and self.arduino_serial.is_open:
            self.arduino_serial.close()

    
if __name__ == "__main__":
    PagtultolApp().run()
