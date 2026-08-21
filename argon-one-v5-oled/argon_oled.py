#!/usr/bin/env python3
"""Argon ONE OLED Display Service for Home Assistant.

The add-on reads local system metrics, read-only Supervisor status endpoints,
and (for ambient/context modes) read-only Home Assistant entity states. It
never touches GPIO, never issues a POST request, and never reboots or shuts
down the host.
"""

import os
import sys
import time

from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from PIL import Image, ImageFont

from system_info import SystemInfo
from supervisor_api import SupervisorAPI
from home_context import HomeContextClient
from screens import ScreenRenderer
from visual_modes import VisualModeRenderer
from faults import evaluate_faults
from interruptions import InterruptionController, evaluate_contextual_facts

I2C_BUS = 1
I2C_ADDRESS = 0x3C
SCREEN_WIDTH = 128
SCREEN_HEIGHT = 64
ALERT_SWITCH_DURATION = 5


class ArgonOLED:
    """Argon ONE OLED display manager with selectable normal modes."""

    def __init__(self, screen_list, switch_duration=30, temp_unit='C', debug_logging=False,
                 show_credits=True, version='1.0.0', thresholds=None,
                 mode='current', ambient_scene='auto', contextual_interruptions=True,
                 urgent_interruptions=True, contextual_duration=8,
                 contextual_interval=300, ha_refresh_seconds=60):
        try:
            self.serial = i2c(port=I2C_BUS, address=I2C_ADDRESS)
            self.device = ssd1306(self.serial, width=SCREEN_WIDTH, height=SCREEN_HEIGHT)
            self.device.clear()
        except Exception as exc:
            print(f'Error initializing OLED: {exc}')
            sys.exit(1)

        self.screen_list = screen_list or ['clock']
        self.switch_duration = switch_duration
        self.temp_unit = temp_unit
        self.debug_logging = debug_logging
        self.show_credits = show_credits
        self.version = version
        self.thresholds = thresholds or {}
        self.mode = mode if mode in ('current', 'ambient', 'character') else 'current'
        self.ambient_scene = ambient_scene
        self.contextual_interruptions = contextual_interruptions
        self.urgent_interruptions = urgent_interruptions
        self.credits_shown = False
        self.current_screen = 0
        self.last_screen_switch = time.time()

        self.system_info = SystemInfo(temp_unit=temp_unit)
        self.supervisor_api = SupervisorAPI(debug_callback=self.debug_log)
        self.home_context = HomeContextClient(
            debug_callback=self.debug_log,
            state_ttl=ha_refresh_seconds,
        )
        self.interruptions = InterruptionController(
            contextual_enabled=contextual_interruptions,
            urgent_enabled=urgent_interruptions,
            contextual_duration=contextual_duration,
            contextual_interval=contextual_interval,
            urgent_switch_duration=ALERT_SWITCH_DURATION,
        )

        try:
            font_small = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 10)
            font_medium = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 14)
            font_large = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 20)
        except Exception:
            font_small = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_large = ImageFont.load_default()

        fonts = {'small': font_small, 'medium': font_medium, 'large': font_large}

        logo_image = None
        logo_paths = ['/data/logo.png', '/data/logo.jpg', '/data/logo.bmp', '/logo.png']
        for logo_path in logo_paths:
            try:
                if os.path.exists(logo_path):
                    img = Image.open(logo_path)
                    img = img.convert('1')
                    img.thumbnail((SCREEN_WIDTH, SCREEN_HEIGHT), Image.Resampling.LANCZOS)
                    logo_image = img
                    self.debug_log(f'Loaded logo image from: {logo_path}')
                    break
            except Exception as exc:
                self.debug_log(f'Could not load logo from {logo_path}: {exc}')

        if not logo_image:
            self.debug_log('No logo image could be loaded')

        self.renderer = ScreenRenderer(
            device=self.device,
            fonts=fonts,
            temp_unit=temp_unit,
            logo_image=logo_image,
        )
        self.visuals = VisualModeRenderer(
            device=self.device,
            fonts=fonts,
            temp_unit=temp_unit,
        )

    def debug_log(self, message):
        if self.debug_logging:
            print(message)
            sys.stdout.flush()

    def display_screen(self, screen_name):
        if screen_name == 'clock':
            self.renderer.draw_clock()
        elif screen_name == 'cpu':
            self.renderer.draw_cpu(self.system_info)
        elif screen_name == 'ram':
            self.renderer.draw_ram(self.system_info)
        elif screen_name == 'storage':
            self.renderer.draw_storage(self.system_info)
        elif screen_name == 'temp':
            self.renderer.draw_temp(self.system_info)
        elif screen_name == 'fan':
            self.renderer.draw_fan(self.system_info)
        elif screen_name == 'uptime':
            self.renderer.draw_uptime(self.system_info)
        elif screen_name == 'ip':
            self.renderer.draw_ip(self.supervisor_api)
        elif screen_name == 'qr':
            self.renderer.draw_qr(self.supervisor_api)
        elif screen_name in ('hastatus', 'status'):
            self.renderer.draw_ha_status(self.supervisor_api)
        elif screen_name == 'logo':
            self.renderer.draw_logo()
        else:
            self.debug_log(f'Unknown screen in screen_list: {screen_name}')

    def collect_fault_metrics(self):
        cpu_temp_c = self.system_info.get_cpu_temp()
        if self.temp_unit == 'F':
            cpu_temp_c = (cpu_temp_c - 32) * 5 / 9

        fan = self.system_info.get_fan_speed()
        _, _, disk_percent, storage_available = self.system_info.get_disk_usage()
        storage = {'available': storage_available, 'percent': disk_percent}
        ha_status = self.supervisor_api.get_ha_system_status()

        return {
            'cpu_temp_c': cpu_temp_c,
            'fan': fan,
            'storage': storage,
            'ha_status': ha_status,
        }

    def display_normal_mode(self, context, metrics, frame, current_time):
        if self.mode == 'ambient':
            self.visuals.draw_ambient(context, frame=frame, scene=self.ambient_scene)
            return

        if self.mode == 'character':
            self.visuals.draw_character(
                context,
                frame=frame,
                cpu_temp_c=metrics.get('cpu_temp_c'),
            )
            return

        if current_time - self.last_screen_switch >= self.switch_duration:
            self.current_screen = (self.current_screen + 1) % len(self.screen_list)
            self.last_screen_switch = current_time
        self.display_screen(self.screen_list[self.current_screen])

    def cleanup(self):
        try:
            self.device.clear()
            self.device.cleanup()
        except Exception:
            pass

    def run(self):
        self.debug_log('Starting Argon OLED Display')
        self.debug_log(f'Display mode: {self.mode}')
        self.debug_log(f'Ambient scene: {self.ambient_scene}')
        self.debug_log(f"Screen rotation: {' -> '.join(self.screen_list)}")
        self.debug_log(f'Switch duration: {self.switch_duration}s')
        self.debug_log(f'Temperature unit: {self.temp_unit}')
        self.debug_log(f'Contextual interruptions: {self.contextual_interruptions}')
        self.debug_log(f'Urgent interruptions: {self.urgent_interruptions}')

        if self.show_credits and not self.credits_shown:
            self.debug_log('Displaying credits splash screen')
            self.renderer.draw_credits(version=self.version)
            self.credits_shown = True
            time.sleep(5)

        loop_count = 0
        try:
            while True:
                current_time = time.time()
                metrics = self.collect_fault_metrics()
                faults = evaluate_faults(metrics, thresholds=self.thresholds)
                context = self.home_context.get_context()
                contextual_facts = evaluate_contextual_facts(context, metrics=metrics)
                decision = self.interruptions.choose(faults, contextual_facts)

                if decision['kind'] == 'urgent':
                    self.last_screen_switch = current_time
                    fault = decision['item']
                    self.debug_log(f"Urgent interruption: {fault['id']} - {fault['title']}: {fault['detail']}")
                    if self.mode == 'character':
                        self.visuals.draw_character(
                            context,
                            frame=loop_count,
                            fault=fault,
                            cpu_temp_c=metrics.get('cpu_temp_c'),
                        )
                    else:
                        self.renderer.draw_alert(fault)

                elif decision['kind'] == 'contextual':
                    self.last_screen_switch = current_time
                    fact = decision['item']
                    self.debug_log(f"Contextual interruption: {fact['id']} - {fact['detail']}")
                    if self.mode == 'character':
                        self.visuals.draw_character(
                            context,
                            frame=loop_count,
                            fact=fact,
                            cpu_temp_c=metrics.get('cpu_temp_c'),
                        )
                    else:
                        self.visuals.draw_contextual(fact)

                else:
                    self.display_normal_mode(context, metrics, loop_count, current_time)

                loop_count += 1
                time.sleep(1)

        except KeyboardInterrupt:
            print('\nShutting down...')
        except Exception as exc:
            print(f'Error in main loop: {exc}')
            raise
        finally:
            self.cleanup()


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in ('true', '1', 'yes', 'on')


def main():
    screen_list_str = os.environ.get('SCREEN_LIST', 'clock hastatus cpu fan ram storage ip uptime')
    screen_list = screen_list_str.split()

    switch_duration = _env_int('SWITCH_DURATION', 30)
    temp_unit = os.environ.get('TEMP_UNIT', 'C')
    debug_logging = _env_bool('DEBUG_LOGGING', False)
    show_credits = _env_bool('SHOW_CREDITS', True)
    version = os.environ.get('ADDON_VERSION', '1.0.0')
    mode = os.environ.get('DISPLAY_MODE', 'current').lower()
    ambient_scene = os.environ.get('AMBIENT_SCENE', 'auto').lower()
    contextual_interruptions = _env_bool('CONTEXTUAL_INTERRUPTS', True)
    urgent_interruptions = _env_bool('URGENT_INTERRUPTS', True)
    contextual_duration = _env_int('CONTEXTUAL_DURATION', 8)
    contextual_interval = _env_int('CONTEXTUAL_INTERVAL', 300)
    ha_refresh_seconds = _env_int('HA_REFRESH_SECONDS', 60)

    thresholds = {
        'cpu_temp_alert_c': _env_int('CPU_TEMP_ALERT_C', 80),
        'fan_min_temp_c': _env_int('FAN_MIN_TEMP_C', 55),
        'backup_max_age_hours': _env_int('BACKUP_MAX_AGE_HOURS', 48),
        'storage_min_free_percent': _env_int('STORAGE_MIN_FREE_PERCENT', 10),
    }

    oled = ArgonOLED(
        screen_list,
        switch_duration,
        temp_unit,
        debug_logging,
        show_credits,
        version,
        thresholds=thresholds,
        mode=mode,
        ambient_scene=ambient_scene,
        contextual_interruptions=contextual_interruptions,
        urgent_interruptions=urgent_interruptions,
        contextual_duration=contextual_duration,
        contextual_interval=contextual_interval,
        ha_refresh_seconds=ha_refresh_seconds,
    )
    oled.run()


if __name__ == '__main__':
    main()
