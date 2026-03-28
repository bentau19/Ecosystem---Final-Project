from typing import Type, List, Optional

from PySide6.QtCore import QFile, QTextStream

from resources.colors import ColorsEnum, Colors


def _replace_colors_placeholders(
        qss: str, color_class: Type[ColorsEnum]
) -> str:
    """
    Replace color placeholders in a QSS stylesheet with their corresponding values.

    Args:
        qss (str): The QSS stylesheet with color placeholders.
        color_class (Type[ColorsEnum]): The enum class containing the color values.

    Returns:
        str: The QSS stylesheet with color placeholders replaced by their values.
    """
    for name, color in color_class.__members__.items():
        qss = qss.replace(f"{{{{{name}}}}}", color.value)
    return qss


def load_stylesheet(
        qss_path: str, color_classes: Optional[List[Type[ColorsEnum]]] = None
) -> str:
    """
    Load a QSS stylesheet from a file and return its contents as a string.

    Args:
        qss_path (str): The path of the QSS file to load.
        color_classes (Optional[List[Type[ColorsEnum]]]): The list of enum classes
            containing the color values.

    Returns:
        str: The contents of the QSS file.

    Raises:
        FileNotFoundError: If the specified QSS file cannot be found.
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
