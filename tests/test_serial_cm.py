"""Tests for owlsensor.serial_cm."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from owlsensor.serial_cm import CMDataCollector, DeviceState, OWL_CM160
from owlsensor.const import (
    CURRENT,
    PACKET_ID_HISTORY,
    PACKET_ID_HISTORY_DATA,
    PACKET_ID_REALTIME,
)

CONFIG = OWL_CM160


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_writer():
    w = MagicMock()
    w.drain = AsyncMock()
    w.wait_closed = AsyncMock()
    return w


def _make_collector():
    """CMDataCollector with a pre-wired mock connection."""
    c = CMDataCollector("/dev/ttyUSB0", CONFIG)
    c.writer = _make_writer()
    c.reader = AsyncMock()
    c.connected = True
    return c


def _realtime_packet(current_raw: int) -> bytearray:
    """11-byte 0x51 packet with LSB-encoded current_raw at bytes 8–9."""
    buf = bytearray(11)
    buf[0] = PACKET_ID_REALTIME
    buf[8] = current_raw & 0xFF
    buf[9] = (current_raw >> 8) & 0xFF
    return buf


def _history_id_packet(text: str = "IDTCMV001") -> bytearray:
    """11-byte 0xa9 packet whose payload (bytes 1–10) holds *text*."""
    buf = bytearray(11)
    buf[0] = PACKET_ID_HISTORY
    encoded = text.encode("cp850")[:10]
    buf[1 : 1 + len(encoded)] = encoded
    return buf


def _historical_data_packet(
    year: int, month: int, day: int, hour: int, minute: int, current_raw: int
) -> bytearray:
    """11-byte 0x59 packet with a correct checksum."""
    buf = bytearray(11)
    buf[0] = PACKET_ID_HISTORY_DATA
    buf[1] = year - 2000
    buf[2] = month & 0x0F
    buf[3] = day
    buf[4] = hour
    buf[5] = minute
    buf[8] = current_raw & 0xFF
    buf[9] = (current_raw >> 8) & 0xFF
    buf[10] = sum(buf[0:10]) & 0xFF
    return buf


# ---------------------------------------------------------------------------
# parse_buffer
# ---------------------------------------------------------------------------


class TestParseBuffer:
    def test_lsb_raw_100_gives_7_amps(self):
        # 100 * 0.07 = 7.0
        c = _make_collector()
        assert c.parse_buffer(_realtime_packet(100))[CURRENT] == pytest.approx(7.0, abs=0.05)

    def test_lsb_raw_256(self):
        # 256 * 0.07 = 17.92 → rounds to 17.9
        c = _make_collector()
        assert c.parse_buffer(_realtime_packet(256))[CURRENT] == pytest.approx(17.9, abs=0.05)

    def test_lsb_raw_zero(self):
        c = _make_collector()
        assert c.parse_buffer(_realtime_packet(0))[CURRENT] == pytest.approx(0.0)

    def test_result_is_rounded_to_one_decimal(self):
        c = _make_collector()
        result = c.parse_buffer(_realtime_packet(100))
        # round() to 1 dp means at most one digit after the dot
        assert result[CURRENT] == round(result[CURRENT], 1)


# ---------------------------------------------------------------------------
# parse_packet
# ---------------------------------------------------------------------------


class TestParsePacket:
    @pytest.mark.asyncio
    async def test_realtime_returns_current(self):
        c = _make_collector()
        result = await c.parse_packet(_realtime_packet(100))
        assert result is not None
        assert result[CURRENT] == pytest.approx(7.0, abs=0.05)

    @pytest.mark.asyncio
    async def test_realtime_sets_state(self):
        c = _make_collector()
        await c.parse_packet(_realtime_packet(50))
        assert c.device_state == DeviceState.TransmittingRealtime

    @pytest.mark.asyncio
    async def test_realtime_after_history_marks_complete(self):
        c = _make_collector()
        c.device_state = DeviceState.TransmittingHistory
        await c.parse_packet(_realtime_packet(50))
        assert c._historical_complete is True

    @pytest.mark.asyncio
    async def test_history_id_reply_sets_device_found(self):
        c = _make_collector()
        result = await c.parse_packet(_history_id_packet("IDTCMV001"))
        assert result is None
        assert c.device_found is True
        assert c.device_state == DeviceState.IdentifierReceived

    @pytest.mark.asyncio
    async def test_history_id_reply_sends_start_request(self):
        c = _make_collector()
        await c.parse_packet(_history_id_packet("IDTCMV001"))
        c.writer.write.assert_called()

    @pytest.mark.asyncio
    async def test_history_wait_sends_continue(self):
        c = _make_collector()
        c.device_found = True
        await c.parse_packet(_history_id_packet("IDTWAITPCR"))
        c.writer.write.assert_called()

    @pytest.mark.asyncio
    async def test_history_wait_ignored_before_device_found(self):
        c = _make_collector()
        c.device_found = False
        await c.parse_packet(_history_id_packet("IDTWAITPCR"))
        c.writer.write.assert_not_called()

    @pytest.mark.asyncio
    async def test_historical_data_stores_record(self):
        c = _make_collector()
        c.device_found = True
        await c.parse_packet(_historical_data_packet(2024, 5, 15, 14, 30, 100))
        assert c.device_state == DeviceState.TransmittingHistory
        assert len(c._historical_data) == 1

    @pytest.mark.asyncio
    async def test_wrong_buffer_length_returns_none(self):
        c = _make_collector()
        assert await c.parse_packet(bytearray(5)) is None

    @pytest.mark.asyncio
    async def test_multiple_realtime_packets_accumulate_last(self):
        c = _make_collector()
        await c.parse_packet(_realtime_packet(100))
        result = await c.parse_packet(_realtime_packet(200))
        assert result is not None
        assert result[CURRENT] == pytest.approx(round(200 * 0.07, 1), abs=0.05)


# ---------------------------------------------------------------------------
# _parse_historical_packet
# ---------------------------------------------------------------------------


class TestParseHistoricalPacket:
    def test_valid_packet_timestamp_and_current(self):
        c = _make_collector()
        buf = _historical_data_packet(2024, 5, 15, 14, 30, 100)
        result = c._parse_historical_packet(buf)
        assert result is not None
        assert result["timestamp"] == datetime(2024, 5, 15, 14, 30)
        assert result["current"] == pytest.approx(7.0, abs=0.05)

    def test_corrupted_checksum_returns_none(self):
        c = _make_collector()
        buf = _historical_data_packet(2024, 5, 15, 14, 30, 100)
        buf[10] = (buf[10] + 1) & 0xFF
        assert c._parse_historical_packet(buf) is None

    def test_month_13_returns_none(self):
        c = _make_collector()
        buf = _historical_data_packet(2024, 13, 15, 14, 30, 100)
        assert c._parse_historical_packet(buf) is None

    def test_hour_25_returns_none(self):
        c = _make_collector()
        buf = _historical_data_packet(2024, 5, 15, 25, 0, 100)
        assert c._parse_historical_packet(buf) is None

    def test_minute_60_returns_none(self):
        c = _make_collector()
        buf = _historical_data_packet(2024, 5, 15, 10, 60, 100)
        assert c._parse_historical_packet(buf) is None

    def test_wrong_length_returns_none(self):
        c = _make_collector()
        assert c._parse_historical_packet(bytearray(5)) is None

    def test_boundary_dates_accepted(self):
        c = _make_collector()
        buf = _historical_data_packet(2024, 12, 31, 23, 59, 50)
        result = c._parse_historical_packet(buf)
        assert result is not None
        assert result["timestamp"] == datetime(2024, 12, 31, 23, 59)


# ---------------------------------------------------------------------------
# connect (serialx mocked out)
# ---------------------------------------------------------------------------


class TestConnect:
    @pytest.mark.asyncio
    async def test_connect_success(self):
        c = CMDataCollector("/dev/ttyUSB0", CONFIG)
        with patch("serial_asyncio_fast.open_serial_connection", new_callable=AsyncMock) as mock_open:
            mock_open.return_value = (AsyncMock(), _make_writer())
            result = await c.connect()
        assert result is True
        assert c.connected is True

    @pytest.mark.asyncio
    async def test_connect_oserror_returns_false(self):
        c = CMDataCollector("/dev/ttyUSB0", CONFIG)
        with patch("serial_asyncio_fast.open_serial_connection", new_callable=AsyncMock) as mock_open:
            mock_open.side_effect = OSError("no device")
            result = await c.connect()
        assert result is False
        assert c.connected is False

    @pytest.mark.asyncio
    async def test_connect_timeout_returns_false(self):
        c = CMDataCollector("/dev/ttyUSB0", CONFIG)
        with patch("serial_asyncio_fast.open_serial_connection", new_callable=AsyncMock) as mock_open:
            mock_open.side_effect = TimeoutError()
            result = await c.connect()
        assert result is False
        assert c.connected is False

    @pytest.mark.asyncio
    async def test_connect_serial_exception_returns_false(self):
        from serial import SerialException
        c = CMDataCollector("/dev/ttyUSB0", CONFIG)
        with patch("serial_asyncio_fast.open_serial_connection", new_callable=AsyncMock) as mock_open:
            mock_open.side_effect = SerialException("backend error")
            result = await c.connect()
        assert result is False
        assert c.connected is False

    @pytest.mark.asyncio
    async def test_connect_calls_open_with_correct_baudrate(self):
        c = CMDataCollector("/dev/ttyUSB0", CONFIG)
        with patch("serial_asyncio_fast.open_serial_connection", new_callable=AsyncMock) as mock_open:
            mock_open.return_value = (AsyncMock(), _make_writer())
            await c.connect()
        _, kwargs = mock_open.call_args
        assert kwargs.get("baudrate") == 250000


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_clears_connected(self):
        c = _make_collector()
        await c.disconnect()
        assert c.connected is False

    @pytest.mark.asyncio
    async def test_disconnect_clears_writer(self):
        c = _make_collector()
        await c.disconnect()
        assert c.writer is None

    @pytest.mark.asyncio
    async def test_context_manager_disconnects_on_exit(self):
        c = CMDataCollector("/dev/ttyUSB0", CONFIG)
        with patch("serial_asyncio_fast.open_serial_connection", new_callable=AsyncMock) as mock_open:
            mock_open.return_value = (AsyncMock(), _make_writer())
            async with c:
                assert c.connected is True
        assert c.connected is False


# ---------------------------------------------------------------------------
# state accessors
# ---------------------------------------------------------------------------


class TestAccessors:
    def test_get_current_not_connected(self):
        c = CMDataCollector("/dev/ttyUSB0", CONFIG)
        assert c.get_current() is None

    def test_get_current_no_data(self):
        c = _make_collector()
        c._data = None
        assert c.get_current() is None

    def test_get_current_with_data(self):
        c = _make_collector()
        c._data = {CURRENT: 4.9}
        assert c.get_current() == pytest.approx(4.9)

    def test_supported_values_includes_current(self):
        assert CURRENT in _make_collector().supported_values()

    def test_get_device_state_info_keys(self):
        info = _make_collector().get_device_state_info()
        assert info.keys() == {"state", "historical_count", "historical_complete", "connected", "device_found"}

    def test_is_historical_data_complete_initially_false(self):
        assert _make_collector().is_historical_data_complete() is False

    def test_clear_historical_data(self):
        c = _make_collector()
        c._historical_data.append({"timestamp": datetime(2024, 1, 1, 0, 0), "current": 1.0})
        c.clear_historical_data()
        assert c.get_historical_data() == []

    def test_get_historical_data_returns_copy(self):
        c = _make_collector()
        c._historical_data.append({"timestamp": datetime(2024, 1, 1, 0, 0), "current": 1.0})
        data = c.get_historical_data()
        data.clear()
        assert len(c._historical_data) == 1  # original unaffected
