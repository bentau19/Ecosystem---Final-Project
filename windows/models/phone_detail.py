from typing import List

from PySide6.QtCore import QObject

from data_classes.phone_detail import BasicPhoneDetail
from repositories.phone_detail import PhoneDetailRepository


class PhoneDetailModel(QObject):
    """
    Model for fetching phone details.
    """

    def __init__(self, phone_repo: PhoneDetailRepository, parent: QObject = None) -> None:
        """
        Initialize the model with a phone repository.

        Args:
            phone_repo (PhoneDetailRepository): The repository containing phone details.
            parent (QObject, optional): The parent object. Defaults to None.
        """
        super().__init__(parent)

        self.phone_repo: PhoneDetailRepository = phone_repo

    def fetch_phones_details(self) -> List[BasicPhoneDetail]:
        """
        Fetch the phone details.

        Returns:
            List[BasicPhoneDetail]: The list of phone details.
        """
        return self.phone_repo.fetch_items()