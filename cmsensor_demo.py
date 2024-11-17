import asyncio
import logging
import time
from owlsensor import serial_cm as cm

LOGGER = logging.getLogger(__name__)

async def main_loop(port: str):
    logging.basicConfig(level=logging.DEBUG)
    
    LOGGER.info("Connecting to %s", port)
    sensors = []
    sensors.append(cm.CMDataCollector(port, cm.SUPPORTED_SENSORS["CM160"]))

    for s in sensors:
        result = await s.connect()
        LOGGER.info("Connection result : %d", result)

    while True:
        for s in sensors:
            data = await s.read_data()
            LOGGER.info("Read: %s", data)
        await asyncio.sleep(3)

if __name__ == '__main__':
    asyncio.run(main_loop("/dev/ttyUSB0"))