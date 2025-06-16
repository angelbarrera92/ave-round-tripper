import asyncio
import threading

from src.notifications.service import NotificationService

from telegram import Bot
from telegram.error import TimedOut, NetworkError
from telegram.request import HTTPXRequest

_default_read_timeout = 5


class Telegram(NotificationService):

    def __init__(self, token: str, chat_id: str) -> None:
        self.__token = token
        self.__chat_id = chat_id

    def send(self, message: str) -> None:
        print(f"Sending message to Telegram chat {self.__chat_id}: {message}")
        try:
            # Try to get the current event loop
            try:
                loop = asyncio.get_running_loop()
                # If there's a running loop, create a new thread to avoid conflicts
                def run_in_thread():
                    # Create a new Bot instance in this thread to avoid event loop conflicts
                    _request = HTTPXRequest(read_timeout=_default_read_timeout)
                    bot = Bot(self.__token, request=_request)
                    asyncio.run(bot.send_message(chat_id=self.__chat_id, text=message))
                
                thread = threading.Thread(target=run_in_thread)
                thread.start()
                thread.join()  # Wait for the thread to complete
            except RuntimeError:
                # No running loop, safe to use asyncio.run()
                _request = HTTPXRequest(read_timeout=_default_read_timeout)
                bot = Bot(self.__token, request=_request)
                asyncio.run(bot.send_message(chat_id=self.__chat_id, text=message))
        except (TimedOut, NetworkError) as e:
            print(f"Telegram notification failed: {e}")
            pass
