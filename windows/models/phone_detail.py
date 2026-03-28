from typing import List

from PySide6.QtCore import QObject

from data_classes.phone_detail import BasicPhoneDetail
from repositories.phone_detail import PhoneDetailRepository


class PhoneDetailModel(QObject):
    def __init__(self, phone_repo: PhoneDetailRepository, parent=None):
        super().__init__(parent)

        self.phone_repo: PhoneDetailRepository = phone_repo

    def fetch_phones_details(self) -> List[BasicPhoneDetail]:
        return self.phone_repo.fetch_items()
