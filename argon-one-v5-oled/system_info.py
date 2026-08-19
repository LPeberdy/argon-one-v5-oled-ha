"""
System information retrieval module
Provides methods to get system metrics like CPU, RAM, storage, temperature, etc.
"""

import glob
import os


class SystemInfo:
    """Handles system information gathering"""

    def __init__(self, temp_unit='C'):
        self.temp_unit = temp_unit
        self.prev_idle = None
        self.prev_total = None

    def get_cpu_temp(self):
        """Get CPU temperature"""
        try:
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp_c = float(f.read()) / 1000.0
                if self.temp_unit == 'F':
                    return (temp_c * 9 / 5) + 32
                return temp_c
        except Exception:
            return 0

    def get_cpu_usage(self):
        """Get CPU usage percentage"""
        try:
            with open('/proc/stat', 'r') as f:
                line = f.readline()
                fields = line.split()
                idle = float(fields[4])
                total = sum(float(x) for x in fields[1:])

                if self.prev_idle is None:
                    self.prev_idle = idle
                    self.prev_total = total
                    return 0

                diff_idle = idle - self.prev_idle
                diff_total = total - self.prev_total
                self.prev_idle = idle
                self.prev_total = total

                if diff_total == 0:
                    return 0

                usage = 100 * (1 - diff_idle / diff_total)
                return max(0, min(100, usage))
        except Exception:
            return 0

    def get_load_average(self):
        """Get 1/5/15 minute load averages"""
        try:
            return os.getloadavg()
        except (OSError, AttributeError):
            return 0.0, 0.0, 0.0

    def get_uptime_seconds(self):
        """Get system uptime in seconds"""
        try:
            with open('/proc/uptime', 'r') as f:
                return float(f.read().split()[0])
        except Exception:
            return 0

    def get_memory_usage(self):
        """Get memory usage in MB and percentage"""
        try:
            with open('/proc/meminfo', 'r') as f:
                lines = f.readlines()
                mem_total = 0
                mem_available = 0

                for line in lines:
                    if line.startswith('MemTotal:'):
                        mem_total = int(line.split()[1]) / 1024  # Convert to MB
                    elif line.startswith('MemAvailable:'):
                        mem_available = int(line.split()[1]) / 1024

                if mem_total > 0:
                    mem_used = mem_total - mem_available
                    mem_percent = (mem_used / mem_total) * 100
                    return mem_used, mem_total, mem_percent
        except Exception:
            pass
        return 0, 0, 0

    def get_disk_usage(self, path='/data'):
        """Get disk usage representing real host storage.

        The addon's own /data directory is always bind-mounted from the
        host's actual data partition (independent of the `map` option),
        so statvfs() on it reflects genuine host free space. The
        container's root filesystem ("/") is an overlay of the image
        layer and is NOT representative of host storage - using it would
        misleadingly report the (typically tiny, nearly-full) overlay
        instead of real disk usage, so we deliberately do not fall back
        to it.

        Returns: (used_gb, total_gb, percent, available)
        `available` is False when host storage figures could not be
        obtained; callers must not display used/total/percent as if they
        were accurate in that case.
        """
        try:
            stat = os.statvfs(path)
            total = (stat.f_blocks * stat.f_frsize) / (1024 ** 3)
            free = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)
            used = total - free
            percent = (used / total) * 100 if total > 0 else 0
            return used, total, percent, True
        except Exception:
            return 0, 0, 0, False

    def get_fan_speed(self):
        """Get fan speed from Raspberry Pi 5 native fan connector.

        This only reads the kernel hwmon interface; it never writes to
        the fan controller and never modifies the fan curve, which is
        left entirely to the kernel/firmware (`dtparam=fan_temp*` in
        /mnt/boot/config.txt) as documented in the README.

        Returns: dict with 'rpm' (int or None), 'pwm_percent' (int 0-100), 'status' (str)
        """
        result = {
            'rpm': None,
            'pwm_percent': 0,
            'status': 'Not Found',
        }

        try:
            hwmon_paths = glob.glob('/sys/class/hwmon/hwmon*/name')

            for name_file in hwmon_paths:
                try:
                    with open(name_file, 'r') as f:
                        device_name = f.read().strip()

                    if any(keyword in device_name.lower() for keyword in ['fan', 'cooling', 'rp1']):
                        hwmon_dir = os.path.dirname(name_file)

                        fan_input = os.path.join(hwmon_dir, 'fan1_input')
                        if os.path.exists(fan_input):
                            with open(fan_input, 'r') as f:
                                result['rpm'] = int(f.read().strip())

                        pwm_file = os.path.join(hwmon_dir, 'pwm1')
                        if os.path.exists(pwm_file):
                            with open(pwm_file, 'r') as f:
                                pwm_value = int(f.read().strip())
                                result['pwm_percent'] = int((pwm_value / 255) * 100)

                                if result['pwm_percent'] == 0:
                                    result['status'] = 'Off'
                                elif result['rpm'] is not None:
                                    result['status'] = f"{result['rpm']} RPM"
                                else:
                                    result['status'] = f"{result['pwm_percent']}%"

                                return result
                except Exception:
                    continue
        except Exception:
            pass

        return result
