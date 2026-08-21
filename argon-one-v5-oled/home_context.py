"""Read-only Home Assistant state snapshot and context derivation.

The OLED refreshes locally once per second, but Home Assistant entity state is
fetched much more slowly and cached. This module only issues GET requests to
the Home Assistant Core API proxy; it contains no service calls or mutations.
"""

from datetime import datetime
import os
import statistics
import time

import requests


SUPERVISOR_TOKEN = os.environ.get('SUPERVISOR_TOKEN', '')
CORE_STATES_URL = 'http://supervisor/core/api/states'
DEFAULT_STATE_TTL = 60
DEFAULT_FAILURE_RETRY_TTL = 10
ARRIVAL_VISIBLE_SECONDS = 45

_PRECIPITATION = {
    'rainy', 'pouring', 'lightning-rainy', 'snowy', 'snowy-rainy', 'hail',
}


def _to_celsius(value, unit):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if str(unit or '').upper().startswith('F') or '°F' in str(unit or ''):
        return (number - 32.0) * 5.0 / 9.0
    return number


def _entity_name(entity):
    attrs = entity.get('attributes') or {}
    return attrs.get('friendly_name') or entity.get('entity_id', '').split('.', 1)[-1].replace('_', ' ').title()


def _state_map(states):
    return {item.get('entity_id'): item for item in states if item.get('entity_id')}


def derive_home_context(states, previous_states=None, now=None):
    """Turn a Home Assistant /states payload into a compact display context."""
    states = states if isinstance(states, list) else []
    previous = _state_map(previous_states or [])
    current = _state_map(states)
    now_dt = now or datetime.now()

    weather = None
    for entity_id, entity in current.items():
        if entity_id.startswith('weather.') and entity.get('state') not in ('unknown', 'unavailable'):
            weather = entity
            break

    weather_condition = weather.get('state') if weather else None
    weather_attrs = (weather or {}).get('attributes') or {}
    outdoor_temp_c = _to_celsius(
        weather_attrs.get('temperature'),
        weather_attrs.get('temperature_unit') or weather_attrs.get('unit_of_measurement'),
    )

    indoor_temperatures = []
    for entity_id, entity in current.items():
        if not entity_id.startswith('sensor.'):
            continue
        attrs = entity.get('attributes') or {}
        if attrs.get('device_class') != 'temperature':
            continue
        name = f"{entity_id} {_entity_name(entity)}".lower()
        if any(token in name for token in (
            'cpu', 'processor', 'raspberry', 'pi temperature', 'system', 'outdoor',
            'outside', 'weather', 'battery', 'phone', 'ipad', 'macbook', 'ssd',
            'nvme', 'soc', 'gpu', 'radio', 'chip',
        )):
            continue
        value_c = _to_celsius(entity.get('state'), attrs.get('unit_of_measurement'))
        if value_c is not None and -10 <= value_c <= 45:
            indoor_temperatures.append(value_c)

    indoor_temp_c = statistics.median(indoor_temperatures) if indoor_temperatures else None

    people_home = []
    arrivals = []
    total_people = 0
    for entity_id, entity in current.items():
        if not entity_id.startswith('person.'):
            continue
        total_people += 1
        state = entity.get('state')
        if state == 'home':
            name = _entity_name(entity)
            people_home.append(name)
            old = previous.get(entity_id)
            if old and old.get('state') != 'home':
                arrivals.append(name)

    lights_on = sum(
        1 for entity_id, entity in current.items()
        if entity_id.startswith('light.') and entity.get('state') == 'on'
    )

    motion_on = 0
    for entity_id, entity in current.items():
        if not entity_id.startswith('binary_sensor.') or entity.get('state') != 'on':
            continue
        device_class = ((entity.get('attributes') or {}).get('device_class') or '').lower()
        if device_class in ('motion', 'occupancy', 'presence'):
            motion_on += 1

    return {
        'available': True,
        'weather': weather_condition,
        'precipitation': weather_condition in _PRECIPITATION,
        'outdoor_temp_c': outdoor_temp_c,
        'indoor_temp_c': indoor_temp_c,
        'home_count': len(people_home),
        'total_people': total_people,
        'people_home': people_home,
        'arrivals': arrivals,
        'lights_on': lights_on,
        'motion_on': motion_on,
        'quiet': motion_on == 0 and lights_on == 0,
        'hour': now_dt.hour,
    }


class HomeContextClient:
    """GET-only, TTL-cached Home Assistant entity context provider."""

    def __init__(self, debug_callback=None, state_ttl=DEFAULT_STATE_TTL,
                 failure_retry_ttl=DEFAULT_FAILURE_RETRY_TTL,
                 clock=None, wall_clock=None):
        self.debug_callback = debug_callback
        self.state_ttl = max(0, float(state_ttl))
        self.failure_retry_ttl = max(0, float(failure_retry_ttl))
        self._clock = clock or time.monotonic
        self._wall_clock = wall_clock or time.time
        self._expires_at = 0.0
        self._context = {'available': False}
        self._previous_states = []
        self._arrival_names = []
        self._arrival_until = 0.0

    def _log(self, message):
        if self.debug_callback:
            self.debug_callback(message)

    def _request_states(self):
        if not SUPERVISOR_TOKEN:
            self._log('No SUPERVISOR_TOKEN available - cannot read Home Assistant states')
            return None
        try:
            response = requests.get(
                CORE_STATES_URL,
                headers={
                    'Authorization': f'Bearer {SUPERVISOR_TOKEN}',
                    'Content-Type': 'application/json',
                },
                timeout=5,
            )
        except requests.exceptions.Timeout:
            self._log('Home Assistant state request timed out')
            return None
        except Exception as exc:
            self._log(f'Home Assistant state request failed: {exc}')
            return None

        if response.status_code != 200:
            self._log(f'GET Home Assistant states returned status {response.status_code}')
            return None
        try:
            payload = response.json()
        except ValueError:
            self._log('GET Home Assistant states returned an unparseable body')
            return None
        return payload if isinstance(payload, list) else None

    def get_context(self):
        """Return the current compact context, refreshing at most once per TTL."""
        now_mono = self._clock()
        now_wall = self._wall_clock()

        if now_mono >= self._expires_at:
            states = self._request_states()
            if states is None:
                self._context = {'available': False}
                self._expires_at = now_mono + self.failure_retry_ttl
            else:
                context = derive_home_context(states, previous_states=self._previous_states)
                if context.get('arrivals'):
                    self._arrival_names = list(context['arrivals'])
                    self._arrival_until = now_wall + ARRIVAL_VISIBLE_SECONDS
                self._previous_states = states
                self._context = context
                self._expires_at = now_mono + self.state_ttl

        result = dict(self._context)
        result['hour'] = datetime.now().hour
        if result.get('available') and now_wall < self._arrival_until:
            result['recent_arrivals'] = list(self._arrival_names)
        else:
            result['recent_arrivals'] = []
        return result
