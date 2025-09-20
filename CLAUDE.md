# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python library for reading sensor data from serial-connected OWL Energy meters, specifically the CM 160 model. The library provides asynchronous data collection from energy meters via serial communication, designed primarily for Home Assistant integration.

## Architecture

### Core Components

- **`owlsensor/serial_cm.py`**: Main data collector class (`CMDataCollector`) that handles serial communication with OWL CM160 devices
- **`owlsensor/device.py`**: Device type definitions and data structures for supported energy meter models
- **`owlsensor/const.py`**: Protocol constants, packet IDs, and communication parameters for the OWL CM160
- **`owlsensor/__init__.py`**: Public API interface with `get_async_datacollector()` factory function

### Communication Protocol

The library implements a custom serial protocol for OWL CM160 meters:
- **Baud rate**: 250000
- **Packet types**: History data (0xa9, 0x59) and real-time data (0x51)
- **Device states**: Unknown → IdentifierReceived → TransmittingHistory → TransmittingRealtime
- **Data format**: 11-byte records with LSB byte order, current measurement at byte 8

## Development Commands

### Building
```bash
./build.sh
```
This sets UTF-8 locale, creates source distribution, and generates egg info.

### Testing and Linting
```bash
./test.sh
```
This cleans `__pycache__` directories, runs pylint on all Python files in owlsensor/, and executes pytest.

### Package Installation
```bash
pip install -e .
```
For development installation with the `pyserial-asyncio-fast>=0.13` dependency.

## Usage Pattern

The library follows an async/await pattern:

1. Create collector: `CMDataCollector(port, SUPPORTED_SENSORS["CM160"])`
2. Connect: `await collector.connect()`
3. Read data: `await collector.read_data()` returns `{'Current': float_value}`

See `cmsensor_demo.py` for a complete working example that continuously reads from `/dev/ttyUSB0`.

## Key Dependencies

- **pyserial-asyncio-fast**: Fast async serial communication (>=0.16)
- **Standard library**: asyncio, logging, dataclasses, enum

## Serial Device Configuration

Devices use `/dev/ttyUSB0` on Linux or `COM4` on Windows. The library handles automatic connection when `read_data()` is called, discarding historical data and focusing on real-time transmissions only.

## Recent Improvements (v0.4.3)

### Reliability Enhancements
- **Connection retry logic**: Added 5-second backoff to prevent connection spam
- **Resource cleanup**: Proper async context manager support with `async with`
- **Error handling**: Enhanced exception handling and logging consistency
- **Buffer protection**: Improved buffer parsing with encoding error handling

### Code Quality
- **Dependencies**: Updated to pyserial-asyncio-fast>=0.16 (latest)
- **Lint compliance**: Fixed trailing whitespace, imports, and variable naming
- **Method additions**: Added `disconnect()` method for explicit cleanup

### Usage Pattern (Updated)
```python
# Recommended: Using context manager
async with cm.CMDataCollector(port, cm.SUPPORTED_SENSORS["CM160"]) as sensor:
    data = await sensor.read_data()
    print(data)  # {'Current': 4.1}

# Traditional: Manual cleanup
sensor = cm.CMDataCollector(port, cm.SUPPORTED_SENSORS["CM160"])
await sensor.connect()
data = await sensor.read_data()
await sensor.disconnect()  # Important for cleanup
```