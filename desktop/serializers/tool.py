from domain.entities.tool import ToolEntity
from serializers.serializer import ISerializer


class ToolSerializer(ISerializer[ToolEntity | None, tuple]):
    """Serializes and deserializes ToolEntity objects to and from SQLite row tuples.

    Maps between a ``ToolEntity`` (or ``None`` when absent) and its SQLite
    row representation ``(title, description, icon_path, is_enabled)``.

    A falsy row (``None`` or empty tuple) round-trips to ``None`` so that
    absent tools can be handled without special-case logic in the repository.
    """

    def serialize(self, entity: ToolEntity | None) -> tuple[str, str, str, bool] | None:
        """Convert a ToolEntity to a SQLite row tuple.

        Args:
            entity: The entity to serialize, or ``None`` if no tool is present.

        Returns:
            A tuple ``(title, description, icon_path, is_enabled)`` suitable
            for use with ``cursor.execute``.  Returns ``None`` when ``entity``
            is ``None``.
        """
        if entity is None:
            return None
        return (
            entity.title,
            entity.description,
            entity.icon_path,
            entity.is_enabled,
        )

    def deserialize(self, db_row: tuple) -> ToolEntity | None:
        """Reconstruct a ToolEntity from a SQLite row tuple.

        Args:
            db_row: A tuple with columns ``(title, description, icon_path,
                is_enabled)`` as returned by ``cursor.fetchone()``.  A falsy
                value (``None`` or empty tuple) is treated as "not found" and
                returns ``None``.

        Returns:
            A ``ToolEntity`` if ``db_row`` is non-empty, otherwise ``None``.
        """
        if not db_row:
            return None
        return ToolEntity(
            title=db_row[0],
            description=db_row[1],
            icon_path=db_row[2],
            is_enabled=bool(db_row[3]),
        )
