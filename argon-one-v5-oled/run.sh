#!/usr/bin/with-contenv bashio
# ==============================================================================
# Home Assistant Add-on: Argon ONE OLED Display
# Runs the Argon ONE OLED display service
# ==============================================================================

bashio::log.info "Starting Argon ONE OLED Display Add-on..."

DISPLAY_MODE=$(bashio::config 'mode')
AMBIENT_SCENE=$(bashio::config 'ambient_scene')
CONTEXTUAL_INTERRUPTS=$(bashio::config 'contextual_interruptions')
URGENT_INTERRUPTS=$(bashio::config 'urgent_interruptions')
CONTEXTUAL_DURATION=$(bashio::config 'contextual_duration')
CONTEXTUAL_INTERVAL=$(bashio::config 'contextual_interval')
HA_REFRESH_SECONDS=$(bashio::config 'ha_refresh_seconds')
TEMP_UNIT=$(bashio::config 'temp_unit')
SWITCH_DURATION=$(bashio::config 'switch_duration')
SCREEN_LIST=$(bashio::config 'screen_list')
DEBUG_LOGGING=$(bashio::config 'debug_logging')
SHOW_CREDITS=$(bashio::config 'show_credits')
CPU_TEMP_ALERT_C=$(bashio::config 'cpu_temp_alert_c')
FAN_MIN_TEMP_C=$(bashio::config 'fan_min_temp_c')
BACKUP_MAX_AGE_HOURS=$(bashio::config 'backup_max_age_hours')
STORAGE_MIN_FREE_PERCENT=$(bashio::config 'storage_min_free_percent')

ADDON_VERSION=$(bashio::addon.version)

bashio::log.info "Display mode: ${DISPLAY_MODE}"
bashio::log.info "Ambient scene: ${AMBIENT_SCENE}"
bashio::log.info "Contextual interruptions: ${CONTEXTUAL_INTERRUPTS} (${CONTEXTUAL_DURATION}s every >=${CONTEXTUAL_INTERVAL}s)"
bashio::log.info "Urgent interruptions: ${URGENT_INTERRUPTS}"
bashio::log.info "Home Assistant state refresh: ${HA_REFRESH_SECONDS}s"
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

if [ ! -c /dev/i2c-1 ]; then
    bashio::log.warning "I2C device not found at /dev/i2c-1"
    bashio::log.warning "Make sure I2C is enabled on your Raspberry Pi"
fi

export DISPLAY_MODE="${DISPLAY_MODE}"
export AMBIENT_SCENE="${AMBIENT_SCENE}"
export CONTEXTUAL_INTERRUPTS="${CONTEXTUAL_INTERRUPTS}"
export URGENT_INTERRUPTS="${URGENT_INTERRUPTS}"
export CONTEXTUAL_DURATION="${CONTEXTUAL_DURATION}"
export CONTEXTUAL_INTERVAL="${CONTEXTUAL_INTERVAL}"
export HA_REFRESH_SECONDS="${HA_REFRESH_SECONDS}"
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

bashio::log.info "Starting OLED display service..."
python3 /argon_oled.py
