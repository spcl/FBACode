from logging import (
    LoggerAdapter,
    getLogger,
    INFO,
    DEBUG,
    FileHandler,
    Formatter,
    StreamHandler,
)


def create_stream_logger(name, stream, verbose):
    log = getLogger(name)
    if verbose == "True":
        log.setLevel(DEBUG)
    else:
        log.setLevel(INFO)
    handler = StreamHandler(stream)
    format = Formatter("%(levelname)s - %(message)s")
    handler.setFormatter(format)
    log.addHandler(handler)
    return CountingLogger(log)


def create_file_logger(filename, time, verbose):
    log = getLogger(filename)
    if verbose:
        log.setLevel(DEBUG)
    else:
        log.setLevel(INFO)
    filename = "%s_%s.log" % (filename, time) if time != "" else "%s.log" % filename
    handler = FileHandler(filename)
    format = Formatter("%(levelname)s - %(message)s")
    handler.setFormatter(format)
    log.addHandler(handler)
    return CountingLogger(log), filename


class CountingLogger(LoggerAdapter):
    def __init__(self, logger):
        super().__init__(logger, {})
        logger.propagate = False
        self.extra["cur"] = 0
        self.extra["size"] = 0

    # Thread-safe alternative to overwrite counter value
    def print_info(self, counter, msg):
        old_cur = self.extra["cur"]
        self.extra["cur"] = counter
        self.info(msg)
        self.extra["cur"] = old_cur

    def print_debug(self, counter, msg):
        old_cur = self.extra["cur"]
        self.extra["cur"] = counter
        self.debug(msg)
        self.extra["cur"] = old_cur

    def print_error(self, counter, msg):
        old_cur = self.extra["cur"]
        self.extra["cur"] = counter
        self.error(msg)
        self.extra["cur"] = old_cur

    def next(self):
        self.extra["cur"] += 1

    def next(self, step):
        self.extra["cur"] += step

    def process(self, msg, kwargs):
        if "cur" in self.extra:
            return "[%d/%d] %s" % (self.extra["cur"], self.extra["size"], msg), kwargs
        else:
            return msg, kwargs

    def set_counter(self, counter_max):
        self.extra["cur"] = 0
        self.extra["size"] = counter_max

    def delete_counter():
        del self.extra["cur"]
        del self.extra["size"]
