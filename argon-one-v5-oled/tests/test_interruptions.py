import unittest

from interruptions import InterruptionController, evaluate_contextual_facts


class TestContextualFacts(unittest.TestCase):
    def test_arrival_is_more_relevant_than_weather_temperature_and_occupancy(self):
        context = {
            'available': True,
            'recent_arrivals': ['Alex'],
            'weather': 'rainy',
            'precipitation': True,
            'outdoor_temp_c': 12,
            'indoor_temp_c': 28,
            'home_count': 1,
            'total_people': 2,
            'lights_on': 2,
            'hour': 18,
        }
        facts = evaluate_contextual_facts(context, {'cpu_temp_c': 70})
        self.assertEqual(facts[0]['id'], 'arrival')

    def test_unavailable_home_context_yields_no_fact(self):
        self.assertEqual(evaluate_contextual_facts({'available': False}), [])


class TestInterruptionController(unittest.TestCase):
    def test_urgent_faults_outrank_context_and_cycle(self):
        now = [100.0]
        controller = InterruptionController(clock=lambda: now[0], initial_context_delay=0)
        facts = [{'id': 'weather', 'priority': 70, 'title': 'OUTSIDE', 'detail': 'Clear'}]
        faults = [
            {'id': 'a', 'priority': 1, 'title': 'A', 'detail': ''},
            {'id': 'b', 'priority': 2, 'title': 'B', 'detail': ''},
        ]
        self.assertEqual(controller.choose(faults, facts)['item']['id'], 'a')
        now[0] += 5
        self.assertEqual(controller.choose(faults, facts)['item']['id'], 'b')

    def test_context_is_brief_then_returns_to_normal_until_interval(self):
        now = [100.0]
        controller = InterruptionController(
            clock=lambda: now[0],
            contextual_duration=8,
            contextual_interval=300,
            initial_context_delay=0,
        )
        facts = [{'id': 'weather', 'priority': 70, 'title': 'OUTSIDE', 'detail': 'Clear'}]
        self.assertEqual(controller.choose([], facts)['kind'], 'contextual')
        now[0] += 7
        self.assertEqual(controller.choose([], facts)['kind'], 'contextual')
        now[0] += 2
        self.assertEqual(controller.choose([], facts)['kind'], 'normal')
        now[0] = 400
        self.assertEqual(controller.choose([], facts)['kind'], 'contextual')

    def test_both_interruption_layers_can_be_disabled(self):
        now = [100.0]
        controller = InterruptionController(
            clock=lambda: now[0],
            contextual_enabled=False,
            urgent_enabled=False,
            initial_context_delay=0,
        )
        self.assertEqual(controller.choose([{'id': 'fault'}], [{'id': 'fact'}])['kind'], 'normal')


if __name__ == '__main__':
    unittest.main()
