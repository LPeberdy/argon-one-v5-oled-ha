import unittest
from unittest.mock import Mock, patch

import home_context
from home_context import HomeContextClient, derive_home_context


class TestHomeContext(unittest.TestCase):
    def test_derives_live_home_signals_and_arrival(self):
        previous = [
            {'entity_id': 'person.alex', 'state': 'not_home', 'attributes': {'friendly_name': 'Alex'}},
        ]
        states = [
            {'entity_id': 'weather.home', 'state': 'rainy', 'attributes': {'temperature': 12, 'temperature_unit': '°C'}},
            {'entity_id': 'sensor.living_room_temperature', 'state': '21.5', 'attributes': {'device_class': 'temperature', 'unit_of_measurement': '°C'}},
            {'entity_id': 'sensor.pi_temperature', 'state': '56', 'attributes': {'device_class': 'temperature', 'unit_of_measurement': '°C'}},
            {'entity_id': 'person.alex', 'state': 'home', 'attributes': {'friendly_name': 'Alex'}},
            {'entity_id': 'light.lamp', 'state': 'on', 'attributes': {}},
            {'entity_id': 'binary_sensor.hall_motion', 'state': 'on', 'attributes': {'device_class': 'motion'}},
        ]
        context = derive_home_context(states, previous_states=previous)
        self.assertEqual(context['weather'], 'rainy')
        self.assertTrue(context['precipitation'])
        self.assertEqual(context['outdoor_temp_c'], 12)
        self.assertEqual(context['indoor_temp_c'], 21.5)
        self.assertEqual(context['arrivals'], ['Alex'])
        self.assertEqual(context['lights_on'], 1)
        self.assertEqual(context['motion_on'], 1)

    def test_fahrenheit_temperature_converts_to_celsius(self):
        states = [
            {'entity_id': 'sensor.room_temperature', 'state': '68', 'attributes': {'device_class': 'temperature', 'unit_of_measurement': '°F'}},
        ]
        self.assertAlmostEqual(derive_home_context(states)['indoor_temp_c'], 20.0, places=1)

    @patch('home_context.SUPERVISOR_TOKEN', 'token')
    @patch('home_context.requests.get')
    def test_cached_snapshot_avoids_fast_core_polling(self, mock_get):
        now = [100.0]
        wall = [1000.0]
        response = Mock(status_code=200)
        response.json.return_value = []
        mock_get.return_value = response
        client = HomeContextClient(clock=lambda: now[0], wall_clock=lambda: wall[0])
        client.get_context()
        now[0] += 30
        client.get_context()
        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(mock_get.call_args.args[0], home_context.CORE_STATES_URL)

    @patch('home_context.SUPERVISOR_TOKEN', 'token')
    @patch('home_context.requests.get')
    def test_expired_success_is_not_served_after_failed_refresh(self, mock_get):
        now = [100.0]
        wall = [1000.0]
        ok = Mock(status_code=200)
        ok.json.return_value = [{'entity_id': 'person.a', 'state': 'home', 'attributes': {}}]
        fail = Mock(status_code=500)
        mock_get.side_effect = [ok, fail, ok]
        client = HomeContextClient(clock=lambda: now[0], wall_clock=lambda: wall[0])
        self.assertTrue(client.get_context()['available'])
        now[0] += 60
        self.assertFalse(client.get_context()['available'])
        now[0] += 9
        self.assertFalse(client.get_context()['available'])
        self.assertEqual(mock_get.call_count, 2)
        now[0] += 1
        self.assertTrue(client.get_context()['available'])
        self.assertEqual(mock_get.call_count, 3)


if __name__ == '__main__':
    unittest.main()
