
import functools
import threading
import concurrent.futures

from time import time
from os import environ, mkdir
from os.path import join, exists

from .environment import Environment
from .statistics import Statistics
from .database import get_database
from .build_systems import recognize_and_build

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

class Context:

    def __init__(self, projects_count, cfg, out_log, err_log):
        self.cfg = cfg
        self.out_log = out_log
        self.err_log = err_log
        self.env = Environment()
        self.stats = Statistics()
        self.projects_count = projects_count

        # Force compilers to use our wrappers
        self.env.overwrite_environment()
        self.out_log.set_counter(projects_count)
        self.err_log.set_counter(projects_count)

    def close(self):
        self.out_log.next(self.projects_count)
        self.err_log.next(self.projects_count)
        self.env.reset_environment()
        self.stats.print_stats(self.out_log)


def build_projects(build_dir, target_dir, repositories_db, force_update, cfg,
        out_log, error_log):

    if not exists(build_dir):
        mkdir(build_dir)
    if not exists(target_dir):
        mkdir(target_dir)

    projects_count = 0
    for database, repositories in repositories_db.items():
        projects_count += len(repositories)
    ctx = Context(projects_count, cfg, out_log, error_log)

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
            processer = get_database(database)(build_dir, ctx)
            indices = list( range(repositories_idx + 1, repo_count + 1) )
            keys, values = zip(*repositories.items())
            # idx, repo, spec -> downloaded project
            futures = map(pool, processer.clone, [indices, keys, values])
            # save statistics when database processer is done
            when_all(futures, lambda: processer.finish())

            # for each project, attach a builder
            build_func = lambda fut: recognize_and_build(*fut.result(), ctx)
            for project in futures:
                project.add_done_callback(functools.partial(build_func))

            #projects.extend(futures)
            repositories_idx += repo_count
            database_processers.append(processer)

    ctx.close()

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

