from src.notifications.service import NotificationService

class ConsoleNotification(NotificationService):
    def __init__(self, logger):
        self.logger = logger

    def send(self, message: str):
        self.logger.info(message)
