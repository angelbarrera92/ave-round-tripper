from src.notifications.service import NotificationService

from telegram import Bot
from telegram.error import TimedOut
from telegram.utils.request import Request

_default_read_timeout = 5


class Telegram(NotificationService):

    def __init__(self, token: str, chat_id: str) -> None:
        _request = Request(
            read_timeout=_default_read_timeout)
        self.__chat_id = chat_id
        self.__bot = Bot(token, request=_request)

    def send(self, message: str) -> None:
        try:
            self.__bot.send_message(chat_id=self.__chat_id, text=message)
        except TimedOut:
            pass
