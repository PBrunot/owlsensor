"""
Reading data from particulate matter sensors with a serial interface.
"""
import time
import threading
import logging

import serial

STARTBLOCK = "SB"
RECORD_LENGTH = "RL"
# Ofsets of the PM data (always 2 byte)
PM_1_0 = "1"
PM_2_5 = "2.5"
PM_10 = "10"
BAUD_RATE = "BAUD"
BYTE_ORDER = "BO",
LSB = "lsb"
MSB = "msb"
DTR_ON = "DTR"
DTR_OFF = "NOT_DTR"
MULTIPLIER = "MP"
TIMEOUT = "TO"

# Owl CM160 settings
OWL_CM160 = {
    "TheOWL": "CM160",
    STARTBLOCK: bytes([0x42, 0x4d, 0x00, 0x14]),
    RECORD_LENGTH: 24,
    PM_1_0: 10,
    PM_2_5: 12,
    PM_10: 14,
    BAUD_RATE: 250000,
    BYTE_ORDER: MSB,
    MULTIPLIER: 1,
    TIMEOUT: 2
}

SUPPORTED_SENSORS = {
    "TheOWL,CM160": OWL_CM160
}


LOGGER = logging.getLogger(__name__)


class CMDataCollector():
    """Controls the serial interface and reads data from the sensor."""

# pylint: disable=too-many-instance-attributes
    def __init__(self,
                 serialdevice,
                 configuration,
                 power_control=DTR_ON,
                 scan_interval=0):
        """Initialize the data collector based on the given parameters."""

        self.record_length = configuration[RECORD_LENGTH]
        self.start_sequence = configuration[STARTBLOCK]
        self.byte_order = configuration[BYTE_ORDER]
        self.multiplier = configuration[MULTIPLIER]
        self.timeout = configuration[TIMEOUT]
        self.scan_interval = scan_interval
        self.listeners = []
        self.power_control = power_control
        self.sensordata = {}
        self.config = configuration
        self.data = None
        self.last_poll = None
        self.start_func = None
        self.stop_func = None

        self.ser = serial.Serial(port=serialdevice,
                                 baudrate=configuration[BAUD_RATE],
                                 parity=serial.PARITY_NONE,
                                 stopbits=serial.STOPBITS_ONE,
                                 bytesize=serial.EIGHTBITS,
                                 timeout=0.1)

        # Update date in using a background thread
        if self.scan_interval > 0:
            thread = threading.Thread(target=self.refresh, args=())
            thread.daemon = True
            thread.start()

    def refresh(self):
        """Background refreshing thread."""
        while True:
            self.read_data()
            time.sleep(self.scan_interval)

# pylint: disable=too-many-branches
    def read_data(self):
        """Read data from serial interface and return it as a dictionary.

        There is some caching implemented the sensor won't be polled twice 
        within a 15 second interval. If data is requested within 15 seconds 
        after it has been read, the data from the last read_data operation will
        be returned again 
        """

        mytime = time.time()
        if (self.last_poll is not None) and \
                (mytime - self.last_poll) <= 15:
            return self._data

        # Start function that can do several things (e.g. turning the
        # sensor on)
        if self.start_func:
            self.start_func(self.ser)

        res = None
        finished = False
        sbuf = bytearray()
        starttime = time.time()
        checkCode = int(0);
        expectedCheckCode = int()
        #it is necessary to reset input buffer because data is cotinously received by the system and placed in the device buffer when serial is open.
        #But "Home Assistant" code read it only from time to time so the data we read here would be placed in the past. 
        #Better is to clean the buffer and read new data from "present" time.
        self.ser.reset_input_buffer()
        while not finished:
            mytime = time.time()
            if mytime - starttime > self.timeout:
                LOGGER.error("read timeout after %s seconds, read %s bytes",
                             self.timeout, len(sbuf))
                return {}

            if self.ser.inWaiting() > 0:
                sbuf += self.ser.read(1)
                if len(sbuf) == len(self.start_sequence):
                    if sbuf == self.start_sequence:
                        LOGGER.debug("Found start sequence %s",
                                     self.start_sequence)
                    else:
                        LOGGER.debug("Start sequence not yet found")
                        # Remove first character
                        sbuf = sbuf[1:]

                if len(sbuf) == self.record_length:
                    #Check the control sum if it is known how to do it
                    if self.config == PLANTOWER1:                    
                        for c in sbuf[0:(self.record_length-2)]:
                            checkCode += c
                        expectedCheckCode = sbuf[30]*256 + sbuf[31]
                        if checkCode != expectedCheckCode:
			    #because of data inconsistency clean the buffer
                            LOGGER.error("PM sensor data sum error %d, expected %d", checkCode, expectedCheckCode)
                            sbuf = []
                            checkCode = 0                      
                            continue    

                    #if it is ok then send it for interpretation
                    res = self.parse_buffer(sbuf)
                    LOGGER.debug("Finished reading data %s", sbuf)
                    finished = True

            else:
                time.sleep(.5)
                LOGGER.debug("Serial waiting for data, buffer length=%s",
                             len(sbuf))

        if self.stop_func:
            self.stop_func(self.ser)

        self._data = res
        self.last_poll = time.time()
        return res

    def parse_buffer(self, sbuf):
        """Parse the buffer and return the PM values."""
        res = {}
        for pmname in PMVALS:
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

    def supported_values(self):
        res = []
        for pmname in PMVALS:
            offset = self.config[pmname]
            if offset is not None:
                res.append(pmname)
        return res
