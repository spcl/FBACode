import functools

# import threading
import concurrent.futures
import json

from time import time
from os import environ, mkdir, getpid
from os.path import join, exists
from sys import stdout
from datetime import datetime

from .statistics import Statistics
from .database import get_database
from .build_systems.build_systems import recognize_and_build
from .utils.driver import open_logfiles

init = False
loggers = None
builds_left = 0


def initializer_func(ctx, f, args):
    global init, loggers
    if not init:
        init = True
        loggers = open_logfiles(ctx.cfg, getpid())
        for log in (loggers.stdout, loggers.stderr):
            log.set_counter(ctx.projects_count)
        ctx.set_loggers(loggers.stdout, loggers.stderr)
    else:
        ctx.set_loggers(loggers.stdout, loggers.stderr)
    return f(*args)


def map(exec, f, args, ctx):
    return [
        exec.submit(functools.partial(initializer_func, ctx, f, d)) for d in zip(*args)
    ]


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
    def __init__(self, projects_count, cfg):
        self.cfg = cfg
        # self.stats = Statistics()
        self.projects_count = projects_count

    def set_loggers(self, out, err):
        self.out_log = out
        self.err_log = err


def copy_futures(dest, src):
    if src.cancelled():
        dest.cancel()
    exc = src.exception()
    if exc is not None:
        dest.set_exception(exc)
    else:
        dest.set_result(src.result())


def callback(pool, ctx, f, callback):
    future = concurrent.futures.Future()

    def local_callback(f):
        res = pool.submit(
            functools.partial(initializer_func, ctx, callback, f.result())
        )
        res.add_done_callback(functools.partial(copy_futures, future))

    f.add_done_callback(local_callback)
    return future


def build_projects(
    source_dir, build_dir, target_dir, repositories_db, force_update, cfg, output
):

    if not exists(source_dir):
        mkdir(source_dir)
    if not exists(build_dir):
        mkdir(build_dir)
    if not exists(target_dir):
        mkdir(target_dir)

    projects_count = 0
    for database, repositories in repositories_db.items():
        projects_count += len(repositories)
    # env = Environment()
    # env.overwrite_environment()
    builds_left = projects_count
    repositories_idx = 0
    if cfg["clone"]["multithreaded"]:
        threads_count = int(cfg["clone"]["threads"])
    else:
        threads_count = 1
    contexts = []
    ctx = Context(projects_count, cfg)
    start = time()
    with concurrent.futures.ProcessPoolExecutor(threads_count) as pool:
        projects = []
        database_processers = []
        for database, repositories in repositories_db.items():

            repo_count = len(repositories)
            processer = get_database(database)(source_dir, ctx)
            indices = list(range(repositories_idx + 1, repo_count + 1))
            keys, values = zip(*repositories.items())
            # idx, repo, spec -> downloaded project
            futures = map(pool, processer.clone, [indices, keys, values], ctx)
            # save statistics when database processer is done
            # when_all(futures, lambda: processer.finish())

            # TODO handle repository that is not updated

            # for each project, attach a builder
            # build_func = lambda fut: recognize_and_build(*fut.result(), build_dir, target_dir, ctx)
            for project in futures:
                projects.append(
                    callback(
                        pool,
                        ctx,
                        project,
                        functools.partial(
                            recognize_and_build,
                            build_dir=build_dir,
                            target_dir=target_dir,
                            ctx=ctx,
                        ),
                    )
                )
            repositories_idx += repo_count
            database_processers.append(processer)

        stats = Statistics(projects_count)
        for project in projects:
            idx, key, val = project.result()
            repositories[key] = val
            # builds_left -= 1
            # print("{} builds left".format(builds_left))
            stats.update(val, key)

        end = time()
        print("Process repositorites in %f [s]" % (end - start))
        stats.print_stats(stdout)
        # close f again?
        f = stdout if output == "" else open(output, "w")
        print(json.dumps(repositories, indent=2), file=f)
        stats.save_rebuild_json()
        stats.save_errors_json()
        timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
        with open(join("buildlogs", "summary_{}_{}.txt".format(projects_count, timestamp)), 'w') as o:
            stats.print_stats(o)
        with open(join("buildlogs", "build_details_{}_{}.json".format(projects_count, timestamp)), 'w') as o:
            o.write(json.dumps(repositories, indent=2))

    # env.reset_environment()

    # for project in projects:
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
    # end = time()
