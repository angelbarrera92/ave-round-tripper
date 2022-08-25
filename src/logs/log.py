import logging


def log_setup(logger, level):
    logger.setLevel(level)

    # create a formatter that creates a single line of json with a comma at the end
    formatter = logging.Formatter(
        (
            '{"time":"%(asctime)s", "module":"%(name)s:%(lineno)s",'
            ' "level":"%(levelname)s", "msg":"%(message)s"}'
        )
    )

    # create a channel for handling the logger and set its format
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)

    # connect the logger to the channel
    ch.setLevel(level)
    logger.addHandler(ch)

    # send an example message
    logger.debug("logging is working")
    return logger
