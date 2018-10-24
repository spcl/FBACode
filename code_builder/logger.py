
from logging import LoggerAdapter, getLogger, DEBUG, FileHandler, Formatter

def create_logger(name, time):
    log = getLogger(name)
    log.setLevel(DEBUG)
    handler = FileHandler('%s_%s.log' % (name, time))
    format = Formatter('%(levelname)s - %(message)s')
    handler.setFormatter(format)
    log.addHandler(handler)
    return CountingLogger(log)

class CountingLogger(LoggerAdapter):

    def __init__(self, logger):
        super().__init__(logger, {})

    def next(self):
        self.extra['cur'] += 1

    def step(self, val):
        self.extra['cur'] += val

    def process(self, msg, kwargs):
        if 'cur' in self.extra:
            return '[%d/%d] %s' % (self.extra['cur'], self.extra['size'], msg), kwargs
        else:
            return msg, kwargs

    def set_counter(self, counter_max):
        self.extra['cur'] = 1
        self.extra['size'] = counter_max

    def delete_counter():
        del self.extra['cur']
        del self.extra['size']
