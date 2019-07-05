
from time import time
from threading import Lock
from .repository import GitProject

class GitHub:

    def __init__(self, build_dir, cfg, stats, out_log):
        self.build_dir = build_dir
        self.cfg = cfg
        self.out_log = out_log
        self.clone_time = 0
        self.stats = stats
        self.lock = Lock()

    def clone(self, idx, name, project):

        start = time()
        repository_path = project['codebase_data']['git_url']
        git_repo = GitProject(repository_path,
                project['codebase_data']['default_branch'],
                self.cfg, self.out_log)
        git_repo.clone(self.build_dir, idx)
        # check for updates
        if project['status'] == 'new':
            project['status'] = 'cloned'
        if not 'source' in project:
            project['source'] = {'dir' : repository_path}
        end = time()
        self.out_log.print_info(idx, "Cloned project %s from GitHub in %f seconds" % (name, end - start))
        with self.lock:
            self.clone_time += end - start
        return (idx, name, project)

    # Save statistics and display info
    def finish(self):
        with self.stats.lock:
            self.stats.clone_time += self.clone_time

databases = { 'github.org' : GitHub }

def get_database(name):
    return databases[name]
