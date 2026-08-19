"""
Unit tests for supervisor_api module

This client is read-only by design: no reboot/shutdown, no host control,
no POST requests. Tests here also assert that unreachable/forbidden
endpoints are reported as unavailable rather than silently treated as
"zero" results, since the fault engine (faults.py) and status screen
depend on that distinction.
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
        """Set up test fixtures"""
        self.debug_messages = []

        def debug_callback(msg):
            self.debug_messages.append(msg)

        self.api = SupervisorAPI(debug_callback=debug_callback)

    def test_init(self):
        """Test SupervisorAPI initialization"""
        self.assertIsNotNone(self.api.debug_callback)

    def test_init_without_callback(self):
        """Test SupervisorAPI initialization without debug callback"""
        api = SupervisorAPI()
        self.assertIsNone(api.debug_callback)

    def test_no_post_method_exists(self):
        """This client must never be able to issue a mutating (POST) call"""
        self.assertFalse(hasattr(self.api, 'reboot_host'))
        self.assertFalse(hasattr(self.api, 'shutdown_host'))
        self.assertFalse(hasattr(self.api, 'check_power_permissions'))

    @patch('supervisor_api.SUPERVISOR_TOKEN', 'test_token')
    @patch('supervisor_api.requests.get')
    def test_request_get_success(self, mock_get):
        """Test successful GET request"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': 'test'}
        mock_get.return_value = mock_response

        response = self.api.request('test/endpoint')

        self.assertEqual(response.status_code, 200)
        mock_get.assert_called_once()

    def test_request_without_token_returns_none(self):
        """No SUPERVISOR_TOKEN should mean no API call is even attempted"""
        with patch('supervisor_api.SUPERVISOR_TOKEN', ''):
            response = self.api.request('test/endpoint')
            self.assertIsNone(response)

    @patch('supervisor_api.SUPERVISOR_TOKEN', 'test_token')
    @patch('supervisor_api.requests.get')
    def test_request_timeout(self, mock_get):
        """Test request timeout handling"""
        mock_get.side_effect = Exception('Timeout')

        response = self.api.request('test/endpoint')

        self.assertIsNone(response)
        self.assertTrue(any('failed' in msg for msg in self.debug_messages))

    @patch('supervisor_api.SUPERVISOR_TOKEN', 'test_token')
    @patch('supervisor_api.requests.get')
    def test_get_data_reports_unavailable_on_403(self, mock_get):
        """A 403 (e.g. insufficient hassio_role) must be reported as
        unavailable, not as an empty-but-successful result."""
        mock_response = Mock()
        mock_response.status_code = 403
        mock_get.return_value = mock_response

        data, available = self.api.get_supervisor_info()

        self.assertEqual(data, {})
        self.assertFalse(available)

    @patch('supervisor_api.SUPERVISOR_TOKEN', 'test_token')
    @patch('supervisor_api.requests.get')
    def test_get_data_available_on_200(self, mock_get):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': {'update_available': True}}
        mock_get.return_value = mock_response

        data, available = self.api.get_supervisor_info()

        self.assertTrue(available)
        self.assertEqual(data, {'update_available': True})

    @patch('supervisor_api.SUPERVISOR_TOKEN', 'test_token')
    @patch('supervisor_api.requests.get')
    def test_get_ip_address_from_network(self, mock_get):
        """Test getting IP address from network API"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': {
                'interfaces': [
                    {
                        'primary': True,
                        'ipv4': {
                            'address': ['192.168.1.100/24']
                        }
                    }
                ]
            }
        }
        mock_get.return_value = mock_response

        ip = self.api.get_ip_address()

        self.assertEqual(ip, '192.168.1.100')

    @patch('supervisor_api.SUPERVISOR_TOKEN', '')
    @patch('supervisor_api.socket.socket')
    def test_get_ip_address_fallback(self, mock_socket):
        """Test IP address fallback to socket method when API unreachable"""
        mock_sock = MagicMock()
        mock_sock.getsockname.return_value = ['10.0.0.5', 0]
        mock_socket.return_value = mock_sock

        ip = self.api.get_ip_address()

        self.assertEqual(ip, '10.0.0.5')

    @patch('supervisor_api.SupervisorAPI.get_homeassistant_info')
    def test_get_ha_url_external(self, mock_get_ha_info):
        """Test getting HA URL with external URL configured"""
        mock_get_ha_info.return_value = ({'external_url': 'https://mydomain.com'}, True)

        url = self.api.get_ha_url()

        self.assertEqual(url, 'https://mydomain.com')

    @patch('supervisor_api.SUPERVISOR_TOKEN', 'test_token')
    @patch('supervisor_api.requests.get')
    def test_get_ha_system_status_available(self, mock_get):
        """Test getting HA system status when the API is fully reachable"""
        mock_supervisor = Mock(status_code=200, json=Mock(return_value={'data': {'update_available': False}}))
        mock_core = Mock(status_code=200, json=Mock(return_value={'data': {'update_available': True}}))
        mock_backups = Mock(status_code=200, json=Mock(return_value={
            'data': {'backups': [{'date': '2025-11-20T10:00:00+00:00'}]}
        }))

        mock_get.side_effect = [mock_supervisor, mock_core, mock_backups]

        status = self.api.get_ha_system_status()

        self.assertTrue(status['available'])
        self.assertEqual(status['updates'], 1)  # core only
        self.assertEqual(status['backup_state'], 'OK')
        self.assertIsNotNone(status['last_backup'])

    @patch('supervisor_api.SUPERVISOR_TOKEN', 'test_token')
    @patch('supervisor_api.requests.get')
    def test_get_ha_system_status_unavailable_on_403(self, mock_get):
        """Insufficient role (403) must surface as available=False, not '0 updates'."""
        forbidden = Mock(status_code=403)
        mock_get.side_effect = [forbidden, forbidden, forbidden]

        status = self.api.get_ha_system_status()

        self.assertFalse(status['available'])
        self.assertEqual(status['updates'], 0)
        self.assertEqual(status['backup_state'], 'Unknown')

    @patch('supervisor_api.SUPERVISOR_TOKEN', '')
    def test_get_ha_system_status_unavailable_without_token(self):
        """No token at all must also surface as unavailable."""
        status = self.api.get_ha_system_status()
        self.assertFalse(status['available'])


if __name__ == '__main__':
    unittest.main()
