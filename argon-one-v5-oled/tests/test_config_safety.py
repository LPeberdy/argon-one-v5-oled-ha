"""
Permissions and config safety tests.

These tests assert the least-privilege invariants described in
README.md's "Permissions" / "Status Contract" sections directly against
the shipped config.yaml, apparmor.txt, and source files, so any future
change that widens the addon's privilege footprint fails CI rather than
being silently deployed.
"""

import os
import re
import unittest

ADDON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(filename):
    with open(os.path.join(ADDON_DIR, filename), 'r') as f:
        return f.read()


def top_level_scalar(config_text, key):
    """Extract a simple top-level `key: value` from config.yaml (not nested
    under options/schema)."""
    # Stop scanning once we hit the options/schema sections to avoid
    # matching option names that happen to share a key name.
    head = config_text.split('\noptions:')[0]
    match = re.search(rf'^{re.escape(key)}:\s*(.+)$', head, re.MULTILINE)
    return match.group(1).strip() if match else None


def devices_list(config_text):
    match = re.search(r'^devices:\s*\n((?:\s+-\s+.+\n?)+)', config_text, re.MULTILINE)
    if not match:
        return []
    return [line.strip('- ').strip() for line in match.group(1).splitlines() if line.strip()]


class TestConfigYamlPermissions(unittest.TestCase):
    """Assert least-privilege addon options in config.yaml"""

    def setUp(self):
        self.config_text = read('config.yaml')

    def test_only_i2c_bus_1_device_exposed(self):
        devices = devices_list(self.config_text)
        self.assertEqual(devices, ['/dev/i2c-1'],
                          "Only /dev/i2c-1 should be exposed to the container")

    def test_no_gpio_access(self):
        gpio_value = top_level_scalar(self.config_text, 'gpio')
        self.assertEqual(gpio_value, 'false', "gpio must be disabled (GPIO4 button is omitted this release)")

    def test_apparmor_enabled(self):
        apparmor_value = top_level_scalar(self.config_text, 'apparmor')
        self.assertEqual(apparmor_value, 'true', "apparmor must be enabled (enforced)")

    def test_no_config_volume_mapped(self):
        self.assertNotIn('map:', self.config_text,
                          "No `map` (e.g. config:rw) volume should be requested")

    def test_hassio_role_is_not_manager_or_admin(self):
        role = top_level_scalar(self.config_text, 'hassio_role')
        self.assertIsNotNone(role)
        self.assertNotIn(role, ('manager', 'admin'),
                          "hassio_role must not grant host-control-capable roles")

    def test_hassio_role_is_lowest_viable_default(self):
        role = top_level_scalar(self.config_text, 'hassio_role')
        self.assertEqual(role, 'default',
                          "Expected lowest-viable 'default' role; see README for live-verification note")

    def test_hassio_api_enabled_for_status_only(self):
        self.assertEqual(top_level_scalar(self.config_text, 'hassio_api'), 'true')

    def test_homeassistant_core_api_not_used(self):
        self.assertEqual(top_level_scalar(self.config_text, 'homeassistant_api'), 'false',
                          "This addon uses only hassio_api for read-only status, not the Core API")

    def test_boot_auto_for_persistence(self):
        self.assertEqual(top_level_scalar(self.config_text, 'boot'), 'auto')

    def test_invalid_boolean_watchdog_not_declared(self):
        # Home Assistant's manifest watchdog field is a health-check URL,
        # not a boolean restart flag. This display exposes no health port.
        self.assertIsNone(top_level_scalar(self.config_text, 'watchdog'))


class TestAppArmorProfile(unittest.TestCase):
    """Assert the AppArmor profile matches the least-privilege device list"""

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
    """Assert the Python source contains no reboot/shutdown/POST/GPIO code paths"""

    def _source(self, filename):
        return read(filename)

    def test_no_host_reboot_or_shutdown_endpoints(self):
        for filename in ('supervisor_api.py', 'argon_oled.py'):
            source = self._source(filename)
            self.assertNotIn('host/reboot', source, f"{filename} must not call host/reboot")
            self.assertNotIn('host/shutdown', source, f"{filename} must not call host/shutdown")

    def test_no_post_requests_to_supervisor(self):
        source = self._source('supervisor_api.py')
        self.assertNotIn('requests.post', source, "supervisor_api.py must only issue GET requests")
        self.assertNotIn("method='POST'", source)
        self.assertNotIn('method="POST"', source)

    def test_no_gpio_imports(self):
        for filename in ('argon_oled.py', 'system_info.py', 'supervisor_api.py', 'screens.py'):
            source = self._source(filename)
            self.assertNotIn('import gpiod', source, f"{filename} must not import gpiod")
            self.assertNotIn('RPi.GPIO', source, f"{filename} must not import RPi.GPIO")

    def test_no_manager_role_permission_checks(self):
        source = self._source('argon_oled.py')
        for phrase in ('hassio_role', 'manager role', 'check_power_permissions', 'power_management'):
            self.assertNotIn(phrase, source.lower(),
                              f"argon_oled.py should not reference '{phrase}' (host permission checks)")


class TestDockerfileNoGpioPackages(unittest.TestCase):
    def test_no_gpio_packages_installed(self):
        dockerfile = read('Dockerfile')
        self.assertNotIn('libgpiod', dockerfile)
        self.assertNotIn('py3-libgpiod', dockerfile)


if __name__ == '__main__':
    unittest.main()
