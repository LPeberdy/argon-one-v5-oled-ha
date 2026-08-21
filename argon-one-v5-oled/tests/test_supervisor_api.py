"""
Unit tests for supervisor_api module.

This client is read-only by design: no reboot/shutdown, no host control,
no POST requests. Tests here also assert that unreachable/forbidden
endpoints are reported as unavailable rather than silently treated as
"zero" results, and that Supervisor polling is decoupled from the fast
OLED refresh loop by shared TTL caches.
"""

import unittest
from unittest.mock import patch, Mock, MagicMock

try:
    from supervisor_api import SupervisorAPI
    SUPERVISOR_API_AVAILABLE = True
except ImportError:
    SupervisorAPI = None
    SUPERVISOR_API_AVAILABLE = False


@unittest.skipUnless(SUPERVISOR_API_AVAILABLE, "requests module required")
class TestSupervisorAPI(unittest.TestCase):
    """Test SupervisorAPI class"""

    def setUp(self):
        self.debug_messages = []
        self.now = 1000.0

        def debug_callback(msg):
            self.debug_messages.append(msg)

        self.api = SupervisorAPI(
            debug_callback=debug_callback,
            clock=lambda: self.now,
        )

    @staticmethod
    def response(data, status_code=200):
        response = Mock()
        response.status_code = status_code
        response.json.return_value = {'data': data}
        return response

    def test_init(self):
        self.assertIsNotNone(self.api.debug_callback)
        self.assertEqual(self.api.info_ttl, 60)
        self.assertEqual(self.api.backup_ttl, 300)
        self.assertEqual(self.api.failure_retry_ttl, 10)

    def test_init_without_callback(self):
        api = SupervisorAPI()
        self.assertIsNone(api.debug_callback)

    def test_no_post_method_exists(self):
        self.assertFalse(hasattr(self.api, 'reboot_host'))
        self.assertFalse(hasattr(self.api, 'shutdown_host'))
        self.assertFalse(hasattr(self.api, 'check_power_permissions'))

    @patch('supervisor_api.SUPERVISOR_TOKEN', 'test_token')
    @patch('supervisor_api.requests.get')
    def test_request_get_success(self, mock_get):
        mock_response = self.response('test')
        mock_get.return_value = mock_response

        response = self.api.request('test/endpoint')

        self.assertEqual(response.status_code, 200)
        mock_get.assert_called_once()

    def test_request_without_token_returns_none(self):
        with patch('supervisor_api.SUPERVISOR_TOKEN', ''):
            response = self.api.request('test/endpoint')
            self.assertIsNone(response)

    @patch('supervisor_api.SUPERVISOR_TOKEN', 'test_token')
    @patch('supervisor_api.requests.get')
    def test_request_timeout(self, mock_get):
        mock_get.side_effect = Exception('Timeout')

        response = self.api.request('test/endpoint')

        self.assertIsNone(response)
        self.assertTrue(any('failed' in msg for msg in self.debug_messages))

    @patch('supervisor_api.SUPERVISOR_TOKEN', 'test_token')
    @patch('supervisor_api.requests.get')
    def test_get_data_reports_unavailable_on_403(self, mock_get):
        mock_get.return_value = self.response({}, status_code=403)

        data, available = self.api.get_supervisor_info()

        self.assertEqual(data, {})
        self.assertFalse(available)

    @patch('supervisor_api.SUPERVISOR_TOKEN', 'test_token')
    @patch('supervisor_api.requests.get')
    def test_get_data_available_on_200(self, mock_get):
        mock_get.return_value = self.response({'update_available': True})

        data, available = self.api.get_supervisor_info()

        self.assertTrue(available)
        self.assertEqual(data, {'update_available': True})

    @patch('supervisor_api.SUPERVISOR_TOKEN', 'test_token')
    @patch('supervisor_api.requests.get')
    def test_repeated_calls_inside_ttl_do_not_repeat_http(self, mock_get):
        mock_get.return_value = self.response({'update_available': False})

        first = self.api.get_supervisor_info()
        self.now += 30
        second = self.api.get_supervisor_info()

        self.assertEqual(first, second)
        self.assertEqual(mock_get.call_count, 1)

    @patch('supervisor_api.SUPERVISOR_TOKEN', 'test_token')
    @patch('supervisor_api.requests.get')
    def test_data_refreshes_after_ttl_expiry(self, mock_get):
        mock_get.side_effect = [
            self.response({'update_available': False}),
            self.response({'update_available': True}),
        ]

        first, available = self.api.get_core_info()
        self.assertTrue(available)
        self.assertFalse(first['update_available'])

        self.now += 60
        second, available = self.api.get_core_info()

        self.assertTrue(available)
        self.assertTrue(second['update_available'])
        self.assertEqual(mock_get.call_count, 2)

    @patch('supervisor_api.SUPERVISOR_TOKEN', 'test_token')
    @patch('supervisor_api.requests.get')
    def test_backups_use_slower_five_minute_cadence(self, mock_get):
        counts = {'supervisor/info': 0, 'core/info': 0, 'backups': 0}

        def get_response(url, **kwargs):
            endpoint = url.removeprefix('http://supervisor/')
            counts[endpoint] += 1
            if endpoint == 'backups':
                return self.response({'backups': [{'date': '2026-08-21T10:00:00+00:00'}]})
            return self.response({'update_available': False})

        mock_get.side_effect = get_response

        self.api.get_ha_system_status()
        self.now += 60
        self.api.get_ha_system_status()

        self.assertEqual(counts['supervisor/info'], 2)
        self.assertEqual(counts['core/info'], 2)
        self.assertEqual(counts['backups'], 1)

        self.now += 240
        self.api.get_ha_system_status()
        self.assertEqual(counts['backups'], 2)

    @patch('supervisor_api.SUPERVISOR_TOKEN', 'test_token')
    @patch('supervisor_api.requests.get')
    def test_expired_success_does_not_mask_supervisor_failure(self, mock_get):
        mock_get.side_effect = [
            self.response({'update_available': False}),
            self.response({}, status_code=503),
            self.response({'update_available': True}),
        ]

        data, available = self.api.get_supervisor_info()
        self.assertTrue(available)
        self.assertFalse(data['update_available'])

        self.now += 60
        data, available = self.api.get_supervisor_info()
        self.assertFalse(available)
        self.assertEqual(data, {})
        self.assertEqual(mock_get.call_count, 2)

        # Failed refreshes are cached only briefly: no one-second retry storm.
        self.now += 5
        data, available = self.api.get_supervisor_info()
        self.assertFalse(available)
        self.assertEqual(mock_get.call_count, 2)

        # Recovery is retried sooner than the normal 60-second success TTL.
        self.now += 5
        data, available = self.api.get_supervisor_info()
        self.assertTrue(available)
        self.assertTrue(data['update_available'])
        self.assertEqual(mock_get.call_count, 3)

    @patch('supervisor_api.SUPERVISOR_TOKEN', 'test_token')
    @patch('supervisor_api.requests.get')
    def test_fault_and_screen_consumers_share_cached_status_snapshot(self, mock_get):
        responses = {
            'supervisor/info': self.response({'update_available': False}),
            'core/info': self.response({'update_available': True}),
            'backups': self.response({'backups': [{'date': '2026-08-21T10:00:00+00:00'}]}),
        }

        def get_response(url, **kwargs):
            return responses[url.removeprefix('http://supervisor/')]

        mock_get.side_effect = get_response

        # First call represents the main-loop fault collector. The second
        # represents draw_ha_status() during the same cache window.
        fault_status = self.api.get_ha_system_status()
        screen_status = self.api.get_ha_system_status()

        self.assertEqual(fault_status, screen_status)
        self.assertEqual(mock_get.call_count, 3)

    @patch('supervisor_api.SUPERVISOR_TOKEN', 'test_token')
    @patch('supervisor_api.requests.get')
    def test_get_ip_address_from_network(self, mock_get):
        mock_get.return_value = self.response({
            'interfaces': [
                {
                    'primary': True,
                    'ipv4': {'address': ['192.168.1.100/24']}
                }
            ]
        })

        ip = self.api.get_ip_address()

        self.assertEqual(ip, '192.168.1.100')

    @patch('supervisor_api.SUPERVISOR_TOKEN', '')
    @patch('supervisor_api.socket.socket')
    def test_get_ip_address_fallback(self, mock_socket):
        mock_sock = MagicMock()
        mock_sock.getsockname.return_value = ['10.0.0.5', 0]
        mock_socket.return_value = mock_sock

        ip = self.api.get_ip_address()

        self.assertEqual(ip, '10.0.0.5')

    @patch('supervisor_api.SupervisorAPI.get_homeassistant_info')
    def test_get_ha_url_external(self, mock_get_ha_info):
        mock_get_ha_info.return_value = ({'external_url': 'https://mydomain.com'}, True)

        url = self.api.get_ha_url()

        self.assertEqual(url, 'https://mydomain.com')

    @patch('supervisor_api.SUPERVISOR_TOKEN', 'test_token')
    @patch('supervisor_api.requests.get')
    def test_get_ha_system_status_available(self, mock_get):
        mock_supervisor = self.response({'update_available': False})
        mock_core = self.response({'update_available': True})
        mock_backups = self.response({
            'backups': [{'date': '2025-11-20T10:00:00+00:00'}]
        })

        mock_get.side_effect = [mock_supervisor, mock_core, mock_backups]

        status = self.api.get_ha_system_status()

        self.assertTrue(status['available'])
        self.assertEqual(status['updates'], 1)
        self.assertEqual(status['backup_state'], 'OK')
        self.assertIsNotNone(status['last_backup'])

    @patch('supervisor_api.SUPERVISOR_TOKEN', 'test_token')
    @patch('supervisor_api.requests.get')
    def test_get_ha_system_status_unavailable_on_403(self, mock_get):
        forbidden = self.response({}, status_code=403)
        mock_get.side_effect = [forbidden, forbidden, forbidden]

        status = self.api.get_ha_system_status()

        self.assertFalse(status['available'])
        self.assertEqual(status['updates'], 0)
        self.assertEqual(status['backup_state'], 'Unknown')

    @patch('supervisor_api.SUPERVISOR_TOKEN', '')
    def test_get_ha_system_status_unavailable_without_token(self):
        status = self.api.get_ha_system_status()
        self.assertFalse(status['available'])


if __name__ == '__main__':
    unittest.main()
