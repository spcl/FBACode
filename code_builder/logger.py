
from logging import LoggerAdapter, getLogger, DEBUG, FileHandler, Formatter
from datetime import datetime

def create_logger(name, projects_count):
    current_time = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
    log = getLogger(name)
    log.setLevel(DEBUG)
    handler = FileHandler('%s_%s.log' % (name, current_time))
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
