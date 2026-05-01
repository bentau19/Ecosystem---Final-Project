import os
import sys

from PySide6.QtCore import QFile, QTextStream

from resources.colors import ColorsEnum, Colors


def _replace_colors_placeholders(
        qss: str, color_class: type[ColorsEnum]
) -> str:
    """Replace ``{{NAME}}`` color placeholders in a QSS string with design-token values.

    Iterates over every member of *color_class* and substitutes the double-brace
    placeholder ``{{NAME}}`` with its corresponding enum value string.

    Args:
        qss: The raw QSS text containing ``{{NAME}}`` placeholders.
        color_class: An enum class whose members map placeholder names to color values.

    Returns:
        The QSS string with all recognized placeholders replaced by their values.
    """
    for name, color in color_class.__members__.items():
        qss = qss.replace(f"{{{{{name}}}}}", color.value)
    return qss


def load_stylesheet(
        qss_path: str, color_classes: list[type[ColorsEnum]] | None = None
) -> str:
    """Load a QSS stylesheet from a Qt virtual path and resolve color tokens.

    Opens the file via the Qt resource system, reads its full text, then
    replaces ``{{NAME}}`` placeholders using *color_classes* followed by the
    base :class:`~resources.colors.Colors` enum.  The base ``Colors`` pass
    always runs last so it acts as a fallback for any un-overridden tokens.

    Args:
        qss_path: Qt virtual path to the ``.qss`` file (e.g. ``":/styles/topbar.qss"``).
        color_classes: Optional list of additional color enum classes whose
            tokens are resolved before the base ``Colors`` pass.

    Returns:
        The fully resolved QSS string ready to pass to ``setStyleSheet``.

    Raises:
        FileNotFoundError: If *qss_path* cannot be opened via the Qt resource system.
    """
    qss_file = QFile(qss_path)
    if not qss_file.open(QFile.OpenModeFlag.ReadOnly):
        raise FileNotFoundError(f"Stylesheet not found: {qss_path}")

    stream = QTextStream(qss_file)
    qss: str = stream.readAll()
    qss_file.close()

    if color_classes is None:
        return _replace_colors_placeholders(qss, Colors)

    for cls in color_classes:
        qss = _replace_colors_placeholders(qss, cls)
    qss = _replace_colors_placeholders(qss, Colors)

    return qss


def load_stylesheet_disk(
        rel_path: str, color_classes: list[type[ColorsEnum]] | None = None
) -> str:
    """Load a QSS stylesheet from the filesystem and resolve color tokens.

    Designed for standalone PyInstaller executables that cannot access the Qt
    virtual resource filesystem.  Resolves the ``resources/`` root at
    :data:`sys._MEIPASS` when running bundled, or relative to this module's
    directory in development.

    Args:
        rel_path: Path relative to the ``resources/`` directory, e.g.
            ``"styles/handlers/handler-dialog.qss"``.
        color_classes: Optional list of additional :class:`ColorsEnum`
            subclasses resolved before the base :class:`Colors` pass.

    Returns:
        The fully resolved QSS string ready to pass to ``setStyleSheet``.

    Raises:
        FileNotFoundError: If the resolved path does not exist on disk.
    """
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller bundle — resources/ is extracted alongside the executable
        base = os.path.join(sys._MEIPASS, 'resources')
    else:
        # Development — resources/ is a sibling of desktop/utils/
        base = os.path.normpath(
            os.path.join(os.path.dirname(__file__), '..', 'resources')
        )

    full_path = os.path.join(base, rel_path)

    with open(full_path, 'r', encoding='utf-8') as fh:
        qss: str = fh.read()

    if color_classes:
        for cls in color_classes:
            qss = _replace_colors_placeholders(qss, cls)
    qss = _replace_colors_placeholders(qss, Colors)

    return qss
