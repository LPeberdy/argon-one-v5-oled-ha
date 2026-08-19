"""
Home Assistant Supervisor API client

Read-only client for the Supervisor API. Only issues GET requests and only
calls status/info endpoints that are expected to be reachable with the
addon's configured `hassio_role` (see config.yaml). There is no host
control, addon management, or any other mutating capability here by design:
this addon must never be able to reboot/shutdown the host, manage other
addons, or otherwise act with elevated privilege.
"""

import os
import socket

import requests


SUPERVISOR_TOKEN = os.environ.get('SUPERVISOR_TOKEN', '')


class SupervisorAPI:
    """Read-only client for the Home Assistant Supervisor API"""

    def __init__(self, debug_callback=None):
        self.debug_callback = debug_callback

    def _log(self, message):
        """Log debug message if callback is set"""
        if self.debug_callback:
            self.debug_callback(message)

    def request(self, endpoint, timeout=5):
        """Issue a GET request to the Supervisor API with standard error handling.

        Returns the response object, or None if the request could not be
        completed (network error, timeout, or no token available).
        """
        if not SUPERVISOR_TOKEN:
            self._log("No SUPERVISOR_TOKEN available - cannot call Supervisor API")
            return None

        try:
            headers = {
                'Authorization': f'Bearer {SUPERVISOR_TOKEN}',
                'Content-Type': 'application/json',
            }
            url = f'http://supervisor/{endpoint}'
            return requests.get(url, headers=headers, timeout=timeout)
        except requests.exceptions.Timeout:
            self._log(f"GET request to {endpoint} timed out")
            return None
        except Exception as e:
            self._log(f"GET request to {endpoint} failed: {e}")
            return None

    def _get_data(self, endpoint):
        """GET an endpoint and return (data, available).

        available is True only when the endpoint returned HTTP 200 with a
        parseable body. Any other outcome (network failure, non-200 status
        such as 403 for an insufficiently-privileged role, or a bad body)
        is reported as unavailable so callers never mistake "could not
        reach the API" for "API returned an empty/zero result".
        """
        response = self.request(endpoint)
        if response is None:
            return {}, False
        if response.status_code != 200:
            self._log(f"GET {endpoint} returned status {response.status_code}")
            return {}, False
        try:
            return response.json().get('data', {}), True
        except ValueError:
            self._log(f"GET {endpoint} returned an unparseable body")
            return {}, False

    def get_network_info(self):
        """Get network information including IP addresses. Returns (data, available)."""
        return self._get_data('network/info')

    def get_homeassistant_info(self):
        """Get Home Assistant info including URLs. Returns (data, available)."""
        return self._get_data('homeassistant/info')

    def get_core_info(self):
        """Get Home Assistant core info. Returns (data, available)."""
        return self._get_data('core/info')

    def get_supervisor_info(self):
        """Get supervisor info. Returns (data, available)."""
        return self._get_data('supervisor/info')

    def get_addons(self):
        """Get list of addons. Returns (addons_list, available)."""
        data, available = self._get_data('addons')
        return data.get('addons', []), available

    def get_backups(self):
        """Get list of backups. Returns (backups_list, available)."""
        data, available = self._get_data('backups')
        return data.get('backups', []), available

    def get_ip_address(self):
        """Get host IP address from the Supervisor API, falling back to a
        local socket lookup if the API is unavailable."""
        try:
            network_info, available = self.get_network_info()
            if available:
                interfaces = network_info.get('interfaces', [])

                for interface in interfaces:
                    if interface.get('primary', False):
                        ipv4 = interface.get('ipv4', {})
                        addresses = ipv4.get('address', [])
                        if addresses:
                            return addresses[0].split('/')[0]

                for interface in interfaces:
                    if not interface.get('interface', '').startswith('docker'):
                        ipv4 = interface.get('ipv4', {})
                        addresses = ipv4.get('address', [])
                        if addresses:
                            return addresses[0].split('/')[0]
        except Exception as e:
            self._log(f"Could not get IP from Supervisor API: {e}")

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "No Network"

    def get_ha_url(self):
        """Get the Home Assistant URL for display/QR purposes, if available."""
        try:
            ha_info, available = self.get_homeassistant_info()
            if available:
                external_url = ha_info.get('external_url')
                internal_url = ha_info.get('internal_url')
                if external_url:
                    return external_url
                if internal_url:
                    return internal_url
        except Exception as e:
            self._log(f"Could not get HA URL from API: {e}")

        ip = self.get_ip_address()
        if ip != "No Network":
            return f"http://{ip}:8123"

        return None

    def get_ha_system_status(self):
        """Get Home Assistant system status for the status screen and fault engine.

        Returns a dict:
            available: bool - True if at least the core update/backup
                queries succeeded (i.e. the Supervisor API answered with
                the addon's configured role). If False, treat HA status
                as unknown/unavailable rather than assuming "all clear".
            updates: int - count of pending updates (supervisor + core + addons)
            last_backup: str or None - ISO timestamp of most recent backup
            backup_state: 'OK' | 'None' | 'Unknown'
        """
        status_info = {
            'available': False,
            'updates': 0,
            'last_backup': None,
            'backup_state': 'Unknown',
        }

        supervisor_info, supervisor_available = self.get_supervisor_info()
        core_info, core_available = self.get_core_info()
        addons, addons_available = self.get_addons()
        backups, backups_available = self.get_backups()

        # Consider HA status "available" only if we could reach the core
        # info endpoints; if the addon's role can't reach any of them,
        # report unavailable rather than a misleading "0 updates".
        status_info['available'] = supervisor_available and core_available

        if status_info['available']:
            if supervisor_info.get('update_available', False):
                status_info['updates'] += 1
            if core_info.get('update_available', False):
                status_info['updates'] += 1
            if addons_available:
                for addon in addons:
                    if addon.get('update_available', False):
                        status_info['updates'] += 1

        if backups_available:
            self._log(f"Found {len(backups)} backups")
            if backups:
                sorted_backups = sorted(backups, key=lambda x: x.get('date', ''), reverse=True)
                latest = sorted_backups[0]
                status_info['last_backup'] = latest.get('date')
                status_info['backup_state'] = 'OK'
            else:
                status_info['backup_state'] = 'None'
        else:
            status_info['backup_state'] = 'Unknown'

        return status_info
