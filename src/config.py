from logging import Logger

from src.notifications.service import NotificationService


class RunConfig():
    def __init__(self, log: Logger, db, notification: NotificationService) -> None:
        self.log = log
        self.db = db
        self.notification = notification
