from __future__ import annotations

import json

from domain.dto.backup_session_prompt import BackupSessionPromptDTO
from serializers.serializer import ISerializer


class BackupSessionSerializer(ISerializer[BackupSessionPromptDTO, str]):
    """Serializes and deserializes the backup-session prompt DTO.

    Maps between a :class:`~domain.dto.backup_session_prompt.BackupSessionPromptDTO`
    and its JSON wire representation sent over the ``backup_manifest`` TauSync
    channel.

    Wire format (Android → PC)::

        {
            "file_count":    <int>,
            "files_bytes":   <int>,
            "classify":      <bool>,   # optional — defaults to True when absent
            "storage_saver": <bool>    # optional — defaults to False when absent
        }

    Field mapping:

    DTO field            ↔  JSON key
    ``file_count``       ↔  ``"file_count"``
    ``total_size_bytes`` ↔  ``"files_bytes"``
    ``classify``         ↔  ``"classify"``        (optional; defaults to ``True``)
    ``storage_saver``    ↔  ``"storage_saver"``   (optional; defaults to ``False``)
    """

    @staticmethod
    def serialize(entity: BackupSessionPromptDTO | None) -> str | None:
        """Convert a :class:`~domain.dto.backup_session_prompt.BackupSessionPromptDTO`
        to a JSON string.

        Args:
            entity: The DTO to serialize, or ``None``.

        Returns:
            A JSON string with ``file_count``, ``files_bytes``, and ``classify``
            keys, or ``None`` when *entity* is ``None``.
        """
        if entity is None:
            return None

        payload = {
            "file_count":    entity.file_count,
            "files_bytes":   entity.total_size_bytes,
            "classify":      entity.classify,
            "storage_saver": entity.storage_saver,
        }
        return json.dumps(payload)

    @staticmethod
    def deserialize(data: str) -> BackupSessionPromptDTO | None:
        """Reconstruct a :class:`~domain.dto.backup_session_prompt.BackupSessionPromptDTO`
        from a JSON string.

        ``classify`` is optional on inbound payloads (legacy senders that omit
        it produce a DTO with ``classify=True`` so existing behaviour is
        preserved).

        Args:
            data: JSON string containing at least ``file_count`` and
                ``files_bytes`` keys.

        Returns:
            A :class:`~domain.dto.backup_session_prompt.BackupSessionPromptDTO`
            instance, or ``None`` when *data* is falsy.

        Raises:
            json.JSONDecodeError: If *data* is not valid JSON.
            ValueError: If required keys are absent.
        """
        if not data:
            return None

        parsed = json.loads(data)

        file_count = parsed.get("file_count")
        files_bytes = parsed.get("files_bytes")

        if file_count is None or files_bytes is None:
            raise ValueError(
                "Backup manifest JSON is missing required keys "
                f"('file_count', 'files_bytes'). Got: {list(parsed.keys())}"
            )

        return BackupSessionPromptDTO(
            file_count=int(file_count),
            total_size_bytes=int(files_bytes),
            classify=bool(parsed.get("classify", True)),
            storage_saver=bool(parsed.get("storage_saver", False)),
        )
