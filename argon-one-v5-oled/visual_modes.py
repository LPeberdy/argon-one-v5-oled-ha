"""Generative ambient and character renderers for the 128x64 OLED."""

from datetime import datetime
import math
import random

from luma.core.render import canvas


RAIN_STATES = {'rainy', 'pouring', 'lightning-rainy'}
SNOW_STATES = {'snowy', 'snowy-rainy', 'hail'}


class VisualModeRenderer:
    def __init__(self, device, fonts, temp_unit='C'):
        self.device = device
        self.font_small = fonts['small']
        self.font_medium = fonts['medium']
        self.font_large = fonts['large']
        self.temp_unit = temp_unit

    @staticmethod
    def _night(context):
        hour = context.get('hour', datetime.now().hour)
        return hour >= 20 or hour < 6

    @staticmethod
    def _temperature(context):
        value = context.get('indoor_temp_c')
        if value is None:
            value = context.get('outdoor_temp_c')
        return value if value is not None else 20.0

    def choose_ambient_scene(self, context, requested='auto'):
        if requested and requested != 'auto':
            return requested
        weather = context.get('weather')
        if weather in RAIN_STATES or weather in SNOW_STATES:
            return 'weather'
        if self._night(context):
            return 'stars'
        if context.get('home_count', 0) and context.get('lights_on', 0) >= 3:
            return 'city'
        if self._temperature(context) >= 24:
            return 'waves'
        if context.get('quiet'):
            return 'plant'
        if context.get('motion_on', 0) > 0:
            return 'particles'
        return 'landscape'

    def draw_ambient(self, context, frame=0, scene='auto'):
        context = context or {'available': False}
        selected = self.choose_ambient_scene(context, scene)
        with canvas(self.device) as draw:
            method = getattr(self, f'_ambient_{selected}', self._ambient_landscape)
            method(draw, context, frame)

    def _ambient_stars(self, draw, context, frame):
        temp = self._temperature(context)
        density = max(14, min(34, int(18 + (temp - 15) * 0.5)))
        seed = datetime.now().timetuple().tm_yday
        rng = random.Random(seed)
        for i in range(density):
            x = rng.randrange(2, 126)
            y = rng.randrange(2, 50)
            if (i + frame // 3) % 5:
                draw.point((x, y), fill=255)
            else:
                draw.rectangle((x, y, x + 1, y + 1), fill=255)
        draw.ellipse((98, 7, 115, 24), outline=255)
        draw.ellipse((93, 4, 108, 20), fill=0)
        self._draw_hills(draw, frame, baseline=56)
        if context.get('home_count', 0):
            draw.rectangle((16, 46, 30, 58), outline=255)
            draw.polygon([(14, 46), (23, 38), (32, 46)], outline=255)
            draw.rectangle((20, 50, 23, 54), fill=255)

    def _ambient_weather(self, draw, context, frame):
        phase = frame % 128
        for offset in (-35, 10, 55):
            x = (offset + phase // 3) % 150 - 15
            self._cloud(draw, x, 8 + (offset % 2) * 5)
        weather = context.get('weather')
        if weather in SNOW_STATES:
            for i in range(24):
                x = (i * 23 + frame * (1 + i % 2)) % 128
                y = (i * 17 + frame * 2) % 44 + 20
                draw.point((x, y), fill=255)
                if i % 5 == 0:
                    draw.point(((x + 1) % 128, y), fill=255)
        else:
            for i in range(22):
                x = (i * 19 + frame * 2) % 132 - 2
                y = (i * 13 + frame * 4) % 46 + 17
                draw.line((x, y, x - 2, y + 5), fill=255)
        self._draw_hills(draw, frame, baseline=59)

    def _ambient_waves(self, draw, context, frame):
        temp = self._temperature(context)
        amplitude = max(2, min(7, int(2 + (temp - 18) / 2)))
        for band, base in enumerate((28, 40, 52)):
            points = []
            for x in range(0, 128, 2):
                y = base + int(amplitude * math.sin((x + frame * (1 + band)) / (9.0 + band * 2)))
                points.append((x, y))
            draw.line(points, fill=255, width=1)
        if self._night(context):
            draw.ellipse((94, 5, 109, 20), outline=255)
        else:
            draw.ellipse((97, 5, 111, 19), fill=255)
        for i in range(context.get('home_count', 0)):
            x = (18 + i * 21 + frame) % 128
            draw.point((x, 16 + (i % 3)), fill=255)

    def _ambient_city(self, draw, context, frame):
        rng = random.Random(8021)
        x = 0
        building = 0
        while x < 128:
            width = rng.randint(10, 18)
            height = rng.randint(20, 47)
            top = 63 - height
            draw.rectangle((x, top, min(127, x + width), 63), outline=255)
            for wx in range(x + 3, min(127, x + width - 1), 5):
                for wy in range(top + 4, 60, 7):
                    lit = (wx + wy + building + context.get('lights_on', 0) + frame // 8) % 4 == 0
                    if lit:
                        draw.rectangle((wx, wy, wx + 1, wy + 2), fill=255)
            x += width + 3
            building += 1
        if not self._night(context):
            draw.ellipse((8, 5, 20, 17), outline=255)
        for i in range(context.get('motion_on', 0)):
            px = (frame * 3 + i * 31) % 128
            draw.point((px, 57), fill=255)

    def _ambient_plant(self, draw, context, frame):
        sway = int(3 * math.sin(frame / 8.0))
        draw.rectangle((51, 50, 76, 62), outline=255)
        draw.line((64, 50, 64 + sway, 19), fill=255)
        branches = [(42, 40), (84, 36), (45, 29), (81, 24)]
        for i, (tx, ty) in enumerate(branches):
            start_y = 46 - i * 7
            sx = 64 + int(sway * (start_y - 18) / 32)
            draw.line((sx, start_y, tx + sway, ty), fill=255)
            draw.ellipse((tx - 5 + sway, ty - 3, tx + 5 + sway, ty + 3), outline=255)
        temp = self._temperature(context)
        particles = max(3, min(12, int(temp / 3)))
        for i in range(particles):
            x = (i * 37 + frame) % 128
            y = (i * 19 + frame // 2) % 45
            draw.point((x, y), fill=255)

    def _ambient_particles(self, draw, context, frame):
        temp = self._temperature(context)
        density = max(10, min(30, int(10 + temp * 0.7)))
        activity = 1 + min(3, context.get('motion_on', 0) + context.get('home_count', 0))
        for i in range(density):
            x = (i * 41 + frame * activity * (1 + i % 3)) % 128
            y = (i * 29 + frame * (1 + (i % 2))) % 64
            if i % 6 == 0:
                draw.rectangle((x, y, min(127, x + 1), min(63, y + 1)), fill=255)
            else:
                draw.point((x, y), fill=255)

    def _ambient_landscape(self, draw, context, frame):
        night = self._night(context)
        if night:
            for i in range(14):
                draw.point(((i * 29 + 7) % 128, (i * 17 + 5) % 30), fill=255)
            draw.ellipse((99, 5, 112, 18), outline=255)
        else:
            sun_y = 8 + int(4 * math.sin(frame / 40.0))
            draw.ellipse((96, sun_y, 110, sun_y + 14), fill=255)
        self._draw_hills(draw, frame, baseline=45)
        self._draw_hills(draw, frame + 25, baseline=56)
        if context.get('home_count', 0):
            draw.rectangle((16, 45, 32, 59), outline=255)
            draw.polygon([(13, 45), (24, 35), (35, 45)], outline=255)
            for i in range(min(2, context.get('home_count', 0))):
                draw.rectangle((20 + i * 7, 49, 23 + i * 7, 53), fill=255)

    @staticmethod
    def _cloud(draw, x, y):
        draw.ellipse((x, y + 5, x + 18, y + 15), outline=255)
        draw.ellipse((x + 8, y, x + 25, y + 15), outline=255)
        draw.ellipse((x + 17, y + 5, x + 34, y + 15), outline=255)
        draw.line((x + 3, y + 15, x + 31, y + 15), fill=255)

    @staticmethod
    def _draw_hills(draw, frame, baseline=54):
        points = []
        for x in range(0, 128, 3):
            y = baseline + int(4 * math.sin((x + frame / 4) / 15.0))
            points.append((x, y))
        draw.line(points, fill=255)

    def draw_contextual(self, fact):
        with canvas(self.device) as draw:
            draw.rectangle((0, 0, 127, 63), outline=255)
            draw.text((64, 15), fact.get('title', 'NOW'), font=self.font_medium, fill=255, anchor='mm')
            draw.line((18, 27, 110, 27), fill=255)
            draw.text((64, 44), fact.get('detail', ''), font=self.font_small, fill=255, anchor='mm')
            draw.text((64, 58), '•', font=self.font_small, fill=255, anchor='mm')

    def draw_character(self, context, frame=0, fault=None, fact=None, cpu_temp_c=None):
        context = context or {'available': False}
        mood = self._character_mood(context, fault=fault, fact=fact, cpu_temp_c=cpu_temp_c)
        label = (fault or fact or {}).get('title')

        with canvas(self.device) as draw:
            draw.rounded_rectangle((29, 7, 98, 55), radius=15, outline=255)
            self._draw_character_face(draw, mood, frame)
            if label:
                text = label[:18]
                draw.rectangle((0, 54, 127, 63), fill=0)
                draw.text((64, 58), text, font=self.font_small, fill=255, anchor='mm')

    def _character_mood(self, context, fault=None, fact=None, cpu_temp_c=None):
        if fault:
            fault_id = fault.get('id')
            if fault_id in ('cpu_temp', 'fan_stopped'):
                return 'hot'
            if fault_id == 'ha_unavailable':
                return 'confused'
            return 'annoyed'
        if fact:
            if fact.get('id') == 'arrival':
                return 'excited'
            if fact.get('id') == 'precipitation':
                return 'umbrella'
            if fact.get('id') in ('warm_home', 'warm_pi'):
                return 'hot'
        if context.get('recent_arrivals'):
            return 'excited'
        if cpu_temp_c is not None and cpu_temp_c >= 65:
            return 'hot'
        if context.get('precipitation'):
            return 'umbrella'
        if context.get('quiet') and self._night(context):
            return 'sleeping'
        if context.get('home_count', 0) > 0 or context.get('motion_on', 0) > 0:
            return 'happy'
        return 'calm'

    def _draw_character_face(self, draw, mood, frame):
        if mood == 'sleeping':
            draw.line((44, 29, 54, 29), fill=255)
            draw.line((73, 29, 83, 29), fill=255)
            draw.arc((53, 34, 74, 48), 0, 180, fill=255)
            draw.text((92, 13), 'z', font=self.font_small, fill=255)
            draw.text((102, 5), 'z', font=self.font_small, fill=255)
            return

        if mood == 'confused':
            draw.ellipse((44, 24, 50, 30), outline=255)
            draw.ellipse((75, 22, 81, 28), outline=255)
            draw.line((56, 43, 63, 40, 70, 44), fill=255)
            draw.text((100, 10), '?', font=self.font_medium, fill=255)
            return

        if mood == 'annoyed':
            draw.line((42, 25, 53, 29), fill=255)
            draw.line((74, 29, 85, 25), fill=255)
            draw.rectangle((47, 31, 50, 34), fill=255)
            draw.rectangle((77, 31, 80, 34), fill=255)
            draw.line((55, 46, 72, 43), fill=255)
            draw.text((101, 9), '!', font=self.font_medium, fill=255)
            return

        if mood == 'hot':
            draw.ellipse((45, 26, 50, 31), fill=255)
            draw.ellipse((77, 26, 82, 31), fill=255)
            draw.ellipse((57, 39, 70, 49), outline=255)
            drop = 1 + (frame // 3) % 3
            draw.line((103, 18, 100, 23 + drop), fill=255)
            draw.ellipse((98, 22 + drop, 102, 27 + drop), outline=255)
            return

        if mood == 'umbrella':
            draw.ellipse((45, 27, 50, 32), fill=255)
            draw.ellipse((77, 27, 82, 32), fill=255)
            draw.arc((54, 36, 73, 48), 180, 360, fill=255)
            draw.arc((88, 7, 119, 28), 180, 360, fill=255)
            draw.line((103, 18, 103, 36), fill=255)
            draw.arc((97, 31, 104, 39), 270, 90, fill=255)
            return

        if mood == 'excited':
            eye_h = 2 + (frame % 2)
            draw.rectangle((44, 25, 50, 25 + eye_h), fill=255)
            draw.rectangle((77, 25, 83, 25 + eye_h), fill=255)
            draw.arc((51, 32, 76, 50), 0, 180, fill=255)
            draw.text((14, 14), '*', font=self.font_small, fill=255)
            draw.text((108, 18), '*', font=self.font_small, fill=255)
            return

        draw.ellipse((45, 27, 50, 32), fill=255)
        draw.ellipse((77, 27, 82, 32), fill=255)
        if mood == 'happy':
            draw.arc((52, 33, 75, 48), 0, 180, fill=255)
        else:
            draw.line((57, 43, 70, 43), fill=255)
