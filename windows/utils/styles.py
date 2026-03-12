from PySide6.QtCore import QFile, QTextStream

from resources.colors import Colors


def replace_colors_placeholders(qss: str):
    for color in Colors:
        qss = qss.replace(f"{{{{{color.name}}}}}", color.value)
    return qss


def load_stylesheet(qss_path: str) -> str:
    """
    Load a QSS stylesheet from a file and return its contents as a string.

    Args:
        qss_path (str): The path of the QSS file to load.

    Returns:
        str: The contents of the QSS file.

    Raises:
        FileNotFoundError: If the specified QSS file cannot be found.
    """

    qss_file: QFile = QFile(qss_path)

    if not qss_file.open(QFile.OpenModeFlag.ReadOnly):
        raise FileNotFoundError(f"Stylesheet not found: {qss_path}")

    stream: QTextStream = QTextStream(qss_file)

    qss = stream.readAll()

    qss = replace_colors_placeholders(qss)
    return qss
