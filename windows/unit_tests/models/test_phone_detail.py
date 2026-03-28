from unittest.mock import MagicMock

from data_classes.phone_detail import BasicPhoneDetail
from models.phone_detail import PhoneDetailModel
from repositories.phone_detail import PhoneDetailRepository


class TestPhoneDetailModel:
    def setup_method(self):
        self.model = PhoneDetailModel(PhoneDetailRepository())

    def test_returns_list(self):
        assert isinstance(self.model.fetch_phones_details(), list)

    def test_returns_four(self):
        assert len(self.model.fetch_phones_details()) == 4

    def test_all_basic_phone_detail(self):
        assert all(isinstance(i, BasicPhoneDetail) for i in self.model.fetch_phones_details())

    def test_delegates_to_repo(self):
        mock_repo = MagicMock()

        print(mock_repo)
        mock_repo.fetch_items.return_value = []
        print(mock_repo)
        PhoneDetailModel(mock_repo).fetch_phones_details()
        mock_repo.fetch_items.assert_called_once()

    def test_returns_repo_result_unchanged(self):
        mock_repo = MagicMock()
        sentinel = [MagicMock()]
        mock_repo.fetch_items.return_value = sentinel
        assert PhoneDetailModel(mock_repo).fetch_phones_details() is sentinel
