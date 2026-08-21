import unittest

try:
    from visual_modes import VisualModeRenderer
except ImportError:
    VisualModeRenderer = None


@unittest.skipIf(VisualModeRenderer is None, 'luma/Pillow renderer dependencies not installed')
class TestVisualModeSelection(unittest.TestCase):
    def setUp(self):
        self.renderer = VisualModeRenderer.__new__(VisualModeRenderer)

    def test_auto_scene_weather_wins_for_precipitation(self):
        context = {'hour': 12, 'weather': 'rainy', 'home_count': 1, 'lights_on': 0, 'quiet': False, 'motion_on': 0}
        self.assertEqual(self.renderer.choose_ambient_scene(context), 'weather')

    def test_auto_scene_uses_stars_at_night(self):
        context = {'hour': 23, 'weather': 'clear-night', 'home_count': 0, 'lights_on': 0, 'quiet': True, 'motion_on': 0}
        self.assertEqual(self.renderer.choose_ambient_scene(context), 'stars')

    def test_auto_scene_uses_waves_when_warm(self):
        context = {'hour': 14, 'weather': 'sunny', 'indoor_temp_c': 26, 'home_count': 0, 'lights_on': 0, 'quiet': False, 'motion_on': 0}
        self.assertEqual(self.renderer.choose_ambient_scene(context), 'waves')

    def test_auto_scene_uses_plant_when_quiet(self):
        context = {'hour': 14, 'weather': 'cloudy', 'indoor_temp_c': 20, 'home_count': 0, 'lights_on': 0, 'quiet': True, 'motion_on': 0}
        self.assertEqual(self.renderer.choose_ambient_scene(context), 'plant')

    def test_character_maps_urgent_faults_to_expressions(self):
        base = {'hour': 12, 'quiet': False, 'home_count': 1, 'motion_on': 0}
        self.assertEqual(self.renderer._character_mood(base, fault={'id': 'cpu_temp'}), 'hot')
        self.assertEqual(self.renderer._character_mood(base, fault={'id': 'ha_unavailable'}), 'confused')
        self.assertEqual(self.renderer._character_mood(base, fault={'id': 'backup_old'}), 'annoyed')

    def test_character_reacts_to_arrival_and_rain_context(self):
        base = {'hour': 12, 'quiet': False, 'home_count': 1, 'motion_on': 0}
        self.assertEqual(self.renderer._character_mood(base, fact={'id': 'arrival'}), 'excited')
        self.assertEqual(self.renderer._character_mood(base, fact={'id': 'precipitation'}), 'umbrella')


if __name__ == '__main__':
    unittest.main()
