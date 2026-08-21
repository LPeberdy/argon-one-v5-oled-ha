"""Display interruption arbitration.

Urgent faults outrank contextual facts, which outrank the selected normal mode.
The contextual layer deliberately shows a single fact briefly and then returns
to the living/default display instead of becoming another rotating dashboard.
"""

import time


_CONTEXT_PRIORITIES = {
    'arrival': 10,
    'precipitation': 20,
    'warm_home': 30,
    'cold_home': 30,
    'warm_pi': 40,
    'occupancy': 50,
    'night_lights': 60,
    'weather': 70,
}


def _fact(fact_id, title, detail):
    return {
        'id': fact_id,
        'priority': _CONTEXT_PRIORITIES[fact_id],
        'title': title,
        'detail': detail,
    }


def evaluate_contextual_facts(context, metrics=None):
    """Return relevance-ranked non-urgent facts from live home state."""
    if not (context or {}).get('available'):
        return []

    facts = []
    arrivals = context.get('recent_arrivals') or []
    if arrivals:
        name = arrivals[0]
        suffix = '' if len(arrivals) == 1 else f' +{len(arrivals) - 1}'
        facts.append(_fact('arrival', 'WELCOME HOME', f'{name}{suffix} arrived'))

    weather = (context.get('weather') or '').replace('-', ' ').title()
    outdoor = context.get('outdoor_temp_c')
    if context.get('precipitation'):
        detail = weather or 'Wet weather'
        if outdoor is not None:
            detail = f'{detail}, {outdoor:.0f}C'
        facts.append(_fact('precipitation', 'WEATHER', detail))

    indoor = context.get('indoor_temp_c')
    if indoor is not None and indoor >= 26:
        facts.append(_fact('warm_home', 'WARM HOME', f'Inside {indoor:.1f}C'))
    elif indoor is not None and indoor <= 15:
        facts.append(_fact('cold_home', 'COOL HOME', f'Inside {indoor:.1f}C'))

    cpu_temp = (metrics or {}).get('cpu_temp_c')
    if cpu_temp is not None and 65 <= cpu_temp < 80:
        facts.append(_fact('warm_pi', 'PI IS WARM', f'CPU {cpu_temp:.0f}C'))

    home_count = context.get('home_count', 0)
    total_people = context.get('total_people', 0)
    if home_count:
        facts.append(_fact(
            'occupancy',
            'HOME',
            f'{home_count}/{total_people or home_count} home',
        ))

    hour = context.get('hour', 12)
    lights_on = context.get('lights_on', 0)
    if (hour >= 22 or hour < 6) and lights_on > 0:
        facts.append(_fact('night_lights', 'STILL AWAKE', f'{lights_on} light(s) on'))

    if weather and not context.get('precipitation'):
        detail = weather
        if outdoor is not None:
            detail = f'{weather}, {outdoor:.0f}C'
        facts.append(_fact('weather', 'OUTSIDE', detail))

    facts.sort(key=lambda item: item['priority'])
    return facts


class InterruptionController:
    """Stateful urgent/context/normal arbitration with bounded interruptions."""

    def __init__(self, contextual_enabled=True, urgent_enabled=True,
                 contextual_duration=8, contextual_interval=300,
                 urgent_switch_duration=5, initial_context_delay=30,
                 clock=None):
        self.contextual_enabled = bool(contextual_enabled)
        self.urgent_enabled = bool(urgent_enabled)
        self.contextual_duration = max(1, float(contextual_duration))
        self.contextual_interval = max(self.contextual_duration, float(contextual_interval))
        self.urgent_switch_duration = max(1, float(urgent_switch_duration))
        self._clock = clock or time.monotonic
        now = self._clock()
        self._next_context_at = now + max(0, float(initial_context_delay))
        self._context_until = 0.0
        self._active_context = None
        self._urgent_index = 0
        self._last_urgent_switch = now
        self._was_urgent = False

    def choose(self, faults, contextual_facts):
        now = self._clock()
        faults = faults or []
        contextual_facts = contextual_facts or []

        if self.urgent_enabled and faults:
            self._active_context = None
            self._context_until = 0.0
            if not self._was_urgent:
                self._urgent_index = 0
                self._last_urgent_switch = now
            elif now - self._last_urgent_switch >= self.urgent_switch_duration:
                self._urgent_index = (self._urgent_index + 1) % len(faults)
                self._last_urgent_switch = now
            else:
                self._urgent_index = min(self._urgent_index, len(faults) - 1)
            self._was_urgent = True
            return {'kind': 'urgent', 'item': faults[self._urgent_index]}

        if self._was_urgent:
            self._was_urgent = False
            self._next_context_at = max(self._next_context_at, now + 10)

        if self.contextual_enabled and self._active_context and now < self._context_until:
            return {'kind': 'contextual', 'item': self._active_context}

        if now >= self._context_until:
            self._active_context = None

        if self.contextual_enabled and contextual_facts and now >= self._next_context_at:
            self._active_context = contextual_facts[0]
            self._context_until = now + self.contextual_duration
            self._next_context_at = now + self.contextual_interval
            return {'kind': 'contextual', 'item': self._active_context}

        return {'kind': 'normal', 'item': None}
