
from threading import Lock

class Statistics:

    def __init__(self):
        self.correct_projects = 0
        self.incorrect_projects = 0
        self.unrecognized_projects = 0
        self.clone_time = 0
        self.build_time = 0
        self.lock = Lock()

    def print_stats(self, out_log):
        out_log.info('Repository clone time: %f seconds', self.clone_time)
        out_log.info('Repository build time: %f seconds', self.build_time)
        out_log.info('Succesfull builds: %d' % self.correct_projects)
        out_log.info('Failed builds: %d' % self.incorrect_projects)
        out_log.info('Unrecognized builds: %d' % self.unrecognized_projects)

    def update_clone_time(self, clone_time):
        with self.lock:
            self.clone_time += clone_time
