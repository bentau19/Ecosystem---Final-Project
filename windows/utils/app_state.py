from repositories.phone_detail import PhoneDetailRepository
from repositories.tool_detail import ToolDetailRepository


class AppState:
    def __init__(self):
        self.tools_repository = ToolDetailRepository()
        self.phone_repository = PhoneDetailRepository()


app_state = AppState()
