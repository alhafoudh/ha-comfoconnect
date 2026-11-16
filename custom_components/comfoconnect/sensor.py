"""Platform to control a Zehnder ComfoAir Q350/450/600 ventilation unit."""

from dataclasses import dataclass
from datetime import datetime
import logging
import time
from typing import override

import probatio
from pycomfoconnect import (
    SENSOR_BYPASS_STATE,
    SENSOR_CURRENT_RMOT,
    SENSOR_DAYS_TO_REPLACE_FILTER,
    SENSOR_FAN_EXHAUST_DUTY,
    SENSOR_FAN_EXHAUST_FLOW,
    SENSOR_FAN_EXHAUST_SPEED,
    SENSOR_FAN_SUPPLY_DUTY,
    SENSOR_FAN_SUPPLY_FLOW,
    SENSOR_FAN_SUPPLY_SPEED,
    SENSOR_HUMIDITY_EXHAUST,
    SENSOR_HUMIDITY_EXTRACT,
    SENSOR_HUMIDITY_OUTDOOR,
    SENSOR_HUMIDITY_SUPPLY,
    SENSOR_POWER_CURRENT,
    SENSOR_POWER_TOTAL,
    SENSOR_PREHEATER_POWER_CURRENT,
    SENSOR_PREHEATER_POWER_TOTAL,
    SENSOR_TEMPERATURE_EXHAUST,
    SENSOR_TEMPERATURE_EXTRACT,
    SENSOR_TEMPERATURE_OUTDOOR,
    SENSOR_TEMPERATURE_SUPPLY,
)

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA as SENSOR_PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONF_RESOURCES,
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import CALLBACK_TYPE, HassJob, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import DOMAIN, SIGNAL_COMFOCONNECT_UPDATE_RECEIVED, ComfoConnectBridge

ATTR_AIR_FLOW_EXHAUST = "air_flow_exhaust"
ATTR_AIR_FLOW_SUPPLY = "air_flow_supply"
ATTR_BYPASS_STATE = "bypass_state"
ATTR_CURRENT_HUMIDITY = "current_humidity"
ATTR_CURRENT_RMOT = "current_rmot"
ATTR_CURRENT_TEMPERATURE = "current_temperature"
ATTR_DAYS_TO_REPLACE_FILTER = "days_to_replace_filter"
ATTR_EXHAUST_FAN_DUTY = "exhaust_fan_duty"
ATTR_EXHAUST_FAN_SPEED = "exhaust_fan_speed"
ATTR_EXHAUST_HUMIDITY = "exhaust_humidity"
ATTR_EXHAUST_TEMPERATURE = "exhaust_temperature"
ATTR_OUTSIDE_HUMIDITY = "outside_humidity"
ATTR_OUTSIDE_TEMPERATURE = "outside_temperature"
ATTR_POWER_CURRENT = "power_usage"
ATTR_POWER_TOTAL = "power_total"
ATTR_PREHEATER_POWER_CURRENT = "preheater_power_usage"
ATTR_PREHEATER_POWER_TOTAL = "preheater_power_total"
ATTR_SUPPLY_FAN_DUTY = "supply_fan_duty"
ATTR_SUPPLY_FAN_SPEED = "supply_fan_speed"
ATTR_SUPPLY_HUMIDITY = "supply_humidity"
ATTR_SUPPLY_TEMPERATURE = "supply_temperature"

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class ComfoconnectSensorEntityDescription(SensorEntityDescription):
    """Describes Comfoconnect sensor entity."""

    sensor_id: int
    multiplier: float = 1


SENSOR_TYPES = (
    ComfoconnectSensorEntityDescription(
        key=ATTR_CURRENT_TEMPERATURE,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Inside temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        sensor_id=SENSOR_TEMPERATURE_EXTRACT,
        multiplier=0.1,
    ),
    ComfoconnectSensorEntityDescription(
        key=ATTR_CURRENT_HUMIDITY,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        name="Inside humidity",
        native_unit_of_measurement=PERCENTAGE,
        sensor_id=SENSOR_HUMIDITY_EXTRACT,
    ),
    ComfoconnectSensorEntityDescription(
        key=ATTR_CURRENT_RMOT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Current RMOT",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        sensor_id=SENSOR_CURRENT_RMOT,
        multiplier=0.1,
    ),
    ComfoconnectSensorEntityDescription(
        key=ATTR_OUTSIDE_TEMPERATURE,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Outside temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        sensor_id=SENSOR_TEMPERATURE_OUTDOOR,
        multiplier=0.1,
    ),
    ComfoconnectSensorEntityDescription(
        key=ATTR_OUTSIDE_HUMIDITY,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        name="Outside humidity",
        native_unit_of_measurement=PERCENTAGE,
        sensor_id=SENSOR_HUMIDITY_OUTDOOR,
    ),
    ComfoconnectSensorEntityDescription(
        key=ATTR_SUPPLY_TEMPERATURE,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Supply temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        sensor_id=SENSOR_TEMPERATURE_SUPPLY,
        multiplier=0.1,
    ),
    ComfoconnectSensorEntityDescription(
        key=ATTR_SUPPLY_HUMIDITY,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        name="Supply humidity",
        native_unit_of_measurement=PERCENTAGE,
        sensor_id=SENSOR_HUMIDITY_SUPPLY,
    ),
    ComfoconnectSensorEntityDescription(
        key=ATTR_SUPPLY_FAN_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        name="Supply fan speed",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        icon="mdi:fan-plus",
        sensor_id=SENSOR_FAN_SUPPLY_SPEED,
    ),
    ComfoconnectSensorEntityDescription(
        key=ATTR_SUPPLY_FAN_DUTY,
        state_class=SensorStateClass.MEASUREMENT,
        name="Supply fan duty",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:fan-plus",
        sensor_id=SENSOR_FAN_SUPPLY_DUTY,
    ),
    ComfoconnectSensorEntityDescription(
        key=ATTR_EXHAUST_FAN_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        name="Exhaust fan speed",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        icon="mdi:fan-minus",
        sensor_id=SENSOR_FAN_EXHAUST_SPEED,
    ),
    ComfoconnectSensorEntityDescription(
        key=ATTR_EXHAUST_FAN_DUTY,
        state_class=SensorStateClass.MEASUREMENT,
        name="Exhaust fan duty",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:fan-minus",
        sensor_id=SENSOR_FAN_EXHAUST_DUTY,
    ),
    ComfoconnectSensorEntityDescription(
        key=ATTR_EXHAUST_TEMPERATURE,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Exhaust temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        sensor_id=SENSOR_TEMPERATURE_EXHAUST,
        multiplier=0.1,
    ),
    ComfoconnectSensorEntityDescription(
        key=ATTR_EXHAUST_HUMIDITY,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        name="Exhaust humidity",
        native_unit_of_measurement=PERCENTAGE,
        sensor_id=SENSOR_HUMIDITY_EXHAUST,
    ),
    ComfoconnectSensorEntityDescription(
        key=ATTR_AIR_FLOW_SUPPLY,
        state_class=SensorStateClass.MEASUREMENT,
        name="Supply airflow",
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        icon="mdi:fan-plus",
        sensor_id=SENSOR_FAN_SUPPLY_FLOW,
    ),
    ComfoconnectSensorEntityDescription(
        key=ATTR_AIR_FLOW_EXHAUST,
        state_class=SensorStateClass.MEASUREMENT,
        name="Exhaust airflow",
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        icon="mdi:fan-minus",
        sensor_id=SENSOR_FAN_EXHAUST_FLOW,
    ),
    ComfoconnectSensorEntityDescription(
        key=ATTR_BYPASS_STATE,
        state_class=SensorStateClass.MEASUREMENT,
        name="Bypass state",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:camera-iris",
        sensor_id=SENSOR_BYPASS_STATE,
    ),
    ComfoconnectSensorEntityDescription(
        key=ATTR_DAYS_TO_REPLACE_FILTER,
        name="Days to replace filter",
        native_unit_of_measurement=UnitOfTime.DAYS,
        icon="mdi:calendar",
        sensor_id=SENSOR_DAYS_TO_REPLACE_FILTER,
    ),
    ComfoconnectSensorEntityDescription(
        key=ATTR_POWER_CURRENT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        name="Power usage",
        native_unit_of_measurement=UnitOfPower.WATT,
        sensor_id=SENSOR_POWER_CURRENT,
    ),
    ComfoconnectSensorEntityDescription(
        key=ATTR_POWER_TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        name="Energy total",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        sensor_id=SENSOR_POWER_TOTAL,
    ),
    ComfoconnectSensorEntityDescription(
        key=ATTR_PREHEATER_POWER_CURRENT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        name="Preheater power usage",
        native_unit_of_measurement=UnitOfPower.WATT,
        sensor_id=SENSOR_PREHEATER_POWER_CURRENT,
    ),
    ComfoconnectSensorEntityDescription(
        key=ATTR_PREHEATER_POWER_TOTAL,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        name="Preheater energy total",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        sensor_id=SENSOR_PREHEATER_POWER_TOTAL,
    ),
)

CONF_THROTTLE = "throttle"
CONF_DEADBAND = "deadband"

# The bridge pushes every tiny change (fan RPM jitters by a few rpm several times
# a second), and each one becomes a state write sent to every websocket client.
# By default a sensor writes at most once per DEFAULT_THROTTLE seconds; a change
# of at least its deadband is written right away so real changes stay snappy.
DEFAULT_THROTTLE = 60.0
DEFAULT_DEADBANDS: dict[str, float] = {
    ATTR_EXHAUST_FAN_SPEED: 50,
    ATTR_SUPPLY_FAN_SPEED: 50,
    ATTR_AIR_FLOW_EXHAUST: 10,
    ATTR_AIR_FLOW_SUPPLY: 10,
    ATTR_POWER_CURRENT: 3,
    ATTR_PREHEATER_POWER_CURRENT: 3,
}

PLATFORM_SCHEMA = SENSOR_PLATFORM_SCHEMA.extend(
    {
        probatio.Optional(CONF_RESOURCES, default=[]): probatio.All(
            probatio.EnsureList(), [probatio.In([desc.key for desc in SENSOR_TYPES])]
        ),
        probatio.Optional(CONF_THROTTLE, default=DEFAULT_THROTTLE): cv.positive_float,
        probatio.Optional(CONF_DEADBAND, default={}): probatio.Schema(
            {
                probatio.Optional(desc.key): cv.positive_float
                for desc in SENSOR_TYPES
            }
        ),
    }
)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the ComfoConnect sensor platform."""
    ccb = hass.data[DOMAIN]
    deadbands = {**DEFAULT_DEADBANDS, **config[CONF_DEADBAND]}

    sensors = [
        ComfoConnectSensor(
            ccb=ccb,
            description=description,
            throttle=config[CONF_THROTTLE],
            deadband=deadbands.get(description.key),
        )
        for description in SENSOR_TYPES
        if description.key in config[CONF_RESOURCES]
    ]

    add_entities(sensors, True)


class ComfoConnectSensor(SensorEntity):
    """Representation of a ComfoConnect sensor."""

    _attr_should_poll = False
    entity_description: ComfoconnectSensorEntityDescription

    def __init__(
        self,
        ccb: ComfoConnectBridge,
        description: ComfoconnectSensorEntityDescription,
        throttle: float = 0,
        deadband: float | None = None,
    ) -> None:
        """Initialize the ComfoConnect sensor."""
        self._ccb = ccb
        self.entity_description = description
        self._attr_name = f"{ccb.name} {description.name}"
        self._attr_unique_id = f"{ccb.unique_id}-{description.key}"
        self._throttle = throttle
        self._deadband = deadband
        self._last_write: float | None = None
        self._pending_value: float | None = None
        self._cancel_flush: CALLBACK_TYPE | None = None
        self._flush_job = HassJob(
            self._flush, "comfoconnect sensor flush", cancel_on_shutdown=True
        )

    @override
    async def async_added_to_hass(self) -> None:
        """Register for sensor updates."""
        _LOGGER.debug(
            "Registering for sensor %s (%d)",
            self.entity_description.key,
            self.entity_description.sensor_id,
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_COMFOCONNECT_UPDATE_RECEIVED.format(
                    self.entity_description.sensor_id
                ),
                self._handle_update,
            )
        )
        self.async_on_remove(self._async_cancel_flush)
        await self.hass.async_add_executor_job(
            self._ccb.comfoconnect.register_sensor, self.entity_description.sensor_id
        )

    @callback
    def _handle_update(self, value: float) -> None:
        """Handle update callbacks, throttling state writes."""
        _LOGGER.debug(
            "Handle update for sensor %s (%d): %s",
            self.entity_description.key,
            self.entity_description.sensor_id,
            value,
        )
        new_value = round(value * self.entity_description.multiplier, 2)
        current = self._attr_native_value

        if self._last_write is None or self._throttle <= 0:
            self._async_write(new_value)
            return

        if new_value == current:
            # Back to the value already shown, nothing left to flush.
            self._pending_value = None
            self._async_cancel_flush()
            return

        elapsed = time.monotonic() - self._last_write
        big_change = (
            self._deadband is not None
            and isinstance(current, (int, float))
            and abs(new_value - current) >= self._deadband
        )
        if big_change or elapsed >= self._throttle:
            self._async_write(new_value)
            return

        # Hold the value and write the newest one when the window ends.
        self._pending_value = new_value
        if self._cancel_flush is None:
            self._cancel_flush = async_call_later(
                self.hass, self._throttle - elapsed, self._flush_job
            )

    @callback
    def _async_write(self, value: float) -> None:
        """Write a value to the state machine now."""
        self._async_cancel_flush()
        self._pending_value = None
        self._last_write = time.monotonic()
        self._attr_native_value = value
        self.async_write_ha_state()

    @callback
    def _flush(self, _now: datetime) -> None:
        """Write the newest held value at the end of the throttle window."""
        self._cancel_flush = None
        if self._pending_value is not None:
            self._async_write(self._pending_value)

    @callback
    def _async_cancel_flush(self) -> None:
        """Cancel a scheduled flush."""
        if self._cancel_flush is not None:
            self._cancel_flush()
            self._cancel_flush = None
