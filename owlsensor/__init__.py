from .serial_cm import CMDataCollector, SUPPORTED_SENSORS
from .device import Device

def get_async_datacollector(port_url: str, model: str, scan_interval_s: int = 30) -> CMDataCollector:
    """
    Return asynchronous version of CMDataCollector interface
    :param port_url: serial port, i.e. '/dev/ttyUSB0'
    :param model: device type, i.e. "CM160"
    :return: asynchronous implementation of Monoprice interface
    """
    if not model in SUPPORTED_SENSORS:
        return None
    
    return CMDataCollector(port_url, SUPPORTED_SENSORS[model], scan_interval_s)