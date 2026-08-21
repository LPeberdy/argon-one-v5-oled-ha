"""Permissions and config safety tests for the shipped add-on."""

import os
import re
import unittest

ADDON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(filename):
    with open(os.path.join(ADDON_DIR, filename), 'r') as f:
        return f.read()


def top_level_scalar(config_text, key):
    head = config_text.split('\noptions:')[0]
    match = re.search(rf'^{re.escape(key)}:\s*(.+)$', head, re.MULTILINE)
    return match.group(1).strip() if match else None


def devices_list(config_text):
    match = re.search(r'^devices:\s*\n((?:\s+-\s+.+\n?)+)', config_text, re.MULTILINE)
    if not match:
        return []
    return [line.strip('- ').strip() for line in match.group(1).splitlines() if line.strip()]


class TestConfigYamlPermissions(unittest.TestCase):
    def setUp(self):
        self.config_text = read('config.yaml')

    def test_only_i2c_bus_1_device_exposed(self):
        self.assertEqual(devices_list(self.config_text), ['/dev/i2c-1'])

    def test_no_gpio_access(self):
        self.assertEqual(top_level_scalar(self.config_text, 'gpio'), 'false')

    def test_apparmor_enabled(self):
        self.assertEqual(top_level_scalar(self.config_text, 'apparmor'), 'true')

    def test_no_config_volume_mapped(self):
        self.assertNotIn('map:', self.config_text)

    def test_hassio_role_remains_narrow_backup_role(self):
        role = top_level_scalar(self.config_text, 'hassio_role')
        self.assertEqual(role, 'backup')
        self.assertNotIn(role, ('manager', 'admin'))

    def test_hassio_api_enabled_for_status_only(self):
        self.assertEqual(top_level_scalar(self.config_text, 'hassio_api'), 'true')

    def test_homeassistant_core_api_enabled_for_read_only_context(self):
        self.assertEqual(top_level_scalar(self.config_text, 'homeassistant_api'), 'true')

    def test_boot_auto_for_persistence(self):
        self.assertEqual(top_level_scalar(self.config_text, 'boot'), 'auto')

    def test_invalid_boolean_watchdog_not_declared(self):
        self.assertIsNone(top_level_scalar(self.config_text, 'watchdog'))


class TestAppArmorProfile(unittest.TestCase):
    def setUp(self):
        self.profile_text = read('apparmor.txt')

    def test_only_i2c_bus_1_allowed(self):
        i2c_lines = [line for line in self.profile_text.splitlines() if '/dev/i2c' in line]
        self.assertEqual(len(i2c_lines), 1)
        self.assertIn('/dev/i2c-1', i2c_lines[0])

    def test_no_gpio_device_access(self):
        self.assertNotIn('gpiochip', self.profile_text.lower())

    def test_config_share_ssl_backup_explicitly_denied(self):
        for path in ('/config/', '/ssl/', '/share/', '/backup/'):
            self.assertIn(path, self.profile_text)
            self.assertIn(f'deny {path}', self.profile_text)


class TestSourceHasNoHostControlOrGpio(unittest.TestCase):
    def _source(self, filename):
        return read(filename)

    def test_no_host_reboot_or_shutdown_endpoints(self):
        for filename in ('supervisor_api.py', 'home_context.py', 'argon_oled.py'):
            source = self._source(filename)
            self.assertNotIn('host/reboot', source)
            self.assertNotIn('host/shutdown', source)

    def test_api_clients_are_get_only(self):
        for filename in ('supervisor_api.py', 'home_context.py'):
            source = self._source(filename)
            for method in ('post', 'put', 'patch', 'delete'):
                self.assertNotIn(f'requests.{method}', source,
                                 f'{filename} must not issue {method.upper()} requests')

    def test_home_context_only_reads_states_proxy(self):
        source = self._source('home_context.py')
        self.assertIn('http://supervisor/core/api/states', source)
        self.assertNotIn('/api/services/', source)

    def test_no_gpio_imports(self):
        for filename in (
            'argon_oled.py', 'system_info.py', 'supervisor_api.py', 'home_context.py',
            'screens.py', 'visual_modes.py', 'interruptions.py',
        ):
            source = self._source(filename)
            self.assertNotIn('import gpiod', source)
            self.assertNotIn('RPi.GPIO', source)

    def test_no_manager_role_permission_checks(self):
        source = self._source('argon_oled.py')
        for phrase in ('hassio_role', 'manager role', 'check_power_permissions', 'power_management'):
            self.assertNotIn(phrase, source.lower())


class TestDockerfileNoGpioPackages(unittest.TestCase):
    def test_no_gpio_packages_installed(self):
        dockerfile = read('Dockerfile')
        self.assertNotIn('libgpiod', dockerfile)
        self.assertNotIn('py3-libgpiod', dockerfile)


if __name__ == '__main__':
    unittest.main()
