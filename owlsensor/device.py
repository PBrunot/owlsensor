from dataclasses import dataclass
from enum import Enum

class DeviceType(Enum):
    """Device types."""

    CM160_I = "CM 160 - Current"

DEVICES = [
    {"id": 1, "type": DeviceType.CM160_I},
]

@dataclass
class Device:
    """API device."""

    device_id: int
    device_unique_id: str
    device_type: DeviceType
    name: str
    state: int | bool
