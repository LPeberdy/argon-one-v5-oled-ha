"""
Unit tests for the fault evaluation engine (faults.py)

Covers: exception prioritization (alerts must supersede routine display)
and correctness of each fault's trigger condition and threshold handling.
"""

import unittest
from datetime import datetime, timedelta, timezone

from faults import evaluate_faults, backup_age_hours, DEFAULT_THRESHOLDS


def healthy_metrics(now=None):
    now = now or datetime.now(timezone.utc)
    return {
        'cpu_temp_c': 45.0,
        'fan': {'rpm': 2000, 'pwm_percent': 40, 'status': '2000 RPM'},
        'storage': {'available': True, 'percent': 50.0},
        'ha_status': {
            'available': True,
            'updates': 0,
            'last_backup': (now - timedelta(hours=1)).isoformat(),
            'backup_state': 'OK',
        },
    }


class TestBackupAgeHours(unittest.TestCase):
    def test_none_when_missing(self):
        self.assertIsNone(backup_age_hours(None))

    def test_none_when_unparseable(self):
        self.assertIsNone(backup_age_hours('not-a-date'))

    def test_computes_hours_since_backup(self):
        now = datetime.now(timezone.utc)
        ts = (now - timedelta(hours=5)).isoformat()
        self.assertAlmostEqual(backup_age_hours(ts, now=now), 5.0, places=2)

    def test_handles_z_suffix(self):
        now = datetime.now(timezone.utc)
        ts = (now - timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%S.000000Z')
        self.assertAlmostEqual(backup_age_hours(ts, now=now), 2.0, places=1)


class TestHealthySystemHasNoFaults(unittest.TestCase):
    def test_no_faults_when_all_nominal(self):
        faults = evaluate_faults(healthy_metrics())
        self.assertEqual(faults, [])


class TestCpuTempFault(unittest.TestCase):
    def test_fault_at_or_above_threshold(self):
        metrics = healthy_metrics()
        metrics['cpu_temp_c'] = DEFAULT_THRESHOLDS['cpu_temp_alert_c']
        faults = evaluate_faults(metrics)
        self.assertEqual(faults[0]['id'], 'cpu_temp')

    def test_no_fault_just_below_threshold(self):
        metrics = healthy_metrics()
        metrics['cpu_temp_c'] = DEFAULT_THRESHOLDS['cpu_temp_alert_c'] - 0.1
        faults = evaluate_faults(metrics)
        self.assertNotIn('cpu_temp', [f['id'] for f in faults])

    def test_custom_threshold_respected(self):
        metrics = healthy_metrics()
        metrics['cpu_temp_c'] = 70.0
        faults = evaluate_faults(metrics, thresholds={'cpu_temp_alert_c': 65})
        self.assertIn('cpu_temp', [f['id'] for f in faults])


class TestFanStoppedFault(unittest.TestCase):
    def test_fault_when_hot_and_fan_off(self):
        metrics = healthy_metrics()
        metrics['cpu_temp_c'] = DEFAULT_THRESHOLDS['fan_min_temp_c']
        metrics['fan'] = {'rpm': None, 'pwm_percent': 0, 'status': 'Off'}
        faults = evaluate_faults(metrics)
        self.assertIn('fan_stopped', [f['id'] for f in faults])

    def test_no_fault_when_cool_and_fan_off(self):
        metrics = healthy_metrics()
        metrics['cpu_temp_c'] = DEFAULT_THRESHOLDS['fan_min_temp_c'] - 0.1
        metrics['fan'] = {'rpm': None, 'pwm_percent': 0, 'status': 'Off'}
        faults = evaluate_faults(metrics)
        self.assertNotIn('fan_stopped', [f['id'] for f in faults])

    def test_no_fault_when_fan_hardware_not_found(self):
        """Can't assert 'stopped' when there's no hwmon fan device to read at all."""
        metrics = healthy_metrics()
        metrics['cpu_temp_c'] = 50.0
        metrics['fan'] = {'rpm': None, 'pwm_percent': 0, 'status': 'Not Found'}
        faults = evaluate_faults(metrics)
        self.assertNotIn('fan_stopped', [f['id'] for f in faults])

    def test_no_fault_when_fan_spinning(self):
        metrics = healthy_metrics()
        metrics['cpu_temp_c'] = 50.0
        metrics['fan'] = {'rpm': 1500, 'pwm_percent': 30, 'status': '1500 RPM'}
        faults = evaluate_faults(metrics)
        self.assertNotIn('fan_stopped', [f['id'] for f in faults])


class TestBackupFaults(unittest.TestCase):
    def test_fault_when_no_backups(self):
        metrics = healthy_metrics()
        metrics['ha_status']['backup_state'] = 'None'
        metrics['ha_status']['last_backup'] = None
        faults = evaluate_faults(metrics)
        self.assertIn('backup_missing', [f['id'] for f in faults])

    def test_fault_when_backup_old(self):
        now = datetime.now(timezone.utc)
        metrics = healthy_metrics(now=now)
        old_ts = (now - timedelta(hours=DEFAULT_THRESHOLDS['backup_max_age_hours'] + 1)).isoformat()
        metrics['ha_status']['last_backup'] = old_ts
        faults = evaluate_faults(metrics, now=now)
        self.assertIn('backup_old', [f['id'] for f in faults])

    def test_no_fault_when_backup_recent(self):
        faults = evaluate_faults(healthy_metrics())
        self.assertNotIn('backup_old', [f['id'] for f in faults])
        self.assertNotIn('backup_missing', [f['id'] for f in faults])

    def test_no_backup_fault_when_ha_status_unavailable(self):
        """Unknown backup age should not be conflated with 'old backup'."""
        metrics = healthy_metrics()
        metrics['ha_status'] = {'available': False, 'updates': 0, 'last_backup': None, 'backup_state': 'Unknown'}
        faults = evaluate_faults(metrics)
        self.assertNotIn('backup_old', [f['id'] for f in faults])
        self.assertNotIn('backup_missing', [f['id'] for f in faults])
        self.assertIn('ha_unavailable', [f['id'] for f in faults])


class TestStorageFault(unittest.TestCase):
    def test_fault_when_low_free_space(self):
        metrics = healthy_metrics()
        metrics['storage'] = {'available': True, 'percent': 95.0}
        faults = evaluate_faults(metrics)
        self.assertIn('storage_low', [f['id'] for f in faults])

    def test_no_fault_when_storage_unavailable(self):
        """Don't fault on a metric we couldn't obtain - avoid false positives."""
        metrics = healthy_metrics()
        metrics['storage'] = {'available': False, 'percent': 0}
        faults = evaluate_faults(metrics)
        self.assertNotIn('storage_low', [f['id'] for f in faults])


class TestHaStatusAndUpdatesFaults(unittest.TestCase):
    def test_fault_when_ha_status_unavailable(self):
        metrics = healthy_metrics()
        metrics['ha_status']['available'] = False
        faults = evaluate_faults(metrics)
        self.assertIn('ha_unavailable', [f['id'] for f in faults])

    def test_fault_when_updates_available(self):
        metrics = healthy_metrics()
        metrics['ha_status']['updates'] = 3
        faults = evaluate_faults(metrics)
        self.assertIn('updates_available', [f['id'] for f in faults])

    def test_no_updates_fault_when_ha_unavailable(self):
        """available=False should produce exactly one HA-related fault, not both."""
        metrics = healthy_metrics()
        metrics['ha_status']['available'] = False
        metrics['ha_status']['updates'] = 3
        faults = evaluate_faults(metrics)
        ids = [f['id'] for f in faults]
        self.assertIn('ha_unavailable', ids)
        self.assertNotIn('updates_available', ids)


class TestFaultPrioritization(unittest.TestCase):
    """Exception prioritization: hardware safety > data protection > software/info"""

    def test_faults_sorted_by_priority(self):
        now = datetime.now(timezone.utc)
        metrics = {
            'cpu_temp_c': 90.0,  # cpu_temp fault (priority 10)
            'fan': {'rpm': None, 'pwm_percent': 0, 'status': 'Off'},  # fan_stopped (priority 20)
            'storage': {'available': True, 'percent': 99.0},  # storage_low (priority 40)
            'ha_status': {
                'available': True,
                'updates': 5,  # updates_available (priority 60)
                'last_backup': None,
                'backup_state': 'None',  # backup_missing (priority 30)
            },
        }
        faults = evaluate_faults(metrics, now=now)
        ids = [f['id'] for f in faults]
        self.assertEqual(ids, ['cpu_temp', 'fan_stopped', 'backup_missing', 'storage_low', 'updates_available'])

    def test_all_faults_have_title_and_detail(self):
        metrics = {
            'cpu_temp_c': 90.0,
            'fan': {'rpm': None, 'pwm_percent': 0, 'status': 'Off'},
            'storage': {'available': True, 'percent': 99.0},
            'ha_status': {'available': False, 'updates': 0, 'last_backup': None, 'backup_state': 'Unknown'},
        }
        faults = evaluate_faults(metrics)
        self.assertGreater(len(faults), 0)
        for fault in faults:
            self.assertTrue(fault['title'])
            self.assertTrue(fault['detail'])
            self.assertIn('priority', fault)


if __name__ == '__main__':
    unittest.main()
