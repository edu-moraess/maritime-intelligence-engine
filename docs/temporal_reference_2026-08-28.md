# Temporal semantics reference

Source: [AISStream developer documentation](https://aisstream.io/documentation), consulted 2026-08-28.

The official PositionReport schema describes `Timestamp` as an **AIS UTC-second timestamp** and does not provide a complete observation datetime in the PositionReport payload. The official example PositionReport used by the service contains `MetaData` with MMSI, ShipName and last known position, while the PositionReport contains the position fields and `Timestamp`; the example does not establish `MetaData.time_utc` as vessel observation time.

The application therefore keeps the following semantics:

- `received_at`: timezone-aware UTC instant when the MIE receives/processes the frame.
- `ais_timestamp_second`: the AIS UTC second within the minute, retained as an integer only; values outside 0–59 are treated as unavailable/special and are not converted to a datetime.
- `observed_at`: `None` unless a future trusted source supplies an absolute observation datetime.
- `gateway_time`: not added because the current official payload contract used by the application does not establish a trustworthy absolute provider timestamp for the report.
- `latency`: unavailable until two comparable absolute timestamps exist; the former modulo-60 calculation is not a network-latency measure.

The official documentation also states that real-time stream messages are event-driven and that service/network/client conditions affect delivery, reinforcing that receive time and vessel observation time must not be conflated.
