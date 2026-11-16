# Zehnder ComfoAir Q (throttled)

A copy of the Home Assistant core
[`comfoconnect`](https://www.home-assistant.io/integrations/comfoconnect) integration
(taken from core `2026.11.1`) with throttled sensor updates.

The ComfoConnect bridge pushes every small change. Fan RPM and airflow jitter by a
few units several times a second, and the core integration writes each one to the state
machine. Every write goes to every open dashboard over the websocket, and from there to the
recorder and any derived sensors (Riemann sum, utility meters). With all sensors
enabled that is about 3 state writes per second.

This version writes each sensor **at most once per `throttle` seconds**. The newest
value is always written when the window ends, so nothing is lost. A change of at least the sensor's
**deadband** skips the wait and is written right away, so real changes (switching the fan
mode) still show up immediately. The update handler also runs on the event loop
instead of a worker thread.

It uses the same domain (`comfoconnect`), so it replaces the core integration. Entity
IDs, unique IDs and history stay the same. Home Assistant logs a warning at startup
that a custom integration overrides a core one. That is expected.

## Install

1. Marketplace (HACS) > Custom repositories > add `https://github.com/alhafoudh/ha-comfoconnect`,
   type Integration.
2. Install it and restart Home Assistant.

## Configuration

The existing YAML keeps working. Two optional keys are added to the sensor platform:

```yaml
comfoconnect:
  host: 192.168.x.x

sensor:
  - platform: comfoconnect
    resources:
      - supply_fan_speed
      - exhaust_fan_speed
      - power_usage
      # ...
    throttle: 60          # seconds (default 60), max one write per sensor per window; 0 = upstream behaviour
    deadband:             # optional per-sensor overrides; a change this large is written immediately
      supply_fan_speed: 50
      power_usage: 3
```

Default deadbands (override any of them under `deadband:`):

| Sensor | Deadband |
|---|---|
| `supply_fan_speed`, `exhaust_fan_speed` | 50 rpm |
| `air_flow_supply`, `air_flow_exhaust` | 10 m³/h |
| `power_usage`, `preheater_power_usage` | 3 W |

Sensors without a deadband (temperatures, humidity, ...) only use the throttle window.

## License

Apache 2.0, same as Home Assistant core (see `LICENSE.md`).
