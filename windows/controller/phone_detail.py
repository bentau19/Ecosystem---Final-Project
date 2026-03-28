from typing import List, TYPE_CHECKING

from data_classes.phone_detail import BasicPhoneDetail

from models.phone_detail import PhoneDetailModel

if TYPE_CHECKING:
    from views.widgets.dashboard.phone_details_row import PhoneDetailsRow


class PhoneDetailController:
    def __init__(
            self,
            view: PhoneDetailsRow,
            model: PhoneDetailModel,
    ) -> None:
        """
        Initialize the controller with a view and a model.

        Args:
            view (PhoneDetailsRow): The view to update.
            model (PhoneDetailModel): The model containing the data.
        """
        self.model: PhoneDetailModel = model
        self.view: PhoneDetailsRow = view

    def fetch_phones_details(self) -> List[BasicPhoneDetail]:
        """
        Fetch the phone details.

        Returns:
            List[BasicPhoneDetail]: The list of phone details.
        """
        return self.model.fetch_phones_details()
