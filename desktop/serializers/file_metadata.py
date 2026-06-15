import json
from pathlib import Path
from typing import Any

from jsonschema import validate

from domain.dto.file_metadata import FileMetadataDTO
from serializers.serializer import ISerializer

# Schema loaded once at import time — avoids repeated disk reads per call.
_SCHEMA: dict[str, Any] = json.loads(
    (Path(__file__).parent / "schemas" / "file_metadata.json").read_text(encoding="utf-8")
)


class FileMetadataSerializer(ISerializer[FileMetadataDTO, str]):
    """Serializes :class:`~domain.dto.file_metadata.FileMetadataDTO` to/from JSON.

    Converts the DTO to and from the JSON wire format used on the
    ``file_meta`` TauSync channel.

    Wire format::

        {"file_name": <str>, "file_size": <int>, "modified_at": <int>}

    ``modified_at`` is optional on inbound payloads (legacy senders may omit
    it); it defaults to ``0`` when absent, meaning "timestamp not provided".

    Both :meth:`serialize` and :meth:`deserialize` validate the wire object
    against the JSON Schema at ``serializers/schemas/file_metadata.json``
    before returning, so malformed payloads are caught at the boundary rather
    than propagating into domain code.
    """

    @staticmethod
    def serialize(data: FileMetadataDTO) -> str:
        """Convert a :class:`~domain.dto.file_metadata.FileMetadataDTO` to a JSON string.

        Args:
            data: The metadata DTO to serialize.

        Returns:
            A validated JSON string with ``file_name``, ``file_size``, and
            ``modified_at`` keys.

        Raises:
            jsonschema.ValidationError: If the produced object fails schema validation.
        """
        wire: dict[str, Any] = {
            "file_name": data.name,
            "file_size": data.size,
            "modified_at": data.modified_at,
        }
        validate(instance=wire, schema=_SCHEMA)
        return json.dumps(wire)

    @staticmethod
    def deserialize(data: str) -> FileMetadataDTO:
        """Parse a JSON string into a :class:`~domain.dto.file_metadata.FileMetadataDTO`.

        ``modified_at`` is optional — legacy senders that omit it produce a DTO
        with ``modified_at=0``, which callers treat as "timestamp not provided".

        Args:
            data: JSON string containing ``file_name`` and ``file_size`` keys,
                and optionally ``modified_at``.

        Returns:
            A :class:`~domain.dto.file_metadata.FileMetadataDTO` instance.

        Raises:
            json.JSONDecodeError: If *data* is not valid JSON.
            jsonschema.ValidationError: If the parsed object fails schema validation.
            KeyError: If required keys are absent after validation.
        """
        parsed: dict[str, Any] = json.loads(data)
        validate(instance=parsed, schema=_SCHEMA)
        return FileMetadataDTO(
            name=parsed["file_name"],
            size=int(parsed["file_size"]),
            modified_at=int(parsed.get("modified_at", 0)),
        )
