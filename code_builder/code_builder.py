import functools

# import threading
import concurrent.futures
import json
import multiprocessing
import sys
from multiprocessing import Manager

from time import time
from os import environ, mkdir, getpid, listdir, remove
import os
from os.path import isdir, join, exists, basename
from sys import stdout
from datetime import datetime
import traceback

import shutil

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


def get_dir_size(start_path):

    # https://stackoverflow.com/questions/1392413/calculating-a-directorys-size-using-python
    total_size = 0
    file_count = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
        for f in filenames:
            fp = join(dirpath, f)
            # skip if it is symbolic link
            if not os.path.islink(fp):
                file_count += 1
                total_size += os.path.getsize(fp)

    return total_size, file_count


def download_and_build(
    cloner, idx, name, project, target_dir, build_dir, ctx, stats, running_builds
):
    running_builds[multiprocessing.current_process().name] = (idx, name)
    print("| ", end="")
    print("\n| ".join("{}\t{}".format(k, v) for k, v in running_builds.items()))
    global loggers
    ctx.set_loggers(loggers.stdout, loggers.stderr)
    try:
        cloner.clone(idx, name, project)
    except Exception as e:
        print("error cloning {}:\n{}".format(name, e))
        project["status"] = "clone fail"
        return (idx, name, project)
    try:
        idx, name, new_project = recognize_and_build(
            idx, name, project, build_dir, target_dir, ctx, stats=stats
        )
    except Exception as e:
        print("aaaaaaaaaaaaaaaaaa failure in {} builder:\n{}".format(name, e))
        print(
            "Stackoverflow approach:\n{}".format(
                "".join(traceback.format_exception(*sys.exc_info()))
            )
        )
        project["status"] = "docker_crash"
        new_project = project
    # save build dir and source dir size
    if "build" in project and "dir" in project["build"]:
        size, count = get_dir_size(project["build"]["dir"])
        project["build"]["file_count"] = count
        project["build"]["size"] = size
    if "source" in project:
        size, count = get_dir_size(project["source"]["dir"])
        project["source"]["file_count"] = count
        project["source"]["size"] = size
    # delete build files if option set
    if ctx.cfg["build"]["keep_build_files"] == "False":
        # delete everything except log file and project.json
        proj_build_dir = join(build_dir, basename(project["source"]["dir"]))
        if exists(proj_build_dir):
            for f in listdir(proj_build_dir):
                try:
                    p = join(proj_build_dir, f)
                    if isdir(p):
                        shutil.rmtree(p, ignore_errors=True)
                    elif not (".log" in f or f == "output.json"):
                        remove(p)
                except Exception as e:
                    print("Error removing build dir: {}".format(e))
    if ctx.cfg["build"]["keep_source_files"] == "False":
        # delete source folder
        shutil.rmtree(project["source"]["dir"], ignore_errors=True)
    print("| DONE building {}".format(name))
    running_builds.pop(multiprocessing.current_process().name)
    running_builds["builds_left"] -= 1
    # print("\n| ".join("{}\t{}".format(k, v) for k, v in running_builds.items()))
    # print("|----------------")
    return (idx, name, new_project)


def build_projects(
    source_dir,
    build_dir,
    target_dir,
    repositories_db,
    force_update,
    cfg,
    output,
    log_dir,
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
    # builds_left = projects_count
    repositories_idx = 0
    if cfg["clone"]["multithreaded"]:
        threads_count = int(cfg["clone"]["threads"])
    else:
        threads_count = 1
    # contexts = []
    ctx = Context(projects_count, cfg)
    # global loggers
    # loggers = open_logfiles(ctx.cfg, getpid())
    # for log in (loggers.stdout, loggers.stderr):
    #     log.set_counter(ctx.projects_count)
    # ctx.set_loggers(loggers.stdout, loggers.stderr)
    start = time()
    stats = Statistics(projects_count)
    manager = Manager()
    running_builds = manager.dict()
    running_builds["builds_left"] = projects_count
    with concurrent.futures.ProcessPoolExecutor(threads_count) as pool:
        projects = []

        database_processers = []
        # we need an instance of the statistics class for the dependency analysis
        # when we build twice
        all_repositories = {}
        temporary_stats = Statistics(projects_count)
        idx = 0
        for database, repositories in repositories_db.items():
            # my simple attempt:
            repo_count = len(repositories)
            db_processor = get_database(database)(source_dir, ctx)
            database_processers.append(db_processor)
            # indices = list(range(repositories_idx + 1, repositories_idx + repo_count + 1))
            # idx = indices[0]
            for name, proj in repositories.items():
                future = pool.submit(
                    initializer_func,
                    ctx,
                    download_and_build,
                    (
                        db_processor,
                        idx,
                        name,
                        proj,
                        target_dir,
                        build_dir,
                        ctx,
                        temporary_stats,
                        running_builds,
                    ),
                )
                projects.append(future)
                idx += 1
            repositories_idx += repo_count
        print("submitted {} tasks to queue".format(idx))
        # for project in concurrent.futures.as_completed(futures):
        for project in projects:
            idx, key, val = project.result()
            all_repositories[key] = val
            # builds_left -= 1
            # print("{} builds left".format(builds_left))
        end = time()
        print("Process repositorites in %f [s]" % (end - start))
    start = time()
    with open("current_build.json", "w",) as o:
        o.write(json.dumps(all_repositories, indent=2))
    for (i, (name, proj)) in enumerate(all_repositories.items()):
        print("[{}/{}] stats for {}".format(i, projects_count, name))
        stats.update(proj, name)
    print()
    end = time()
    print("Process repositorites in %f [s]" % (end - start))
    stats.print_stats(stdout)
    # save various jsons with stats
    timestamp = cfg["output"]["time"]
    stats.save_rebuild_json(log_dir, timestamp)
    stats.save_errors_json()
    stats.save_errorstat_json(log_dir, timestamp)
    stats.save_dependencies_json(log_dir, timestamp)
    # timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    with open(
        join(log_dir, "summary_{}_{}.txt".format(timestamp, projects_count)), "w"
    ) as o:
        stats.print_stats(o)
    with open(
        join(log_dir, "build_details_{}_{}.json".format(timestamp, projects_count)),
        "w",
    ) as o:
        o.write(json.dumps(all_repositories, indent=2))
