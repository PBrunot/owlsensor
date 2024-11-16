import asyncio
import logging
import time
from owlsensor import serial_cm as cm


async def main_loop():
    logging.basicConfig(level=logging.DEBUG)
    sensors = []
    sensors.append(cm.CMDataCollector("COM4",
                                      cm.SUPPORTED_SENSORS["TheOWL,CM160"]))

    for s in sensors:
        await s.connect()

    while True:
        for s in sensors:
            print(await s.read_data())
        await asyncio.sleep(3)

if __name__ == '__main__':
    asyncio.run(main_loop())
