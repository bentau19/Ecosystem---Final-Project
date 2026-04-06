from dataclasses import asdict, dataclass

import pytest

from enums.device_type import DeviceType


# ── Inline stubs ──────────────────────────────────────────────────────────────


@dataclass
class DeviceBaseInfoEntity:
    title: str
    icon_path: str
    icon_background_color: str
    type: DeviceType


@dataclass
class DeviceBatteryInfoEntity(DeviceBaseInfoEntity):
    battery_percentage: int
    is_charging: bool


@dataclass
class DeviceStorageInfoEntity(DeviceBaseInfoEntity):
    used_storage: int
    total_storage: int


@dataclass
class DeviceGeneralInfoEntity(DeviceBaseInfoEntity):
    description: str


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def serializer():
    from serializers.device_info import DeviceInfoSerializer
    return DeviceInfoSerializer()


@pytest.fixture
def general_entity():
    return DeviceGeneralInfoEntity(
        title="Device Name", icon_path="/icons/name.png",
        icon_background_color="#fff", type=DeviceType.DEVICE_NAME,
        description="A general device"
    )


@pytest.fixture
def battery_entity():
    return DeviceBatteryInfoEntity(
        title="Battery", icon_path="/icons/battery.png",
        icon_background_color="#0f0", type=DeviceType.BATTERY,
        battery_percentage=85, is_charging=True
    )


@pytest.fixture
def storage_entity():
    return DeviceStorageInfoEntity(
        title="Storage", icon_path="/icons/storage.png",
        icon_background_color="#00f", type=DeviceType.STORAGE,
        used_storage=500, total_storage=1000
    )


# ── serialize ─────────────────────────────────────────────────────────────────

def test_serialize_empty_dict(serializer):
    assert serializer.serialize({}) == {}


def test_serialize_uses_device_type_value_as_key(serializer, battery_entity):
    result = serializer.serialize({DeviceType.BATTERY: battery_entity})
    assert DeviceType.BATTERY.value in result


def test_serialize_single_entity_matches_asdict(serializer, battery_entity):
    result = serializer.serialize({DeviceType.BATTERY: battery_entity})
    assert result[DeviceType.BATTERY.value] == asdict(battery_entity)


def test_serialize_multiple_entities(serializer, battery_entity, storage_entity):
    data = {
        DeviceType.BATTERY: battery_entity,
        DeviceType.STORAGE: storage_entity,
    }
    result = serializer.serialize(data)
    assert len(result) == 2
    assert result[DeviceType.BATTERY.value] == asdict(battery_entity)
    assert result[DeviceType.STORAGE.value] == asdict(storage_entity)


def test_serialize_preserves_all_fields(serializer, battery_entity):
    result = serializer.serialize({DeviceType.BATTERY: battery_entity})
    serialized = result[DeviceType.BATTERY.value]
    assert serialized["battery_percentage"] == 85
    assert serialized["is_charging"] is True
    assert serialized["title"] == "Battery"


def test_serialize_general_entity(serializer, general_entity):
    result = serializer.serialize({DeviceType.DEVICE_NAME: general_entity})
    assert result[DeviceType.DEVICE_NAME.value]["description"] == "A general device"


def test_serialize_storage_entity(serializer, storage_entity):
    result = serializer.serialize({DeviceType.STORAGE: storage_entity})
    serialized = result[DeviceType.STORAGE.value]
    assert serialized["used_storage"] == 500
    assert serialized["total_storage"] == 1000


# ── deserialize ───────────────────────────────────────────────────────────────

def test_deserialize_empty_dict(serializer):
    assert serializer.deserialize({}) == {}


def test_deserialize_uses_int_key_as_device_type(serializer, battery_entity):
    raw = {str(DeviceType.BATTERY.value): asdict(battery_entity)}
    result = serializer.deserialize(raw)
    assert DeviceType.BATTERY in result


def test_deserialize_battery_entity_type(serializer, battery_entity):
    raw = {str(DeviceType.BATTERY.value): asdict(battery_entity)}
    result = serializer.deserialize(raw)
    assert isinstance(result[DeviceType.BATTERY], DeviceBatteryInfoEntity)


def test_deserialize_storage_entity_type(serializer, storage_entity):
    raw = {str(DeviceType.STORAGE.value): asdict(storage_entity)}
    result = serializer.deserialize(raw)
    assert isinstance(result[DeviceType.STORAGE], DeviceStorageInfoEntity)


def test_deserialize_general_entity_type(serializer, general_entity):
    raw = {str(DeviceType.DEVICE_NAME.value): asdict(general_entity)}
    result = serializer.deserialize(raw)
    assert isinstance(result[DeviceType.DEVICE_NAME], DeviceGeneralInfoEntity)


def test_deserialize_preserves_battery_fields(serializer, battery_entity):
    raw = {str(DeviceType.BATTERY.value): asdict(battery_entity)}
    result = serializer.deserialize(raw)
    entity = result[DeviceType.BATTERY]
    if not isinstance(entity, DeviceBatteryInfoEntity):
        pytest.fail("entity isn't DeviceBatteryInfoEntity")
    assert entity.battery_percentage == 85
    assert entity.is_charging is True
    assert entity.title == "Battery"


def test_deserialize_preserves_storage_fields(serializer, storage_entity):
    raw = {str(DeviceType.STORAGE.value): asdict(storage_entity)}
    result = serializer.deserialize(raw)
    entity = result[DeviceType.STORAGE]
    if not isinstance(entity, DeviceStorageInfoEntity):
        pytest.fail("entity isn't DeviceStorageInfoEntity")
    assert entity.used_storage == 500
    assert entity.total_storage == 1000


def test_deserialize_preserves_general_fields(serializer, general_entity):
    raw = {str(DeviceType.DEVICE_NAME.value): asdict(general_entity)}
    result = serializer.deserialize(raw)
    entity = result[DeviceType.DEVICE_NAME]
    if not isinstance(entity, DeviceGeneralInfoEntity):
        pytest.fail("entity isn't DeviceGeneralInfoEntity")
    assert entity.description == "A general device"


def test_deserialize_multiple_entities(serializer, battery_entity, storage_entity):
    raw = {
        str(DeviceType.BATTERY.value): asdict(battery_entity),
        str(DeviceType.STORAGE.value): asdict(storage_entity),
    }
    result = serializer.deserialize(raw)
    assert len(result) == 2
    assert isinstance(result[DeviceType.BATTERY], DeviceBatteryInfoEntity)
    assert isinstance(result[DeviceType.STORAGE], DeviceStorageInfoEntity)


def test_deserialize_accepts_int_keys(serializer, battery_entity):
    raw = {DeviceType.BATTERY.value: asdict(battery_entity)}
    result = serializer.deserialize(raw)
    assert DeviceType.BATTERY in result


# ── roundtrip ─────────────────────────────────────────────────────────────────

def test_roundtrip_battery(serializer, battery_entity):
    data = {DeviceType.BATTERY: battery_entity}
    assert serializer.deserialize(serializer.serialize(data)) == data


def test_roundtrip_storage(serializer, storage_entity):
    data = {DeviceType.STORAGE: storage_entity}
    assert serializer.deserialize(serializer.serialize(data)) == data


def test_roundtrip_general(serializer, general_entity):
    data = {DeviceType.DEVICE_NAME: general_entity}
    assert serializer.deserialize(serializer.serialize(data)) == data


def test_roundtrip_all_entities(serializer, general_entity, battery_entity, storage_entity):
    data = {
        DeviceType.DEVICE_NAME: general_entity,
        DeviceType.BATTERY: battery_entity,
        DeviceType.STORAGE: storage_entity,
    }
    assert serializer.deserialize(serializer.serialize(data)) == data
