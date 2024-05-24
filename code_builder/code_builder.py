import functools

# import threading
import concurrent.futures
import json
import multiprocessing
import sys
import tarfile
import tempfile
import glob
import random
from multiprocessing import Manager
from fabric import Connection

from time import time
from os import environ, makedirs, mkdir, getpid, listdir, remove
import os
from os.path import isdir, join, exists, basename
from sys import stdout
from datetime import datetime
import traceback
from time import sleep

import shutil

from .statistics import Statistics
from .database import get_database
from .build_systems.build_systems import recognize_and_build
from .utils.driver import open_logfiles, recursively_get_files, recursively_get_dirs

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


class Context:
    def __init__(self, projects_count, cfg):
        self.cfg = cfg
        # self.stats = Statistics()
        self.projects_count = projects_count
        self.timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")


    def set_loggers(self, out, err):
        self.out_log = out
        self.err_log = err


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

def send_to_spclstorage(ctx, project_name, build_dir, ast_dir, bitcodes_dir, project):
    nr_removed_files = 0
    # ast_files_in_build = glob.glob(join(build_dir, "**/*.ast"), recursive = True)
    ast_files_in_build = recursively_get_files(build_dir, ".ast")
    for ast_file in ast_files_in_build:
        if exists(ast_file):
            os.remove(ast_file)
            nr_removed_files += 1
    print(f"Removed {nr_removed_files} AST files from build directory. Glob reported {len(ast_files_in_build)} ASTs")

    # the temporary file gets deleted when it gets garbage collected
    with tempfile.NamedTemporaryFile(suffix='.tar.gz') as f:
        # print(f"Creating tarball for {project_name} with name {f.name}")
        with tarfile.open(fileobj=f, mode='w:gz') as tar:
            tar.add(name = ast_dir, arcname = f'./compiler_output/AST')
            tar.add(name = bitcodes_dir, arcname = f'./compiler_output/bitcodes')
            # tar.add(name = features_dir, arcname = f'./compiler_output/features/{project_name}')
            tar.add(name = build_dir, arcname = f'./build')
            # if "temp_build_dir" in project["build"]:
            #     tar.add(name = project["build"]["temp_build_dir"], arcname = basename(project["build"]["temp_build_dir"]))

        f.flush()
        f.seek(0)
        
        USER = 'cdragancea'
        c = Connection(host = 'spclstorage.inf.ethz.ch', user = USER)
        c.run(f'mkdir -p /home/{USER}/runs_archived/run_{ctx.cfg["output"]["time"]}')
        c.put(f.name, remote = f'/home/{USER}/runs_archived/run_{ctx.cfg["output"]["time"]}/{project_name}.tar.gz')
        # c.run(f'tar -xf /home/{USER}/{project_name}_{ctx.timestamp}.tar.gz -C /home/{USER}/runs/')
        # c.run(f'rm /home/{USER}/{project_name}_{ctx.timestamp}.tar.gz')
    
    return nr_removed_files

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
        print("Failure in {} builder:\n{}".format(name, e))
        print(
            "Exception trace:\n{}".format(
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
    # if ctx.cfg["build"]["keep_build_files"] == "False":
    #     # delete everything except log file and project.json
    #     proj_build_dir = join(build_dir, basename(project["source"]["dir"]))
    #     if exists(proj_build_dir):
    #         for f in listdir(proj_build_dir):
    #             try:
    #                 p = join(proj_build_dir, f)
    #                 if isdir(p):
    #                     shutil.rmtree(p, ignore_errors=True)
    #                 elif not (".log" in f or f == "output.json"):
    #                     remove(p)
    #             except Exception as e:
    #                 print("Error removing build dir: {}".format(e))
    if ctx.cfg["build"]["keep_source_files"] == "False":
        # delete source folder
        shutil.rmtree(project["source"]["dir"], ignore_errors=True)
    print("| DONE building {}".format(name))

    # copy build artifacts to spcltorage server
    proj_build_dir = join(build_dir, basename(project["source"]["dir"]))
    ast_dir = join(target_dir, name, "AST")
    bitcodes_dir = join(target_dir, name, "bitcodes")
    # features_dir = join(target_dir, "features", name)

    if ctx.cfg["build"]["store_to_spclstorage"] == "True":
        nr_asts = send_to_spclstorage(ctx, name, proj_build_dir, ast_dir, bitcodes_dir, project)
        if "build" in new_project:
            new_project["build"]["nr_asts"] = nr_asts
        
    if ctx.cfg["build"]["remove_local_artifacts"] == "True":
        # shutil.rmtree(proj_build_dir, ignore_errors=True)
        # recursively delete files in the build folder except the logs
        # all_files = glob.glob(join(proj_build_dir, "**/*"), recursive = True)
        all_files = recursively_get_files(proj_build_dir)
        for file in all_files:
            if not os.path.exists(file):
                continue
            if not file.endswith(".log"):
                if isdir(file):
                    shutil.rmtree(file, ignore_errors=True)
                else:
                    os.remove(file)
        shutil.rmtree(ast_dir, ignore_errors=True)
        shutil.rmtree(bitcodes_dir, ignore_errors=True)
        # shutil.rmtree(features_dir, ignore_errors=True)


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

    with open("all_built.json", "r") as fin:
        previous_all_repositories = json.load(fin)
    
    with open("intermediate_all_built.json", "r") as fin:
        temp_data = json.load(fin)
        previous_all_repositories.update(temp_data)
    
    all_built_lock = manager.Lock()

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

            for name, proj in random.sample(list(repositories.items()), len(list(repositories.items()))):
                if name in previous_all_repositories:# and (previous_all_repositories[name]["status"] == "success"
                                                      #    or previous_all_repositories[name]["status"] == "have archive"
                                                       #   or ("build" in previous_all_repositories[name] and previous_all_repositories[name]["build"].get("build", "") == "success")):
                    # all_repositories[name] = previous_all_repositories[name]
                    idx += 1
                    running_builds["builds_left"] -= 1
                    continue

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
            previous_all_repositories[key] = val
            print(f"Got back the result of the {key} project future. Writing to file...")

            all_built_lock.acquire()
            with open("intermediate_all_built.json", "w") as o:
                o.write(json.dumps(previous_all_repositories, indent = 2))
            all_built_lock.release()

            # if running_builds["builds_left"] % 5 == 0:
            # print(f"Builds left: {running_builds['builds_left']}")

            # builds_left -= 1
            # print("{} builds left".format(builds_left))
        end = time()
        print("Process repositorites in %f [s]" % (end - start))
    start = time()
    
    with open("all_built.json", "w") as o:
        o.write(json.dumps(previous_all_repositories, indent = 2))

    with open("current_build.json", "w",) as o:
        o.write(json.dumps(all_repositories, indent=2))
        o.flush()

        saved = False
        tries = 0
        while saved and tries < 5:
            try:
                USER = 'cdragancea'
                c = Connection(host = 'spclstorage.inf.ethz.ch', user = USER)
                c.put(o.name, remote = f'/home/{USER}/runs_archived/run_{ctx.cfg["output"]["time"]}/build_summary.json')
                saved = True
            except:
                tries += 1
                sleep(1)
        
        if saved is False:
            print("Failed to save build summary to spclstorage")

    try:
        for (i, (name, proj)) in enumerate(all_repositories.items()):
            print("[{}/{}] stats for {}".format(i, projects_count, name))
            stats.update(proj, name)
    except Exception as e:
        print("Error updating stats: {}".format(e))
    print()
    end = time()
    print("Process repositorites in %f [s]" % (end - start))
    stats.print_stats(stdout)
    # save various jsons with stats
    if not isdir(log_dir):
        makedirs(log_dir)
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
