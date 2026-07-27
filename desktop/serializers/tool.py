from domain.entities.tool import ToolEntity
from serializers.serializer import ISerializer

_ToolDict = dict[str, object]


class ToolSerializer(ISerializer[ToolEntity | None, _ToolDict | None]):
    """Serializes and deserializes ToolEntity objects to and from JSON dicts.

    Maps between a ``ToolEntity`` (or ``None`` when absent) and a plain,
    JSON-ready dict with keys ``title``, ``description``, ``icon_path`` and
    ``is_enabled``.

    A falsy value (``None`` or empty dict) round-trips to ``None`` so that
    absent tools can be handled without special-case logic in the repository.
    """

    @staticmethod
    def serialize(entity: ToolEntity | None) -> _ToolDict | None:
        """Convert a ToolEntity to a JSON-ready dict.

        Args:
            entity: The entity to serialize, or ``None`` if no tool is present.

        Returns:
            A dict ``{title, description, icon_path, is_enabled}`` ready for
            ``json.dump``.  Returns ``None`` when ``entity`` is ``None``.
        """
        if entity is None:
            return None
        return {
            "title": entity.title,
            "description": entity.description,
            "icon_path": entity.icon_path,
            "is_enabled": entity.is_enabled,
        }

    @staticmethod
    def deserialize(data: _ToolDict | None) -> ToolEntity | None:
        """Reconstruct a ToolEntity from a JSON dict.

        Args:
            data: A dict with keys ``title``, ``description``, ``icon_path`` and
                ``is_enabled`` as parsed from ``tools.json``.  A falsy value
                (``None`` or empty dict) is treated as "not found" and returns
                ``None``.

        Returns:
            A ``ToolEntity`` if ``data`` is non-empty, otherwise ``None``.
        """
        if not data:
            return None
        return ToolEntity(
            title=str(data.get("title", "")),
            description=str(data.get("description", "")),
            icon_path=str(data.get("icon_path", "")),
            is_enabled=bool(data.get("is_enabled", False)),
        )
