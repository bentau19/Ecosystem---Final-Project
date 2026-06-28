import json
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from domain.entities.device_info import DeviceEntity
from repositories.repository import IRepository
from serializers.device import DeviceSerializer
from utils.meta import ABCQObjectMeta
from utils.paths import data_dir


class DeviceRepository(
    IRepository[DeviceEntity, str], QObject, metaclass=ABCQObjectMeta
):
    """Repository for the single current device, backed by ``device.json``.

    Holds at most one ``DeviceEntity`` — the most recently connected device.
    Previous-device history is intentionally **not** retained: every ``save``
    overwrites the stored device.  The record is loaded on construction and
    re-written atomically (``.tmp`` sibling renamed over the real file) on every
    mutation.  A lock guards mutations so the repository is safe to call from
    the background threads that read device info.

    Signals:
        entity_saved:   Emitted with the saved ``DeviceEntity`` after a
            successful ``save`` call.
        entity_deleted: Emitted with the device ID (``str``) after ``delete``.
    """

    entity_saved: Signal = Signal(object)
    entity_deleted: Signal = Signal(str)

    def __init__(
            self,
            parent: QObject | None = None,
            path: Path | None = None,
    ) -> None:
        """Initialize the repository and eagerly load the stored device.

        Args:
            parent: Optional Qt parent object.
            path: Optional override for the ``device.json`` location (used by
                tests). Defaults to ``data_dir() / "device.json"``.
        """
        super().__init__(parent)
        self._serializer = DeviceSerializer()
        self._path: Path = path if path is not None else data_dir() / "device.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._device: DeviceEntity | None = self._load()

    # ── Persistence helpers ──────────────────────────────────────────────────

    def _load(self) -> DeviceEntity | None:
        # Read and deserialize the stored device; missing/corrupt → None.
        try:
            if not self._path.exists():
                return None
            with open(self._path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            return self._serializer.deserialize(raw)
        except (json.JSONDecodeError, OSError, TypeError, ValueError, KeyError):
            return None

    def _flush(self) -> None:
        # Atomically write the current device (or ``null``) back to disk.
        tmp = self._path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._serializer.serialize(self._device), fh, indent=2)
            tmp.replace(self._path)
        except OSError:
            pass

    # ── Public API ───────────────────────────────────────────────────────────

    def id_exists(self, id: str) -> bool:
        """Check whether the stored device has the given ID.

        Args:
            id: The device UUID to look up.

        Returns:
            ``True`` if a device is stored and its ID matches, else ``False``.
        """
        with self._lock:
            return self._device is not None and self._device.id == id

    def get_by_id(self, id: str) -> DeviceEntity | None:
        """Return the stored device if its ID matches, otherwise ``None``.

        Args:
            id: The device ID to look up.

        Returns:
            The stored ``DeviceEntity`` if its ``id`` equals the argument,
            otherwise ``None``.
        """
        with self._lock:
            if self._device is not None and self._device.id == id:
                return self._device
            return None

    def get_all(self) -> list[DeviceEntity]:
        """Return the stored device as a single-element list, or empty.

        Returns:
            A list containing the current device, or ``[]`` if none is set.
        """
        with self._lock:
            return [self._device] if self._device is not None else []

    def save(self, entity: DeviceEntity) -> None:
        """Set the current device (overwriting any previous) and flush to disk.

        Args:
            entity: The device to persist as the currently connected device.

        Emits:
            entity_saved: With the saved entity after the file write.
        """
        if entity is None:
            return
        with self._lock:
            self._device = entity
            self._flush()
        self.entity_saved.emit(entity)

    def delete(self, id: str) -> None:
        """Clear the current device if its ID matches and flush to disk.

        Args:
            id: The device ID to remove.

        Emits:
            entity_deleted: With ``id`` after the write (always emitted, even
                if no matching device was set).
        """
        with self._lock:
            if self._device is not None and self._device.id == id:
                self._device = None
                self._flush()
        self.entity_deleted.emit(id)
