from dataclasses import dataclass

@dataclass
class DeviceEntity:
    id: str
    name: str
    os: str
    tag: str
    last_connected: str
    battery_level: int
    battery_charging: bool
    storage_used: int
    storage_total: int
    ip: str
