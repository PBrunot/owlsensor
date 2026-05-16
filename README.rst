owlsensor - Library for OWL CM160 Energy Meter
================================================

Python async library for reading sensor data from the OWL Energy Monitor CM160 via serial port.
Supports real-time current readings and full historical data collection.

**Current version**: 0.7.2 | **Python**: 3.10+ | **Dependency**: ``serialx>=1.7.2``

Supported devices:

- OWL CM160 (250 000 baud, USB-serial)

Installation
============

.. code-block:: bash

    pip install owlsensor

Requires ``serialx>=1.7.2``, which supports non-POSIX baud rates (250 000 baud) on all platforms.

Quick Start
===========

.. code-block:: python

    import asyncio
    import owlsensor as cm

    async def main():
        port = "/dev/ttyUSB0"   # Linux; use "COM4" on Windows

        async with cm.CMDataCollector(port, cm.SUPPORTED_SENSORS["CM160"]) as sensor:
            data = await sensor.read_data()
            print(data)  # {'Current': 4.1}

    asyncio.run(main())

``read_data()`` waits for the device to finish its historical data burst, then returns the first
real-time packet. Subsequent calls within 15 seconds return the cached value.

Constructor
===========

.. code-block:: python

    cm.CMDataCollector(serialdevice, configuration, scan_interval=0)

Parameters:

- **serialdevice** – Serial port path (``"/dev/ttyUSB0"``, ``"COM4"``, …)
- **configuration** – Device config dict; use ``cm.SUPPORTED_SENSORS["CM160"]``
- **scan_interval** – If > 0, starts a background asyncio task that calls ``read_data()``
  every *scan_interval* seconds. Useful when you need historical data to arrive passively
  while your code does other work. Default: 0 (no background task).

Convenience factory:

.. code-block:: python

    sensor = cm.get_async_datacollector("/dev/ttyUSB0", "CM160", scan_interval_s=30)

API Reference
=============

Connection
----------

``await sensor.connect() -> bool``
    Open the serial port and send the initial stimulation byte to the device.
    Returns ``True`` on success. Called automatically by ``read_data()`` and the context manager.

``await sensor.disconnect()``
    Cancel the background refresh task (if running) and close the serial port.

``async with cm.CMDataCollector(...) as sensor``
    Preferred pattern — calls ``connect()`` on entry and ``disconnect()`` on exit.

Real-time Data
--------------

``await sensor.read_data() -> dict | None``
    Returns the latest real-time packet from the device, or ``None`` on timeout/error.
    Results are cached for 15 seconds (the device's natural update interval).

    Return value (real-time):

    .. code-block:: python

        {'Current': 4.1}   # key is 'Current' with a capital C; value is amperes (float)

``sensor.get_current() -> float | None``
    Synchronous convenience wrapper — returns the last received current value in amperes,
    or ``None`` if not yet connected or no data received.

Historical Data
---------------

``sensor.get_historical_data() -> list[dict]``
    Returns a copy of all historical records collected during device initialisation.

    Each record:

    .. code-block:: python

        {
            'timestamp': datetime(2024, 1, 15, 10, 30),  # timezone-naive, device local time
            'current':   3.8                             # amperes (float); key is lowercase
        }

    .. note::
        The historical data key is ``'current'`` (lowercase), while the real-time key returned
        by ``read_data()`` is ``'Current'`` (capital C). This reflects the internal packet
        parsers and is intentional.

``sensor.is_historical_data_complete() -> bool``
    Returns ``True`` once the device transitions from history-transmission mode to real-time
    mode, **or** after no new history packet arrives for 90 seconds (timeout fallback).

``sensor.clear_historical_data() -> None``
    Frees the in-memory historical buffer. Call after you have processed the data.

Historical Data Collection
==========================

The CM160 transmits its full internal memory (typically 30 days at 5-minute intervals) during
the handshake before switching to real-time mode.  Use ``scan_interval`` so data arrives in the
background while you poll for completion:

.. code-block:: python

    import asyncio
    import owlsensor as cm

    async def collect_history(port):
        async with cm.CMDataCollector(
            port, cm.SUPPORTED_SENSORS["CM160"], scan_interval=1
        ) as sensor:

            # Wait for all historical packets
            timeout, start = 300, asyncio.get_event_loop().time()
            while not sensor.is_historical_data_complete():
                await asyncio.sleep(1)
                count = len(sensor.get_historical_data())
                print(f"\rCollected {count} records...", end="", flush=True)
                if asyncio.get_event_loop().time() - start > timeout:
                    print("\nTimeout")
                    break

            records = sensor.get_historical_data()
            print(f"\n{len(records)} historical records:")
            for r in records[-5:]:
                print(f"  {r['timestamp'].isoformat()}: {r['current']} A")

            # Free memory after processing
            sensor.clear_historical_data()

            # Now read real-time data
            data = await sensor.read_data()
            print(f"Current reading: {data}")

    asyncio.run(collect_history("/dev/ttyUSB0"))

Device State Monitoring
=======================

``sensor.get_device_state() -> str``
    Returns the current state of the protocol state machine:

    - ``"Unknown"`` — Initial state; device not yet identified
    - ``"IdentifierReceived"`` — Device handshake received
    - ``"TransmittingHistory"`` — Historical packets flowing
    - ``"TransmittingRealtime"`` — Real-time mode active

``sensor.get_device_state_info() -> dict``
    Returns a snapshot of all state fields:

    .. code-block:: python

        {
            'state':              'TransmittingRealtime',
            'historical_count':   1234,
            'historical_complete': True,
            'connected':          True,
            'device_found':       True,
        }

Example — wait until real-time mode:

.. code-block:: python

    async with cm.CMDataCollector(port, cm.SUPPORTED_SENSORS["CM160"]) as sensor:
        while sensor.get_device_state() != "TransmittingRealtime":
            info = sensor.get_device_state_info()
            print(f"State: {info['state']}, records: {info['historical_count']}")
            await asyncio.sleep(1)

Device Protocol Notes
=====================

- The CM160 communicates at **250 000 baud** (non-POSIX rate; requires ``serialx``).
- On first connection the device sends all historical records before switching modes.
- Historical data is transmitted chronologically (oldest first).
- Each historical packet contains: year, month, day, hour, minute, and current reading.
- Real-time packets arrive approximately every **15 seconds**.
- The library retries the serial connection automatically after a 5-second cooldown if
  ``read_data()`` is called while disconnected.
- ``read_timeout=0`` is used on the serial port so the asyncio event loop can detect
  inter-packet gaps without blocking (see v0.7.2 changelog below).

Reconnect / Auto-retry
======================

If the serial connection drops, ``read_data()`` detects the failure and attempts to reconnect
automatically, subject to a 5-second minimum retry interval. No manual intervention is required.

Running the Demo
================

.. code-block:: bash

    python cmsensor_demo.py          # defaults to /dev/ttyUSB0
    python historical_data_example.py

Changelog
=========

v0.7.2
    Fixed ``read_timeout=0`` on the serial port to prevent spurious EOF errors caused by
    inter-packet gaps when using ``serialx``.

v0.7.1
    Fixed ``CONTINUE_REQUEST`` and ``START_REQUEST`` constants to be ``bytes`` objects
    (were plain ``int`` values, which broke the ``serialx 1.7.2+`` write API).

v0.7.0
    Migrated from ``pyserial-asyncio-fast`` to ``serialx>=1.7.2``, which correctly handles
    the non-POSIX 250 000 baud rate required by the CM160 on all platforms.

v0.6.1
    Reverted to ``pyserial-asyncio-fast`` after discovering a 250 000 baud bug in early
    ``serialx`` releases.

v0.6.0
    First migration attempt to ``serialx``.

v0.5.9
    Security hardening.

v0.5.8 / v0.5.7 / v0.5.6
    Serial communication reliability fixes; concurrency bugfix (async read lock).

v0.5.5 / v0.5.4
    Timeout increase; general bugfixes.

v0.5.3 / v0.5.2
    Critical fix for the ``IDTWAITPCR`` handshake protocol bug that caused the device to
    loop indefinitely without transitioning to real-time mode.

v0.5.1
    Fixed CM160 historical sync getting stuck after Home Assistant reboot.
    Introduced timeout-based historical-completion detection.

v0.5.0
    Added historical data collection (``get_historical_data()``, ``is_historical_data_complete()``,
    ``clear_historical_data()``).
    Introduced device state API (``get_device_state()``, ``get_device_state_info()``).

License
=======

MIT — see ``LICENSE``.
