from unittest.mock import MagicMock

from controller.phone_detail import PhoneDetailController
from data_classes.phone_detail import DeviceInfoDetail, BatteryDetail


class TestPhoneDetailController:

    def test_correct_fetch(self):
        mock_view = MagicMock()
        mock_model = MagicMock()
        mock_model.fetch_phones_details.return_value = [DeviceInfoDetail("fdfddf", "fddffd", "ffdd", "fdfd"),
                                                        BatteryDetail("fdfd", "fdfdfd", "fdfd", 68, False)]
        controller = PhoneDetailController(view=mock_view, model=mock_model)
        controller.fetch_phones_details()
        mock_model.fetch_phones_details.assert_called_once()
