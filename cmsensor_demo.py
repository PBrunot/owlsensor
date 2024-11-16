import logging
import time
from owlsensor import serial_cm as cm


def main():
    logging.basicConfig(level=logging.INFO)
    sensors = []
    sensors.append(cm.PMDataCollector("/dev/tty.SLAB_USBtoUART",
                                      cm.SUPPORTED_SENSORS["TheOWL,CM160"]))

    for s in sensors:
        print(s.supported_values())

    while True:
        for s in sensors:
            print(s.read_data())
        time.sleep(3)

if __name__ == '__main__':
    main()
