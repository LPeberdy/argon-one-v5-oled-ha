"""
Fault evaluation engine.

Pure functions that turn system/status metrics into a prioritized list of
active faults. Kept free of any I/O or device access so it can be unit
tested exhaustively and reasoned about independently of the rendering and
data-collection code.

When any fault is active, the display should show alert screens for the
active faults instead of (in priority order, ahead of) the routine
rotation - see argon_oled.py.
"""

from datetime import datetime, timezone


# Fault severity/priority - lower number = shown first / more urgent.
# Hardware safety issues rank above data-protection issues, which rank
# above software/informational issues.
PRIORITY_CPU_TEMP = 10
PRIORITY_FAN_STOPPED = 20
PRIORITY_BACKUP = 30
PRIORITY_STORAGE = 40
PRIORITY_HA_UNAVAILABLE = 50
PRIORITY_UPDATES = 60

DEFAULT_THRESHOLDS = {
    'cpu_temp_alert_c': 80,
    'fan_min_temp_c': 55,
    'backup_max_age_hours': 48,
    'storage_min_free_percent': 10,
}


def _make_fault(fault_id, priority, title, detail):
    return {
        'id': fault_id,
        'priority': priority,
        'title': title,
        'detail': detail,
    }


def backup_age_hours(last_backup_iso, now=None):
    """Return hours since the given ISO-8601 backup timestamp, or None if
    the timestamp is missing/unparseable."""
    if not last_backup_iso:
        return None
    try:
        backup_dt = datetime.fromisoformat(last_backup_iso.replace('Z', '+00:00'))
        if backup_dt.tzinfo is None:
            backup_dt = backup_dt.replace(tzinfo=timezone.utc)
        reference = now or datetime.now(timezone.utc)
        delta = reference - backup_dt
        return delta.total_seconds() / 3600.0
    except (ValueError, TypeError):
        return None


def evaluate_faults(metrics, thresholds=None, now=None):
    """Compute the active, priority-ordered list of faults.

    metrics is a dict expected to contain:
        cpu_temp_c: float - CPU temperature, always in Celsius regardless
            of display temp_unit (caller is responsible for conversion
            for display only)
        fan: dict from SystemInfo.get_fan_speed()
        storage: dict with 'available' (bool), 'percent' (float, used%)
        ha_status: dict from SupervisorAPI.get_ha_system_status()
            ('available', 'updates', 'last_backup', 'backup_state')

    thresholds overrides DEFAULT_THRESHOLDS (e.g. from addon config).

    Returns a list of fault dicts sorted by priority (most urgent first).
    Empty list means the system is healthy and routine rotation should be shown.
    """
    cfg = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        cfg.update(thresholds)

    faults = []

    cpu_temp_c = metrics.get('cpu_temp_c')
    if cpu_temp_c is not None and cpu_temp_c >= cfg['cpu_temp_alert_c']:
        faults.append(_make_fault(
            'cpu_temp',
            PRIORITY_CPU_TEMP,
            'HIGH TEMP',
            f"CPU {cpu_temp_c:.0f}C >= {cfg['cpu_temp_alert_c']}C",
        ))

    fan = metrics.get('fan') or {}
    fan_status = fan.get('status')
    if (
        cpu_temp_c is not None
        and fan_status is not None
        and fan_status != 'Not Found'
        and cpu_temp_c >= cfg['fan_min_temp_c']
        and fan.get('pwm_percent', 0) == 0
    ):
        faults.append(_make_fault(
            'fan_stopped',
            PRIORITY_FAN_STOPPED,
            'FAN STOPPED',
            f"Fan off at {cpu_temp_c:.0f}C (expected >= {cfg['fan_min_temp_c']}C)",
        ))

    ha_status = metrics.get('ha_status') or {}
    if ha_status.get('available'):
        backup_state = ha_status.get('backup_state')
        if backup_state == 'None':
            faults.append(_make_fault(
                'backup_missing',
                PRIORITY_BACKUP,
                'NO BACKUP',
                'No backups found',
            ))
        else:
            age_hours = backup_age_hours(ha_status.get('last_backup'), now=now)
            if age_hours is not None and age_hours >= cfg['backup_max_age_hours']:
                age_days = age_hours / 24.0
                faults.append(_make_fault(
                    'backup_old',
                    PRIORITY_BACKUP,
                    'OLD BACKUP',
                    f"Last backup {age_days:.1f}d ago",
                ))
    # If ha_status is unavailable we can't know backup age; that's
    # reported via the ha_unavailable fault below instead of guessing.

    storage = metrics.get('storage') or {}
    if storage.get('available'):
        percent_used = storage.get('percent', 0)
        free_percent = 100 - percent_used
        if free_percent <= cfg['storage_min_free_percent']:
            faults.append(_make_fault(
                'storage_low',
                PRIORITY_STORAGE,
                'LOW STORAGE',
                f"{free_percent:.0f}% free (min {cfg['storage_min_free_percent']}%)",
            ))

    if not ha_status.get('available'):
        faults.append(_make_fault(
            'ha_unavailable',
            PRIORITY_HA_UNAVAILABLE,
            'HA STATUS',
            'Unavailable: API/role',
        ))
    elif ha_status.get('updates', 0) > 0:
        faults.append(_make_fault(
            'updates_available',
            PRIORITY_UPDATES,
            'UPDATES',
            f"{ha_status['updates']} update(s) available",
        ))

    faults.sort(key=lambda f: f['priority'])
    return faults
