
import functools
import threading
import concurrent.futures

from time import time
from os import environ, mkdir
from os.path import join, exists

#from .cmake import CMakeProject, isCmakeProject
from .environment import Environment, get_c_compiler, get_cxx_compiler
from .database import get_database
from .statistics import Statistics
from .build_systems import recognize_and_process

def map(exec, f, args):
    return [exec.submit(f, *d) for d in zip(*args)]

def when_all(futures, callback):
   return WhenAll(futures, callback)

class WhenAll:
    def __init__(self, fs, callback):
        self.callback = callback
        self.futures = set(fs)
        for f in fs:
            f.add_done_callback(self.done)

    def done(self, f):
        self.futures.remove(f)
        if len(self.futures) == 0:
            self.callback()

class RepositoryProcesser:

    def __init__(self, build_dir, cfg, out_log):
        self.build_dir = build_dir
        self.cfg = cfg
        self.out_log = out_log
        self.clone_time = 0
        self.unrecognized_projects = 0
        self.lock = threading.Lock()

    def clone_parallel(self, idx, repo, spec):

        start = time()
        repository_path = spec['codebase_data']['git_url']
        if 'status' in spec:
            # works -> check for updates
            # unrecognized -> nothing
            # fails -> check for updates, maybe try again
            if spec['status'] == 'unrecognized':
                with self.lock:
                    self.unrecognized_projects += 1
        # note; extend here for non-git repos
        project = GitProject(repository_path,
                spec['codebase_data']['default_branch'],
                self.cfg, self.out_log)
        project.clone(self.build_dir, idx)
        end = time()
        with self.lock:
            self.clone_time += end - start
        return (spec, project)

    def clone_serial(self, repositories_db):
        projects = []
        for repo, spec in repositories_db.items():

            self.out_log.next()
            self.error_log.next()
            repository_path = spec['codebase_data']['git_url']
            if 'status' in spec:
                # works -> check for updates
                # unrecognized -> nothing
                # fails -> check for updates, maybe try again
                if spec['status'] == 'unrecognized':
                    self.unrecognized_projects += 1
            # note; extend here for non-git repos
            start = time()
            project = GitProject(repository_path,
                    spec['codebase_data']['default_branch'],
                    self.cfg, self.out_log)
            project.clone(self.build_dir)
            projects.append( (spec, project) )
            end = time()
            self.clone_time += end - start

        self.out_log.info('Repository clone time: %f seconds', self.clone_time)
        return projects

def build_projects(build_dir, target_dir, repositories_db, force_update, cfg,
        out_log, error_log):

    if not exists(build_dir):
        mkdir(build_dir)
    if not exists(target_dir):
        mkdir(target_dir)

    projects_count = 0
    for database, repositories in repositories_db.items():
        projects_count += len(repositories)
    out_log.set_counter(projects_count)
    error_log.set_counter(projects_count)
    # Force compilers to use our wrappers
    env = Environment()
    env.overwrite_environment()
    stats = Statistics()

    repositories_idx = 0
    if cfg['clone']['multithreaded']:
        threads_count = cfg['clone']['threads']
    else:
        threads_count = 1
    with concurrent.futures.ThreadPoolExecutor( int(threads_count) ) as pool:
        projects = []
        database_processers = []
        for database, repositories in repositories_db.items():

            repo_count = len(repositories)
            processer = get_database(database)(build_dir, cfg, stats, out_log)
            indices = list( range(repositories_idx + 1, repo_count + 1) )
            keys, values = zip(*repositories.items())
            # idx, repo, spec -> project instance
            futures = map(pool, processer.clone, [indices, keys, values])
            # save statistics when database processer is done
            when_all(futures, lambda: processer.finish())

            # for each project, attach a builder
            build_func = lambda fut: recognize_and_process(*fut.result(), stats, out_log, error_log)
            for project in futures:
                project.add_done_callback(functools.partial(build_func))

            #projects.extend(futures)
            repositories_idx += repo_count
            database_processers.append(processer)

    out_log.next(projects_count)
    error_log.next(projects_count)

    #for project in projects:
    #    out_log.next()
    #    error_log.next()
    #    # classify repository
    #    source_dir = project.source_dir()
    #    if isCmakeProject(source_dir):
    #        cmake_repo = CMakeProject(source_dir, out_log, error_log)
    #        returnval = cmake_repo.configure(
    #                c_compiler = get_c_compiler(),
    #                cxx_compiler = get_cxx_compiler(),
    #                force_update = True
    #                )
    #        if not returnval:
    #            returnval = cmake_repo.build()
    #        if not returnval:
    #            cmake_repo.generate_bitcodes( join(target_dir, project.name()) )
    #        if returnval:
    #            incorrect_projects += 1
    #            spec['status'] = 'fails'
    #        else:
    #            correct_projects += 1
    #            spec['status'] = 'works'
    #    else:
    #        out_log.info('Unrecognized project %s' % source_dir)
    #        unrecognized_projects += 1
    #        spec['status'] = 'unrecognized'
    #end = time()
    env.reset_environment()
    stats.print_stats(out_log)

