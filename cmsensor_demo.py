import asyncio
import logging
import time
from owlsensor import serial_cm as cm

LOGGER = logging.getLogger(__name__)

async def main_loop(port: str):
    logging.basicConfig(level=logging.DEBUG)

    LOGGER.info("Connecting to %s", port)

    # Using context manager for proper resource cleanup
    async with cm.CMDataCollector(port, cm.SUPPORTED_SENSORS["CM160"]) as sensor:
        while True:
            try:
                data = await sensor.read_data()
                if data:
                    LOGGER.info("Read: %s", data)
                else:
                    LOGGER.warning("No data received")
                await asyncio.sleep(3)
            except KeyboardInterrupt:
                LOGGER.info("Shutting down...")
                break
            except Exception as e:
                LOGGER.error("Error in main loop: %s", e)
                await asyncio.sleep(3)

if __name__ == '__main__':
    asyncio.run(main_loop("/dev/ttyUSB0"))