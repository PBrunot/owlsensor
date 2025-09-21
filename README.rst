owlsensor - Library for OWL CM 160 Energy Meter
================================================

This library lets you read sensor data from serial-connected OWL Energy meters.
It currently supports the following model:

- CM 160

Usage
=====

Create a CMDataCollector with the port name as the first argument and the OWL model as the second argument:

.. code-block:: python

    import owlsensor as cm

    # Windows
    sensor = cm.CMDataCollector("COM4", cm.SUPPORTED_SENSORS["CM160"])

    # Linux
    sensor = cm.CMDataCollector("/dev/ttyUSB0", cm.SUPPORTED_SENSORS["CM160"])

You can add several devices the same way, on different serial ports.

Connection will be called automatically by ``read_data()``:

.. code-block:: python

    # Optional explicit connection
    await sensor.connect()

    # Read data (connects automatically if needed)
    data = await sensor.read_data()

``read_data()`` returns a dictionary containing the acquired real-time value. Currently only current in amperes is returned:

.. code-block:: python

    print(await sensor.read_data())
    # Output: {'Current': 4.1}

Recommended usage with context manager for automatic cleanup:

.. code-block:: python

    import owlsensor as cm

    async with cm.CMDataCollector(port, cm.SUPPORTED_SENSORS["CM160"]) as sensor:
        data = await sensor.read_data()
        print(data)  # {'Current': 4.1}

Historical Data Collection
==========================

The CM160 device transmits historical data during initial connection. This library now captures and provides access to this historical data for Home Assistant integration.

Key Features:

* Automatic collection of historical data during device initialization
* Timestamped current readings with datetime objects
* Home Assistant compatible data structure
* Non-blocking collection with completion detection

.. code-block:: python

    import owlsensor as cm
    import asyncio

    async def collect_history():
        async with cm.CMDataCollector(port, cm.SUPPORTED_SENSORS["CM160"]) as sensor:
            # Wait for historical data collection to complete
            while not sensor.is_historical_data_complete():
                await asyncio.sleep(1)
                count = len(sensor.get_historical_data())
                print(f"Collected {count} historical records...")

            # Get all historical data
            historical_data = sensor.get_historical_data()

            for record in historical_data:
                timestamp = record["timestamp"]  # datetime object
                current = record["current"]      # float (amperes)
                print(f"{timestamp.isoformat()}: {current}A")

API Methods for Historical Data
===============================

``get_historical_data() -> List[Dict]``
    Returns collected historical data as a list of dictionaries.
    Each dictionary contains:

    * ``timestamp``: Python datetime object
    * ``current``: Float value in amperes

``is_historical_data_complete() -> bool``
    Returns True when historical data collection is complete.
    This occurs when the device transitions from TransmittingHistory to TransmittingRealtime state.

``clear_historical_data() -> None``
    Clears the collected historical data from memory.

Data Structure for Home Assistant
=================================

Historical data is provided in a format optimized for Home Assistant processing:

.. code-block:: python

    [
        {
            "timestamp": datetime(2024, 1, 15, 10, 30, 0),
            "current": 4.2
        },
        {
            "timestamp": datetime(2024, 1, 15, 10, 35, 0),
            "current": 3.8
        }
        # ... more records
    ]

* Timestamps are timezone-naive datetime objects in device local time
* Current values are in amperes (float)
* Data is ordered chronologically
* Typical collection contains several days to weeks of 5-minute interval readings

Home Assistant Integration Guidelines
====================================

For Home Assistant component developers:

1. **Connection**: Use context manager for automatic cleanup
2. **Historical Collection**: Wait for ``is_historical_data_complete()`` before processing
3. **Data Processing**: Use ``get_historical_data()`` to retrieve all timestamped readings
4. **Memory Management**: Call ``clear_historical_data()`` after processing to free memory
5. **Real-time Data**: Use ``read_data()`` for ongoing current readings

.. code-block:: python

    # Example Home Assistant integration pattern
    async def setup_cm160_sensor(port):
        async with cm.CMDataCollector(port, cm.SUPPORTED_SENSORS["CM160"]) as sensor:
            # Collect historical data for Home Assistant history
            while not sensor.is_historical_data_complete():
                await asyncio.sleep(1)

            historical_data = sensor.get_historical_data()

            # Process historical data for HA database
            for record in historical_data:
                await hass.async_add_job(
                    process_historical_reading,
                    record["timestamp"],
                    record["current"]
                )

            # Clear historical data to free memory
            sensor.clear_historical_data()

            # Continue with real-time readings
            while True:
                current_data = await sensor.read_data()
                # Process real-time data...

Device State Monitoring
=======================

The library now provides access to the internal communication state machine for debugging and monitoring:

``get_device_state() -> str``
    Returns the current device communication state:

    * ``"Unknown"``: Initial state, device not yet identified
    * ``"IdentifierReceived"``: Device found and identified
    * ``"TransmittingHistory"``: Historical data transmission in progress
    * ``"TransmittingRealtime"``: Real-time data transmission active

``get_device_state_info() -> dict``
    Returns detailed state information including:

    * ``state``: Current state name
    * ``historical_count``: Number of historical records collected
    * ``historical_complete``: Boolean indicating if historical collection is done
    * ``connected``: Connection status
    * ``device_found``: Whether device has been identified

.. code-block:: python

    # Monitor device state during connection
    async with cm.CMDataCollector(port, cm.SUPPORTED_SENSORS["CM160"]) as sensor:
        while sensor.get_device_state() != "TransmittingRealtime":
            state_info = sensor.get_device_state_info()
            print(f"State: {state_info['state']}, Historical: {state_info['historical_count']}")
            await asyncio.sleep(1)

Device Behavior
===============

* Historical data transmission occurs immediately after device identification
* Historical data contains readings from device's internal memory (typically 30 days)
* Data is transmitted chronologically from oldest to newest
* Each packet contains: timestamp (year, month, day, hour, minute) and current reading
* Real-time data begins after historical transmission completes
* Device sends real-time updates approximately every 5 seconds

Bug Fixes
==========

**v0.5.1**: Fixed critical bug where CM160 device would get stuck in historical sync mode after Home Assistant reboot. The device would continuously send handshake messages without transitioning to real-time mode. This was resolved by implementing timeout-based historical data completion detection, following the reference implementation pattern. The fix ensures reliable historical-to-realtime transition and improved protocol state machine handling.