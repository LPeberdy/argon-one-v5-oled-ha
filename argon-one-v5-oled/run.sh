#!/usr/bin/with-contenv bashio
# ==============================================================================
# Home Assistant Add-on: Argon ONE OLED Display
# Runs the Argon ONE OLED display service
# ==============================================================================

bashio::log.info "Starting Argon ONE OLED Display Add-on..."

# Parse configuration
TEMP_UNIT=$(bashio::config 'temp_unit')
SWITCH_DURATION=$(bashio::config 'switch_duration')
SCREEN_LIST=$(bashio::config 'screen_list')
DEBUG_LOGGING=$(bashio::config 'debug_logging')
SHOW_CREDITS=$(bashio::config 'show_credits')
CPU_TEMP_ALERT_C=$(bashio::config 'cpu_temp_alert_c')
FAN_MIN_TEMP_C=$(bashio::config 'fan_min_temp_c')
BACKUP_MAX_AGE_HOURS=$(bashio::config 'backup_max_age_hours')
STORAGE_MIN_FREE_PERCENT=$(bashio::config 'storage_min_free_percent')

# Get addon version from config.yaml
ADDON_VERSION=$(bashio::addon.version)

# Log configuration
bashio::log.info "Temperature unit: ${TEMP_UNIT}"
bashio::log.info "Screen switch duration: ${SWITCH_DURATION}s"
bashio::log.info "Screen list: ${SCREEN_LIST}"
bashio::log.info "Debug logging: ${DEBUG_LOGGING}"
bashio::log.info "Show credits: ${SHOW_CREDITS}"
bashio::log.info "CPU temp alert threshold: ${CPU_TEMP_ALERT_C}C"
bashio::log.info "Fan expected-spinning threshold: ${FAN_MIN_TEMP_C}C"
bashio::log.info "Backup max age: ${BACKUP_MAX_AGE_HOURS}h"
bashio::log.info "Storage min free: ${STORAGE_MIN_FREE_PERCENT}%"
bashio::log.info "Addon version: ${ADDON_VERSION}"

# Check if I2C device is available
if [ ! -c /dev/i2c-1 ]; then
    bashio::log.warning "I2C device not found at /dev/i2c-1"
    bashio::log.warning "Make sure I2C is enabled on your Raspberry Pi"
fi

# Export configuration as environment variables for Python script
export TEMP_UNIT="${TEMP_UNIT}"
export SWITCH_DURATION="${SWITCH_DURATION}"
export SCREEN_LIST="${SCREEN_LIST}"
export DEBUG_LOGGING="${DEBUG_LOGGING}"
export SHOW_CREDITS="${SHOW_CREDITS}"
export ADDON_VERSION="${ADDON_VERSION}"
export CPU_TEMP_ALERT_C="${CPU_TEMP_ALERT_C}"
export FAN_MIN_TEMP_C="${FAN_MIN_TEMP_C}"
export BACKUP_MAX_AGE_HOURS="${BACKUP_MAX_AGE_HOURS}"
export STORAGE_MIN_FREE_PERCENT="${STORAGE_MIN_FREE_PERCENT}"

# Run the OLED display service
bashio::log.info "Starting OLED display service..."
python3 /argon_oled.py
