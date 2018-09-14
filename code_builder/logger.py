
from logging import LoggerAdapter, getLogger, DEBUG, FileHandler, Formatter

def create_logger(name, time, projects_count):
    log = getLogger(name)
    log.setLevel(DEBUG)
    handler = FileHandler('%s_%s.log' % (name, time))
    format = Formatter('%(levelname)s - %(message)s')
    handler.setFormatter(format)
    log.addHandler(handler)
    return CountingLogger(log, projects_count)

class CountingLogger(LoggerAdapter):

    def __init__(self, logger, projects_count):
        super().__init__(logger, { 'cur' : 1, 'size' : projects_count })

    def next(self):
        self.extra['cur'] += 1

    def process(self, msg, kwargs):
        return '[%d/%d] %s' % (self.extra['cur'], self.extra['size'], msg), kwargs
