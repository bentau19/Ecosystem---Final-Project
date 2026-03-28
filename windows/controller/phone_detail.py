from typing import List
from typing import TYPE_CHECKING

from data_classes.phone_detail import BasicPhoneDetail
from models.phone_detail import PhoneDetailModel
from utils.app_state import app_state

if TYPE_CHECKING:
    from views.widgets.dashboard.phone_details_row import PhoneDetailsRow


class PhoneDetailController:
    def __init__(self, view: PhoneDetailsRow, model: PhoneDetailModel):
        self.model = model
        self.view = view

    def fetch_phones_details(self) -> List[BasicPhoneDetail]:
        return self.model.fetch_phones_details()
