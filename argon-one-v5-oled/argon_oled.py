#!/usr/bin/env python3
"""
Argon ONE OLED Display Service for Home Assistant
Displays system status on the Argon ONE Industria OLED screen.

This addon only ever reads local system metrics and calls read-only
Supervisor status endpoints (see supervisor_api.py). It never touches
GPIO, never issues a POST to the Supervisor API, and never reboots or
shuts down the host - see README.md "Permissions" for the full contract.
"""

import os
import sys
import time

from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306
from PIL import Image, ImageFont

from system_info import SystemInfo
from supervisor_api import SupervisorAPI
from screens import ScreenRenderer
from faults import evaluate_faults

# Configuration
I2C_BUS = 1
I2C_ADDRESS = 0x3C
SCREEN_WIDTH = 128
SCREEN_HEIGHT = 64
ALERT_SWITCH_DURATION = 5  # seconds between alert screens when faults are active


class ArgonOLED:
    """Argon ONE OLED Display Manager"""

    def __init__(self, screen_list, switch_duration=30, temp_unit='C', debug_logging=False,
                 show_credits=True, version="1.0.0", thresholds=None):
        """Initialize the OLED display"""
        try:
            self.serial = i2c(port=I2C_BUS, address=I2C_ADDRESS)
            self.device = ssd1306(self.serial, width=SCREEN_WIDTH, height=SCREEN_HEIGHT)
            self.device.clear()
        except Exception as e:
            print(f"Error initializing OLED: {e}")
            sys.exit(1)

        self.screen_list = screen_list
        self.switch_duration = switch_duration
        self.temp_unit = temp_unit
        self.debug_logging = debug_logging
        self.show_credits = show_credits
        self.version = version
        self.thresholds = thresholds or {}
        self.credits_shown = False
        self.current_screen = 0
        self.current_fault_index = 0
        self.last_switch = time.time()

        # Initialize our modules
        self.system_info = SystemInfo(temp_unit=temp_unit)
        self.supervisor_api = SupervisorAPI(debug_callback=self.debug_log)

        # Load fonts
        try:
            font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
            font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
            font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        except Exception:
            font_small = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_large = ImageFont.load_default()

        self.font_small = font_small
        self.font_medium = font_medium
        self.font_large = font_large

        fonts = {
            'small': font_small,
            'medium': font_medium,
            'large': font_large,
        }

        # Load logo image. Only bundled asset and the addon's own /data
        # directory are consulted - there is no /config volume mapped.
        logo_image = None
        logo_paths = [
            '/data/logo.png',
            '/data/logo.jpg',
            '/data/logo.bmp',
            '/logo.png',  # Default logo bundled with addon
        ]

        for logo_path in logo_paths:
            try:
                if os.path.exists(logo_path):
                    img = Image.open(logo_path)
                    img = img.convert('1')
                    img.thumbnail((SCREEN_WIDTH, SCREEN_HEIGHT), Image.Resampling.LANCZOS)
                    logo_image = img
                    self.debug_log(f"Loaded logo image from: {logo_path}")
                    break
            except Exception as e:
                self.debug_log(f"Could not load logo from {logo_path}: {e}")

        if not logo_image:
            self.debug_log("No logo image could be loaded")

        # Initialize screen renderer
        self.renderer = ScreenRenderer(
            device=self.device,
            fonts=fonts,
            temp_unit=temp_unit,
            logo_image=logo_image,
        )

    def debug_log(self, message):
        """Print debug message if debug logging is enabled"""
        if self.debug_logging:
            print(message)
            sys.stdout.flush()

    def display_screen(self, screen_name):
        """Display a specific routine screen"""
        if screen_name == "clock":
            self.renderer.draw_clock()
        elif screen_name == "cpu":
            self.renderer.draw_cpu(self.system_info)
        elif screen_name == "ram":
            self.renderer.draw_ram(self.system_info)
        elif screen_name == "storage":
            self.renderer.draw_storage(self.system_info)
        elif screen_name == "temp":
            self.renderer.draw_temp(self.system_info)
        elif screen_name == "fan":
            self.renderer.draw_fan(self.system_info)
        elif screen_name == "uptime":
            self.renderer.draw_uptime(self.system_info)
        elif screen_name == "ip":
            self.renderer.draw_ip(self.supervisor_api)
        elif screen_name == "qr":
            self.renderer.draw_qr(self.supervisor_api)
        elif screen_name == "hastatus" or screen_name == "status":
            self.renderer.draw_ha_status(self.supervisor_api)
        elif screen_name == "logo":
            self.renderer.draw_logo()
        else:
            self.debug_log(f"Unknown screen in screen_list: {screen_name}")

    def collect_fault_metrics(self):
        """Gather the current metrics needed to evaluate faults"""
        cpu_temp_c = self.system_info.get_cpu_temp()
        if self.temp_unit == 'F':
            # get_cpu_temp() returns in the configured display unit;
            # faults are always evaluated in Celsius against config thresholds.
            cpu_temp_c = (cpu_temp_c - 32) * 5 / 9

        fan = self.system_info.get_fan_speed()

        disk_used, disk_total, disk_percent, storage_available = self.system_info.get_disk_usage()
        storage = {'available': storage_available, 'percent': disk_percent}

        ha_status = self.supervisor_api.get_ha_system_status()

        return {
            'cpu_temp_c': cpu_temp_c,
            'fan': fan,
            'storage': storage,
            'ha_status': ha_status,
        }

    def cleanup(self):
        """Clean up and clear display"""
        try:
            self.device.clear()
            self.device.cleanup()
        except Exception:
            pass

    def run(self):
        """Main loop"""
        self.debug_log("Starting Argon OLED Display")
        self.debug_log(f"Screen rotation: {' -> '.join(self.screen_list)}")
        self.debug_log(f"Switch duration: {self.switch_duration}s")
        self.debug_log(f"Temperature unit: {self.temp_unit}")

        # Show credits splash screen if enabled
        if self.show_credits and not self.credits_shown:
            self.debug_log("Displaying credits splash screen")
            self.renderer.draw_credits(version=self.version)
            self.credits_shown = True
            time.sleep(5)

        loop_count = 0
        try:
            while True:
                if loop_count < 10:
                    self.debug_log(f"[MAIN LOOP] Iteration {loop_count}")
                loop_count += 1

                current_time = time.time()
                metrics = self.collect_fault_metrics()
                active_faults = evaluate_faults(metrics, thresholds=self.thresholds)

                if active_faults:
                    # Faults supersede routine rotation entirely - cycle
                    # through active faults until all are resolved.
                    switch_interval = ALERT_SWITCH_DURATION
                    if current_time - self.last_switch >= switch_interval:
                        self.current_fault_index = (self.current_fault_index + 1) % len(active_faults)
                        self.last_switch = current_time
                    else:
                        self.current_fault_index = min(self.current_fault_index, len(active_faults) - 1)

                    fault = active_faults[self.current_fault_index]
                    self.debug_log(f"Active fault: {fault['id']} - {fault['title']}: {fault['detail']}")
                    self.renderer.draw_alert(fault)
                else:
                    self.current_fault_index = 0
                    if current_time - self.last_switch >= self.switch_duration:
                        self.current_screen = (self.current_screen + 1) % len(self.screen_list)
                        self.last_switch = current_time

                    screen_name = self.screen_list[self.current_screen]
                    self.display_screen(screen_name)

                time.sleep(1)

        except KeyboardInterrupt:
            print("\nShutting down...")
        except Exception as e:
            print(f"Error in main loop: {e}")
            raise
        finally:
            self.cleanup()


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def main():
    """Main entry point"""
    screen_list_str = os.environ.get('SCREEN_LIST', 'clock hastatus cpu fan ram storage ip uptime')
    screen_list = screen_list_str.split()

    switch_duration = _env_int('SWITCH_DURATION', 30)
    temp_unit = os.environ.get('TEMP_UNIT', 'C')
    debug_logging = os.environ.get('DEBUG_LOGGING', 'false').lower() in ('true', '1', 'yes')
    show_credits = os.environ.get('SHOW_CREDITS', 'true').lower() in ('true', '1', 'yes')
    version = os.environ.get('ADDON_VERSION', '1.0.0')

    thresholds = {
        'cpu_temp_alert_c': _env_int('CPU_TEMP_ALERT_C', 80),
        'fan_min_temp_c': _env_int('FAN_MIN_TEMP_C', 55),
        'backup_max_age_hours': _env_int('BACKUP_MAX_AGE_HOURS', 48),
        'storage_min_free_percent': _env_int('STORAGE_MIN_FREE_PERCENT', 10),
    }

    oled = ArgonOLED(screen_list, switch_duration, temp_unit, debug_logging, show_credits,
                      version, thresholds=thresholds)
    oled.run()


if __name__ == '__main__':
    main()
