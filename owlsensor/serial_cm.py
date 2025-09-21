"""
Reading data from particulate matter sensors with a serial interface.
"""

import time
import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Optional
from serial import EIGHTBITS, PARITY_NONE, STOPBITS_ONE
import serial_asyncio_fast

from .const import (
    ID_REPLY, ID_WAIT_HISTORY, CONTINUE_REQUEST, START_REQUEST,
    PACKET_ID_HISTORY, PACKET_ID_HISTORY_DATA, PACKET_ID_REALTIME,
    RECORD_LENGTH, CURRENT, BAUD_RATE, BYTE_ORDER, LSB, MSB,
    MULTIPLIER, TIMEOUT
)
from enum import Enum


# Owl CM160 settings
OWL_CM160 = {
    RECORD_LENGTH: 11,
    CURRENT: 8,
    BAUD_RATE: 250000,
    BYTE_ORDER: LSB,
    MULTIPLIER: 0.07,
    TIMEOUT: 30
}

SUPPORTED_SENSORS = {
    "CM160": OWL_CM160
}

class DeviceState(Enum):
    Unknown = 0
    IdentifierReceived = 1
    TransmittingHistory = 2
    TransmittingRealtime = 3

CMVALS=[CURRENT]

LOGGER = logging.getLogger(__name__)


class CMDataCollector():
    """Controls the serial interface and reads data from the sensor."""

# pylint: disable=too-many-instance-attributes
    def __init__(self,
                 serialdevice,
                 configuration,
                 scan_interval=0):
        """Initialize the data collector based on the given parameters."""

        self.record_length = configuration[RECORD_LENGTH]
        self.byte_order = configuration[BYTE_ORDER]
        self.multiplier = configuration[MULTIPLIER]
        self.timeout = configuration[TIMEOUT]
        self.scan_interval = scan_interval
        self.listeners = []
        self.sensordata = {}
        self.config = configuration
        self._data = None
        self.last_poll = None
        self.device_state = DeviceState.Unknown
        self.device_found = False
        self.serialdevice = serialdevice
        self.reader = None
        self.writer = None
        self.baudrate = configuration[BAUD_RATE]
        self.connected = False
        self.update_task = None
        self._last_connect_attempt = 0
        self._connect_retry_interval = 5  # seconds
        self._historical_data: List[Dict] = []
        self._historical_complete = False
        self._last_historical_packet_time = None
        self._historical_timeout = 90.0  # seconds - timeout for historical data completion
        self._read_lock = asyncio.Lock()

    async def disconnect(self):
        """Disconnect and cleanup resources."""
        if self.update_task is not None:
            try:
                self.update_task.cancel()
                await self.update_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                LOGGER.warning("Exception while cancelling update task: %s", e)
            finally:
                self.update_task = None

        if self.writer is not None:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception as e:
                LOGGER.warning("Exception while closing writer: %s", e)
            finally:
                self.writer = None
                self.reader = None

        self.connected = False

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()

    async def connect(self) -> bool:
        """Establish the serial connection asynchronously."""
        self.connected = False
        try:
            self.reader, self.writer = await serial_asyncio_fast.open_serial_connection(
                url=self.serialdevice,
                baudrate=self.baudrate,
                parity=PARITY_NONE,
                bytesize=EIGHTBITS,
                stopbits=STOPBITS_ONE,
                timeout=1,
                write_timeout=1,
                exclusive=False
            )
        except Exception as ex:
            LOGGER.warning("Failed to connect: %s", ex)
            self.connected = False
            return False

        self.connected = True

        # Stimulate the device
        await self.send_data(CONTINUE_REQUEST)

        if self.update_task is not None:
            try:
                self.update_task.cancel()
                self.update_task = None
            except Exception as e:
                LOGGER.warning("Exception while cancelling update Task: %s", e)

        if self.scan_interval > 0:
            self.update_task = asyncio.create_task(self.refresh())

        LOGGER.info("Connection to %s successful", self.serialdevice)
        return True

    async def refresh(self):
        """Asynchronous background refreshing task."""
        while True:
            try:
                await self.read_data()
                await asyncio.sleep(self.scan_interval)
            except asyncio.CancelledError:
                LOGGER.info("Refresh task cancelled")
                break
            except Exception as e:
                LOGGER.warning("Refresh loop exception: %s", e)
                self.connected = False
                await asyncio.sleep(self.scan_interval)

    async def send_data(self, data: bytes) -> None:
        LOGGER.debug("-> %s", ''.join(format(x, '02x') for x in data))
        try:
            self.writer.write(data)
            await self.writer.drain()
        except Exception as e:
            LOGGER.warning("Error while writing: %s", e)
            self.connected = False

    async def get_packet(self) -> bytearray:
        sbuf = bytearray()
        """Read from the serial port until a valid packet is formed."""
        starttime = asyncio.get_event_loop().time()
        valid_start_bytes = {PACKET_ID_HISTORY, PACKET_ID_HISTORY_DATA, PACKET_ID_REALTIME}

        while len(sbuf) < self.record_length:
            elapsed = asyncio.get_event_loop().time() - starttime
            if elapsed > self.timeout:
                LOGGER.error("Timeout waiting for data")
                return bytearray()

            try:
                data_bytes = await self.reader.readexactly(1)
                if len(data_bytes) == 0:
                    LOGGER.warning("Timeout on data on serial")
        try:
            # 1. Synchronize by finding a valid start byte
            while True:
                elapsed = asyncio.get_event_loop().time() - starttime
                if elapsed > self.timeout:
                    LOGGER.warning("Timeout waiting for a valid packet start byte.")
                    return bytearray()
                sbuf += data_bytes
            except asyncio.IncompleteReadError:
                LOGGER.warning("Timeout on data on serial")
                return bytearray()
                start_byte_data = await self.reader.readexactly(1)
                if start_byte_data[0] in valid_start_bytes:
                    break  # Found start byte, exit sync loop
                else:
                    LOGGER.debug("Discarding unexpected byte for sync: %02x", start_byte_data[0])

        return sbuf
            # 2. Read the rest of the packet
            sbuf = bytearray(start_byte_data)
            bytes_to_read = self.record_length - 1
            remaining_bytes = await self.reader.readexactly(bytes_to_read)
            sbuf.extend(remaining_bytes)
            return sbuf

        except asyncio.IncompleteReadError:
            LOGGER.warning("Timeout on serial read.")
            return bytearray()
        except Exception as e:
            LOGGER.error("Unexpected error while reading packet: %s", e)
            self.connected = False
            return bytearray()

    async def parse_packet(self, buffer: bytearray) -> dict | None:
        if len(buffer) != self.record_length:
            LOGGER.error("Wrong buffer length: %d", len(buffer))
            return

        LOGGER.debug("<- %s", ''.join(format(x, '02x') for x in buffer))
        try:
            str_buffer = buffer[1:11].decode("cp850", errors='replace')
        except (UnicodeDecodeError, IndexError) as e:
            LOGGER.error("Failed to decode buffer: %s", e)
            return None

        if buffer[0] == PACKET_ID_HISTORY:
            if ID_REPLY in str_buffer:
                LOGGER.info("Device found (%s)", str_buffer)
                self.device_found = True
                self.device_state = DeviceState.IdentifierReceived
                # This is the initial "history available" packet.
                # We request the device to start sending.
                await self.send_data(START_REQUEST)
            elif ID_WAIT_HISTORY in str_buffer:
                # This is a "wait" packet during history transmission.
                # The device is waiting for us to acknowledge. Send CONTINUE.
                if self.device_found:
                    await self.send_data(CONTINUE_REQUEST)
                else:
                    LOGGER.warning("Received WAIT packet before device was identified. Ignoring.")
        elif buffer[0] == PACKET_ID_REALTIME:
            LOGGER.info("Realtime data received")
            # Mark historical data as complete when switching to realtime
            if self.device_state == DeviceState.TransmittingHistory:
                self._historical_complete = True
                LOGGER.info("Historical data collection complete. %d records collected.",
                           len(self._historical_data))
            self.device_state = DeviceState.TransmittingRealtime
            res = self.parse_buffer(buffer)
            return res
        elif buffer[0] == PACKET_ID_HISTORY_DATA:
            self.device_state = DeviceState.TransmittingHistory
            historical_data = self._parse_historical_packet(buffer)
            if historical_data:
                self._historical_data.append(historical_data)
                LOGGER.debug("Historical data: %s", historical_data)
                self._last_historical_packet_time = asyncio.get_event_loop().time()

        # Check for historical data completion based on timeout
        if (self.device_state == DeviceState.TransmittingHistory and
            not self._historical_complete and
            self._last_historical_packet_time is not None):

            current_time = asyncio.get_event_loop().time()
            if current_time - self._last_historical_packet_time > self._historical_timeout:
                LOGGER.info("Historical data collection complete due to timeout. %d records.",
                           len(self._historical_data))
                self._historical_complete = True
                self.device_state = DeviceState.TransmittingRealtime

        return None

    async def read_data(self) -> dict | None:
        """Read data from the serial interface asynchronously."""

        async with self._read_lock:
            if not self.connected:
                current_time = time.time()
                if current_time - self._last_connect_attempt < self._connect_retry_interval:
                    return None

                self._last_connect_attempt = current_time
                if not await self.connect():
                    return None

            mytime = asyncio.get_event_loop().time()
            if (self.last_poll is not None) and \
               (mytime - self.last_poll) <= 15 and \
               self._data is not None:
                return self._data

            res = None
            finished = False

            while not finished:
                try:
                    packet = await self.get_packet()
                    if not packet:
                        LOGGER.debug("Failed to get packet (timeout).")
                        return None

                    result = await self.parse_packet(packet)
                    if result is not None:
                        res = result
                        finished = True
                except Exception as ex:
                    LOGGER.warning("Exception during packet read: %s", ex)
                    self.connected = False
                    return None

            # consistency check
            if res is None or res.get(CURRENT) is None or not (0.0 <= res[CURRENT] <= 100.0):
                if res is not None:
                    LOGGER.warning("Inconsistent data: %s", res)
                return None

            self._data = res
            self.last_poll = asyncio.get_event_loop().time()
            return res

    def parse_buffer(self, sbuf) -> dict:
        """Parse the buffer and return the CM values."""
        res = {}
        for pmname in CMVALS:
            offset = self.config[pmname]
            if offset is not None:
                if self.byte_order == MSB:
                    res[pmname] = sbuf[offset] * \
                        256 + sbuf[offset + 1]
                else:
                    res[pmname] = sbuf[offset + 1] * \
                        256 + sbuf[offset]

                res[pmname] = round(res[pmname] * self.multiplier, 1)

        return res

    def _parse_historical_packet(self, buffer: bytearray) -> Optional[Dict]:
        """Parse historical data packet from CM160 device."""
        if len(buffer) != self.record_length:
            return None

        try:
            # Validate checksum
            checksum = sum(buffer[0:10]) & 0xff
            if checksum != buffer[10]:
                LOGGER.warning("Invalid checksum in historical packet")
                return None

            # Extract timestamp and current data
            # Based on reference implementation: frame[1-5] = year, month, day, hour, min
            year = buffer[1] + 2000
            month = buffer[2] & 0xf  # Mask out upper bits as per reference
            day = buffer[3]
            hour = buffer[4]
            minute = buffer[5]

            # Parse current value using the common buffer parser
            parsed_values = self.parse_buffer(buffer)
            current = parsed_values.get(CURRENT)

            # Validate date/time values
            if not (1 <= month <= 12 and 1 <= day <= 31 and 0 <= hour <= 23 and 0 <= minute <= 59) or current is None:
                LOGGER.warning(
                    "Invalid data in historical packet: Y:%d M:%d D:%d H:%d m:%d C:%s",
                    year, month, day, hour, minute, current
                )
                return None

            # Create datetime object
            timestamp = datetime(year, month, day, hour, minute)

            return {
                "timestamp": timestamp,
                "current": current
            }

        except (ValueError, OverflowError) as e:
            LOGGER.warning("Error parsing historical packet: %s", e)
            return None

    def supported_values(self) -> list:
        """Returns the list of supported values for the actual device"""
        res = []
        for pmname in CMVALS:
            offset = self.config[pmname]
            if offset is not None:
                res.append(pmname)
        return res

    def get_current(self) -> float | None:
        """ Returns latest realtime current transmitted by the device """

        if not self.connected:
            return None

        if self._data is None:
            return None

        if CURRENT in self._data:
            return self._data[CURRENT]

        return None

    def get_historical_data(self) -> List[Dict]:
        """Return the collected historical data as a list of timestamped current readings.

        Returns:
            List of dictionaries with 'timestamp' (datetime) and 'current' (float) keys
        """
        return self._historical_data.copy()

    def clear_historical_data(self) -> None:
        """Clear the collected historical data buffer."""
        self._historical_data.clear()

    def is_historical_data_complete(self) -> bool:
        """Check if historical data collection is complete.

        Returns True when device transitions from TransmittingHistory to TransmittingRealtime
        """
        return self._historical_complete

    def get_device_state(self) -> str:
        """Get the current device communication state.

        Returns:
            str: Current state name
        """
        return self.device_state.name

    def get_device_state_info(self) -> dict:
        """Get detailed device state information.

        Returns:
            dict: Contains state, historical_count, historical_complete, connected
        """
        return {
            "state": self.get_device_state(),
            "historical_count": len(self._historical_data),
            "historical_complete": self._historical_complete,
            "connected": self.connected,
            "device_found": self.device_found
        }
