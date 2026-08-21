"""
Unit tests for system_info module
"""

import os
import unittest
from unittest.mock import patch, mock_open
from system_info import SystemInfo


class TestSystemInfo(unittest.TestCase):
    """Test SystemInfo class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.system_info_c = SystemInfo(temp_unit='C')
        self.system_info_f = SystemInfo(temp_unit='F')
    
    def test_init(self):
        """Test SystemInfo initialization"""
        self.assertEqual(self.system_info_c.temp_unit, 'C')
        self.assertEqual(self.system_info_f.temp_unit, 'F')
        self.assertIsNone(self.system_info_c.prev_idle)
        self.assertIsNone(self.system_info_c.prev_total)
    
    @patch('builtins.open', mock_open(read_data='45000'))
    def test_get_cpu_temp_celsius(self):
        """Test CPU temperature in Celsius"""
        temp = self.system_info_c.get_cpu_temp()
        self.assertEqual(temp, 45.0)
    
    @patch('builtins.open', mock_open(read_data='45000'))
    def test_get_cpu_temp_fahrenheit(self):
        """Test CPU temperature in Fahrenheit"""
        temp = self.system_info_f.get_cpu_temp()
        self.assertEqual(temp, 113.0)  # 45°C = 113°F
    
    @patch('builtins.open', side_effect=Exception('File not found'))
    def test_get_cpu_temp_error(self, mock_file):
        """Test CPU temperature error handling"""
        temp = self.system_info_c.get_cpu_temp()
        self.assertEqual(temp, 0)
    
    @patch('builtins.open', mock_open(read_data='cpu  100 0 50 850 0 0 0 0 0 0\n'))
    def test_get_cpu_usage_first_call(self):
        """Test CPU usage on first call (should return 0)"""
        usage = self.system_info_c.get_cpu_usage()
        self.assertEqual(usage, 0)
    
    @patch('builtins.open')
    def test_get_cpu_usage_second_call(self, mock_file):
        """Test CPU usage calculation on second call"""
        # First call
        mock_file.return_value.__enter__.return_value.readline.return_value = 'cpu  100 0 50 850 0 0 0 0 0 0\n'
        self.system_info_c.get_cpu_usage()
        
        # Second call with increased values
        mock_file.return_value.__enter__.return_value.readline.return_value = 'cpu  120 0 60 860 0 0 0 0 0 0\n'
        usage = self.system_info_c.get_cpu_usage()
        
        # CPU usage should be calculated
        self.assertGreater(usage, 0)
        self.assertLessEqual(usage, 100)
    
    @patch('builtins.open', side_effect=Exception('Error'))
    def test_get_cpu_usage_error(self, mock_file):
        """Test CPU usage error handling"""
        usage = self.system_info_c.get_cpu_usage()
        self.assertEqual(usage, 0)
    
    @patch('builtins.open')
    def test_get_memory_usage(self, mock_file):
        """Test memory usage calculation"""
        mock_data = 'MemTotal:       8000000 kB\nMemAvailable:   4000000 kB\n'
        mock_file.return_value.__enter__.return_value.readlines.return_value = mock_data.split('\n')
        
        mem_used, mem_total, mem_percent = self.system_info_c.get_memory_usage()
        
        self.assertAlmostEqual(mem_used, 3906.25, places=1)  # ~4GB used
        self.assertAlmostEqual(mem_total, 7812.5, places=1)  # ~8GB total
        self.assertEqual(mem_percent, 50.0)  # 50% used
    
    @patch('builtins.open', side_effect=Exception('Error'))
    def test_get_memory_usage_error(self, mock_file):
        """Test memory usage error handling"""
        mem_used, mem_total, mem_percent = self.system_info_c.get_memory_usage()
        self.assertEqual(mem_used, 0)
        self.assertEqual(mem_total, 0)
        self.assertEqual(mem_percent, 0)
    
    def test_get_disk_usage(self):
        """Test disk usage calculation reads the real host data partition (/data)"""
        # Mock statvfs result
        class MockStatVFS:
            f_blocks = 10000000  # Total blocks
            f_frsize = 4096      # Block size
            f_bavail = 5000000   # Available blocks

        if hasattr(os, 'statvfs'):
            with patch('os.statvfs', return_value=MockStatVFS()) as mock_statvfs:
                disk_used, disk_total, disk_percent, available = self.system_info_c.get_disk_usage()

                mock_statvfs.assert_called_once_with('/data')
                self.assertTrue(available)
                self.assertAlmostEqual(disk_used, 19.073, places=2)  # ~19GB used
                self.assertAlmostEqual(disk_total, 38.147, places=2)  # ~38GB total
                self.assertEqual(disk_percent, 50.0)  # 50% used
        else:
            disk_used, disk_total, disk_percent, available = self.system_info_c.get_disk_usage()
            self.assertFalse(available)

    def test_get_disk_usage_error_reports_unavailable_not_misleading_zero(self):
        """When /data can't be statvfs'd, storage must be reported unavailable
        rather than silently falling back to the (misleading) container overlay '/'."""
        with patch('os.statvfs', side_effect=Exception('Error')) as mock_statvfs:
            disk_used, disk_total, disk_percent, available = self.system_info_c.get_disk_usage()

            mock_statvfs.assert_called_once_with('/data')
            self.assertFalse(available)
            self.assertEqual(disk_used, 0)
            self.assertEqual(disk_total, 0)
            self.assertEqual(disk_percent, 0)

    def test_get_disk_usage_never_falls_back_to_root_overlay(self):
        """statvfs must never be called against '/' - that would report the
        container overlay, not real host storage."""
        with patch('os.statvfs', side_effect=Exception('Error')) as mock_statvfs:
            self.system_info_c.get_disk_usage()
            for call in mock_statvfs.call_args_list:
                self.assertNotEqual(call.args[0], '/')

    def test_get_load_average(self):
        """Test load average retrieval"""
        with patch('os.getloadavg', return_value=(0.5, 0.75, 1.0)):
            load1, load5, load15 = self.system_info_c.get_load_average()
            self.assertEqual((load1, load5, load15), (0.5, 0.75, 1.0))

    def test_get_load_average_error(self):
        """Test load average error handling"""
        with patch('os.getloadavg', side_effect=OSError('unsupported')):
            load1, load5, load15 = self.system_info_c.get_load_average()
            self.assertEqual((load1, load5, load15), (0.0, 0.0, 0.0))

    @patch('builtins.open', mock_open(read_data='12345.67 54321.00'))
    def test_get_uptime_seconds(self):
        """Test uptime retrieval from /proc/uptime"""
        uptime = self.system_info_c.get_uptime_seconds()
        self.assertEqual(uptime, 12345.67)

    @patch('builtins.open', side_effect=Exception('File not found'))
    def test_get_uptime_seconds_error(self, mock_file):
        """Test uptime error handling"""
        uptime = self.system_info_c.get_uptime_seconds()
        self.assertEqual(uptime, 0)

    @patch('system_info.glob.glob', return_value=['/sys/class/hwmon/hwmon3/name'])
    @patch('system_info.os.path.exists', return_value=True)
    @patch('builtins.open')
    def test_get_fan_speed_remains_read_only_local_hwmon(self, mock_file, mock_exists, mock_glob):
        """Supervisor caching must not alter native Pi 5 fan handling:
        fan RPM/PWM are still read directly from hwmon and never written."""
        file_data = {
            '/sys/class/hwmon/hwmon3/name': 'pwmfan\n',
            '/sys/class/hwmon/hwmon3/fan1_input': '3200\n',
            '/sys/class/hwmon/hwmon3/pwm1': '128\n',
        }

        def open_file(path, mode='r', *args, **kwargs):
            self.assertEqual(mode, 'r', f"fan hwmon path opened non-read-only: {path}")
            return mock_open(read_data=file_data[path])()

        mock_file.side_effect = open_file

        fan = self.system_info_c.get_fan_speed()

        self.assertEqual(fan['rpm'], 3200)
        self.assertEqual(fan['pwm_percent'], int((128 / 255) * 100))
        self.assertEqual(fan['status'], '3200 RPM')
        mock_glob.assert_called_once_with('/sys/class/hwmon/hwmon*/name')
        self.assertGreaterEqual(mock_file.call_count, 3)


if __name__ == '__main__':
    unittest.main()
