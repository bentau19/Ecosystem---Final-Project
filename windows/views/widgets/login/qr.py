import socket
from enum import StrEnum

import qrcode
from PIL.ImageQt import ImageQt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QApplication


class Data(StrEnum):
    IP = "ip"
    

class QR(QLabel):
    """
    QR code image.
    """

    def __init__(self) -> None:
        super().__init__()

        self._load_qr()
        self._setup_ui()

    def _setup_ui(self):
        self.setPixmap(QPixmap.fromImage(self._qr))
        pass

    def _load_qr(self):
        hostname = socket.gethostname()
        print(hostname)
        ip = socket.gethostbyname(hostname)
        data: dict[str, str] = {Data.IP.value: ip}

        qr = qrcode.QRCode(box_size=10, border=4)
        qr.add_data(str(data))
        qr.make(fit=True)

        self._qr: ImageQt = ImageQt(qr.make_image(fill_color="black", back_color="white").get_image())


if __name__ == "__main__":
    app = QApplication()
    qr1 = QR()
    qr1.show()
    app.exec()
