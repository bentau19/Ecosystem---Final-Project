from unittest.mock import MagicMock

import pytest

from entities.device_info import DeviceBaseInfoEntity, DeviceType


def _make_entity(device_type: DeviceType, title: str = "Test Device"):
    e = MagicMock(spec=DeviceBaseInfoEntity)
    e.type = device_type
    e.title = title
    return e


@pytest.fixture()
def mock_store():
    store = MagicMock()
    store.load.return_value = {}
    return store


@pytest.fixture()
def repo(mock_store, qapp):
    from repositories.device_info import DeviceInfoRepository
    return DeviceInfoRepository(store=mock_store)


class TestInit:
    def test_loads_data_from_store_on_init(self, mock_store, qapp):
        battery = _make_entity(DeviceType.BATTERY, "Battery")
        mock_store.load.return_value = {DeviceType.BATTERY: battery}

        from repositories.device_info import DeviceInfoRepository
        r = DeviceInfoRepository(store=mock_store)

        assert r.get_by_id(DeviceType.BATTERY) is battery

    def test_starts_empty_when_store_is_empty(self, repo):
        assert repo.get_all() == []


class TestGetById:
    def test_returns_entity_for_valid_id(self, repo, mock_store):
        entity = _make_entity(DeviceType.STORAGE)
        repo._data[DeviceType.STORAGE] = entity

        assert repo.get_by_id(DeviceType.STORAGE) is entity

    def test_returns_none_for_missing_id(self, repo):
        assert repo.get_by_id(DeviceType.BATTERY) is None


class TestGetAll:
    def test_returns_all_entities(self, repo):
        e1 = _make_entity(DeviceType.BATTERY)
        e2 = _make_entity(DeviceType.STORAGE)
        repo._data = {DeviceType.BATTERY: e1, DeviceType.STORAGE: e2}

        result = repo.get_all()
        assert len(result) == 2
        assert e1 in result
        assert e2 in result

    def test_returns_list_type(self, repo):
        assert isinstance(repo.get_all(), list)


class TestSave:
    def test_saves_entity_to_data(self, repo, mock_store):
        entity = _make_entity(DeviceType.BATTERY)
        repo.save(entity)

        assert repo._data[DeviceType.BATTERY] is entity

    def test_persists_to_store(self, repo, mock_store):
        entity = _make_entity(DeviceType.BATTERY)
        repo.save(entity)

        mock_store.save.assert_called_once()

    def test_emits_device_info_saved_signal(self, repo, qapp):
        entity = _make_entity(DeviceType.BATTERY)
        received = []
        repo.device_info_saved.connect(received.append)
        repo.save(entity)

        assert received == [entity]

    def test_raises_for_invalid_device_type(self, repo):
        entity = MagicMock(spec=DeviceBaseInfoEntity)
        entity.type = 9999  # not a valid DeviceType

        with pytest.raises(ValueError, match="Invalid device type"):
            repo.save(entity)

    def test_raises_for_duplicate_device_type(self, repo):
        entity = _make_entity(DeviceType.BATTERY, "Battery")
        repo.save(entity)

        duplicate = _make_entity(DeviceType.BATTERY, "Battery 2")
        with pytest.raises(ValueError, match="already exists"):
            repo.save(duplicate)

    def test_store_not_called_on_validation_error(self, repo, mock_store):
        entity = MagicMock(spec=DeviceBaseInfoEntity)
        entity.type = 9999

        mock_store.save.reset_mock()
        with pytest.raises(ValueError):
            repo.save(entity)

        mock_store.save.assert_not_called()


class TestDelete:
    def test_removes_entity_from_data(self, repo):
        entity = _make_entity(DeviceType.STORAGE)
        repo._data[DeviceType.STORAGE] = entity

        repo.delete(DeviceType.STORAGE)

        assert DeviceType.STORAGE not in repo._data

    def test_persists_to_store_after_delete(self, repo, mock_store):
        repo._data[DeviceType.STORAGE] = _make_entity(DeviceType.STORAGE)
        repo.delete(DeviceType.STORAGE)

        mock_store.save.assert_called()

    def test_emits_device_info_deleted_signal(self, repo, qapp):
        repo._data[DeviceType.BATTERY] = _make_entity(DeviceType.BATTERY)

        received = []
        repo.device_info_deleted.connect(received.append)
        repo.delete(DeviceType.BATTERY)

        assert received == [DeviceType.BATTERY]

    def test_raises_when_deleting_nonexistent_id(self, repo):
        with pytest.raises(ValueError, match="does not exist"):
            repo.delete(DeviceType.BATTERY)

    def test_store_not_called_on_missing_id(self, repo, mock_store):
        mock_store.save.reset_mock()
        with pytest.raises(ValueError):
            repo.delete(DeviceType.BATTERY)

        mock_store.save.assert_not_called()


class TestLoad:
    def test_delegates_to_store(self, repo, mock_store):
        data = {DeviceType.BATTERY: _make_entity(DeviceType.BATTERY)}
        mock_store.load.return_value = data

        result = repo.load()

        assert result is data
