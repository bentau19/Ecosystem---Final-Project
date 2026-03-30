from dataclasses import asdict

from serializers.device_info import DeviceInfoSerializer
from serializers.tool import ToolSerializer

from entities.device_info import (
    DeviceType,
    DeviceGeneralInfoEntity,
    DeviceBatteryInfoEntity,
    DeviceStorageInfoEntity,
)
from entities.tool import ToolEntity


class TestDeviceInfoSerializerSerialize:
    def setup_method(self):
        self.serializer = DeviceInfoSerializer()

    def _make_battery(self) -> DeviceBatteryInfoEntity:
        return DeviceBatteryInfoEntity(
            title="Battery",
            icon_path="icons/battery.png",
            icon_background_color="#FF0000",
            type=DeviceType.BATTERY,
            battery_percentage=75,
            is_charging=False,
        )

    def _make_storage(self) -> DeviceStorageInfoEntity:
        return DeviceStorageInfoEntity(
            title="Storage",
            icon_path="icons/storage.png",
            icon_background_color="#00FF00",
            type=DeviceType.STORAGE,
            used_storage=100,
            total_storage=512,
        )

    def _make_general(self) -> DeviceGeneralInfoEntity:
        return DeviceGeneralInfoEntity(
            title="Device Name",
            icon_path="icons/device.png",
            icon_background_color="#0000FF",
            type=DeviceType.DEVICE_NAME,
            description="My Phone",
        )

    def test_serialize_returns_dict(self):
        data = {DeviceType.BATTERY: self._make_battery()}
        assert isinstance(self.serializer.serialize(data), dict)

    def test_serialize_uses_enum_value_as_key(self):
        battery = self._make_battery()
        data = {DeviceType.BATTERY: battery}
        result = self.serializer.serialize(data)

        assert DeviceType.BATTERY.value in result

    def test_serialize_converts_entity_to_dict(self):
        battery = self._make_battery()
        result = self.serializer.serialize({DeviceType.BATTERY: battery})

        assert result[DeviceType.BATTERY.value] == asdict(battery)

    def test_serialize_empty_input(self):
        assert self.serializer.serialize({}) == {}

    def test_serialize_multiple_entities(self):
        data = {
            DeviceType.BATTERY: self._make_battery(),
            DeviceType.STORAGE: self._make_storage(),
        }
        result = self.serializer.serialize(data)

        assert len(result) == 2
        assert DeviceType.BATTERY.value in result
        assert DeviceType.STORAGE.value in result

    # --- deserialize ---

    def test_deserialize_returns_dict_with_enum_keys(self):
        raw = {str(DeviceType.BATTERY.value): asdict(self._make_battery())}
        result = self.serializer.deserialize(raw)

        assert DeviceType.BATTERY in result

    def test_deserialize_battery_to_correct_type(self):
        raw = {str(DeviceType.BATTERY.value): asdict(self._make_battery())}
        result = self.serializer.deserialize(raw)

        assert isinstance(result[DeviceType.BATTERY], DeviceBatteryInfoEntity)

    def test_deserialize_storage_to_correct_type(self):
        raw = {str(DeviceType.STORAGE.value): asdict(self._make_storage())}
        result = self.serializer.deserialize(raw)

        assert isinstance(result[DeviceType.STORAGE], DeviceStorageInfoEntity)

    def test_deserialize_general_to_correct_type(self):
        raw = {str(DeviceType.DEVICE_NAME.value): asdict(self._make_general())}
        result = self.serializer.deserialize(raw)

        assert isinstance(result[DeviceType.DEVICE_NAME], DeviceGeneralInfoEntity)

    def test_deserialize_preserves_field_values(self):
        battery = self._make_battery()
        raw = {str(DeviceType.BATTERY.value): asdict(battery)}
        result = self.serializer.deserialize(raw)

        deserialized = result[DeviceType.BATTERY]
        assert deserialized.battery_percentage == battery.battery_percentage
        assert deserialized.is_charging == battery.is_charging

    def test_deserialize_empty_input(self):
        assert self.serializer.deserialize({}) == {}

    def test_roundtrip_preserves_data(self):
        original = {
            DeviceType.BATTERY: self._make_battery(),
            DeviceType.STORAGE: self._make_storage(),
        }
        serialized = self.serializer.serialize(original)
        restored = self.serializer.deserialize(
            {str(k): v for k, v in serialized.items()}
        )

        for device_type, entity in original.items():
            assert asdict(restored[device_type]) == asdict(entity)


# ===========================================================================
# ToolSerializer
# ===========================================================================

def _make_tool_entity(title="Hammer", enabled=True) -> ToolEntity:
    return ToolEntity(
        title=title,
        description=f"{title} desc",
        icon_path=f"icons/{title.lower()}.png",
        icon_background_color="#AABBCC",
        is_enabled=enabled,
    )


class TestToolSerializerSerialize:
    def setup_method(self):
        self.serializer = ToolSerializer()

    def test_serialize_returns_dict(self):
        data = {"Hammer": _make_tool_entity("Hammer")}
        assert isinstance(self.serializer.serialize(data), dict)

    def test_serialize_preserves_keys(self):
        data = {"Hammer": _make_tool_entity("Hammer")}
        result = self.serializer.serialize(data)

        assert "Hammer" in result

    def test_serialize_converts_entity_to_dict(self):
        entity = _make_tool_entity("Drill")
        result = self.serializer.serialize({"Drill": entity})

        assert result["Drill"] == asdict(entity)

    def test_serialize_empty_input(self):
        assert self.serializer.serialize({}) == {}

    def test_serialize_multiple_tools(self):
        data = {
            "Saw": _make_tool_entity("Saw"),
            "Drill": _make_tool_entity("Drill"),
        }
        result = self.serializer.serialize(data)

        assert len(result) == 2

    def test_serialize_disabled_tool(self):
        entity = _make_tool_entity("Chisel", enabled=False)
        result = self.serializer.serialize({"Chisel": entity})

        assert result["Chisel"]["is_enabled"] is False


class TestToolSerializerDeserialize:
    def setup_method(self):
        self.serializer = ToolSerializer()

    def test_deserialize_returns_dict_of_tool_entities(self):
        raw = {"Hammer": asdict(_make_tool_entity("Hammer"))}
        result = self.serializer.deserialize(raw)

        assert "Hammer" in result
        assert isinstance(result["Hammer"], ToolEntity)

    def test_deserialize_preserves_fields(self):
        entity = _make_tool_entity("Wrench")
        raw = {"Wrench": asdict(entity)}
        result = self.serializer.deserialize(raw)

        assert result["Wrench"].title == entity.title
        assert result["Wrench"].is_enabled == entity.is_enabled
        assert result["Wrench"].description == entity.description

    def test_deserialize_empty_input(self):
        assert self.serializer.deserialize({}) == {}

    def test_deserialize_multiple_tools(self):
        raw = {
            "Saw": asdict(_make_tool_entity("Saw")),
            "Drill": asdict(_make_tool_entity("Drill")),
        }
        result = self.serializer.deserialize(raw)

        assert len(result) == 2

    def test_roundtrip_preserves_data(self):
        original = {
            "Hammer": _make_tool_entity("Hammer"),
            "Chisel": _make_tool_entity("Chisel", enabled=False),
        }
        serialized = self.serializer.serialize(original)
        restored = self.serializer.deserialize(serialized)

        for key, entity in original.items():
            assert asdict(restored[key]) == asdict(entity)