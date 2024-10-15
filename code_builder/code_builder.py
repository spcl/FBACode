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
from .utils.driver import open_logfiles, recursively_get_files, recursively_get_files_containing

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
            if os.path.exists(fp) and not os.path.islink(fp):
                file_count += 1
                try:
                    total_size += os.path.getsize(fp)
                except Exception as e:
                    print(f"Error getting size of {fp}: {e}")

    return total_size, file_count

def remove_files_with_ext(dir, ext):
    files = recursively_get_files(dir, ext)
    nr_removed_files = 0
    for file in files:
        if exists(file):
            os.remove(file)
            nr_removed_files += 1
    if nr_removed_files > 0:
        print(f"Removed {nr_removed_files} {ext} files from build directory. Glob reported {len(files)} {ext}")

    return nr_removed_files

def remove_files_containing(dir, substr):
    files = recursively_get_files_containing(dir, substr)
    nr_removed_files = 0
    for file in files:
        if exists(file):
            os.remove(file)
            nr_removed_files += 1
    if nr_removed_files > 0:
        print(f"Removed {nr_removed_files} files containing {substr} from build directory. Glob reported {len(files)} files")

    return nr_removed_files

def clean_build_dir(build_dir):
    nr_removed_files = 0
    EXTENSIONS_TO_REMOVE = [".ast", ".bc", ".png", ".jpg", ".jpeg", ".rar", ".zip", ".7z", ".tar", ".gz", ".wav", ".mp3", ".mp4", ".o", ".a", ".html", ".css", ".svg", ".sh", ".make", ".txt", ".md", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".xml", ".yaml", ".yml", ".csv", ".tsv", ".sql", ".py", ".pyc", ".pyo", ".pyd", ".jar", ".war", ".ear", ".so", ".dll", ".exe", ".bat", ".cmd", ".ps1", ".psm1", ".psd1", ".ps1xml", ".pssc", ".psc1", ".pssc"]
    for ext in EXTENSIONS_TO_REMOVE:
        nr_removed_files += remove_files_with_ext(build_dir, ext)
    
    # clean .so files that have version number after .so
    nr_removed_files += remove_files_containing(build_dir, ".so.")
    
    return nr_removed_files

def send_to_remote_server(ctx, project_name, build_dir, ast_dir, bitcodes_dir, project):
    nr_removed_files = clean_build_dir(build_dir)
    nr_removed_files = 0

    # the temporary file gets deleted when it gets garbage collected
    with tempfile.NamedTemporaryFile(suffix='.tar.gz') as f:
        # print(f"Creating tarball for {project_name} with name {f.name}")
        with tarfile.open(fileobj=f, mode='w:gz') as tar:
            tar.add(name = ast_dir, arcname = f'./compiler_output/AST')
            tar.add(name = bitcodes_dir, arcname = f'./compiler_output/bitcodes')

            # need to recursively add the build folder because some weird projects (scid) create a 
            # folder with no read permission, only for sudo.
            # need to manually walk through and add the files if they are readable
            
            for root, dirs, files in os.walk(build_dir):
                for file in files:
                    file_path = os.path.abspath(join(root, file))
                    file_path_without_build_dir = file_path[len(os.path.abspath(build_dir)) + 1:]

                    try:
                        tar.add(name = file_path, arcname = f'./build/{file_path_without_build_dir}')
                    except Exception as e:
                        # print(f"failed to add file {file_path} to tarball: {e}")
                        pass

            # tar.add(name = build_dir, arcname = f'./build')
            # if "temp_build_dir" in project["build"]:
            #     tar.add(name = project["build"]["temp_build_dir"], arcname = basename(project["build"]["temp_build_dir"]))

        f.flush()

        c = Connection(host = ctx.cfg["remote"]["host"], user = ctx.cfg["remote"]["user"])

        c.run(f'mkdir -p {ctx.cfg["remote"]["artifacts_target_folder"]}/run_{ctx.cfg["output"]["time"]}')
        
        exception_flag = False
        try:
            c.put(f.name, remote = f'{ctx.cfg["remote"]["artifacts_target_folder"]}/run_{ctx.cfg["output"]["time"]}/{project_name}.tar.gz')
            print(f"Copied {f.name} to remote storage server as {ctx.cfg['remote']['artifacts_target_folder']}/run_{ctx.cfg['output']['time']}/{project_name}.tar.gz")
        except Exception as e:
            # There is some weird PermissionError happening even though the file was actually copied to the remote server
            # I think it is happening because of the filesytem on the remote server

            remote_file_size = int(c.run(f"stat -c %s {ctx.cfg['remote']['artifacts_target_folder']}/run_{ctx.cfg['output']['time']}/{project_name}.tar.gz", hide = True).stdout.strip())
            local_file_size = os.path.getsize(f.name)

            if remote_file_size != local_file_size:
                exception_flag = True

                print("Failed to upload build artifacts to remote storage server")
                print(f"src = {f.name} dst = {ctx.cfg['remote']['artifacts_target_folder']}/run_{ctx.cfg['output']['time']}/{project_name}.tar.gz")

                shutil.copyfile(f.name, f'/home/cdragancea/{project_name}_{ctx.timestamp}.tar.gz')
                print(f"Exception: {e}")
                print(f"Traceback: {traceback.format_exc()}")

    if exception_flag:
        raise Exception("Failed to upload build artifacts to remote storage server")


    print(f"Uploaded {project_name} to remote storage server")
    return nr_removed_files

def download_and_build(
    cloner, idx, name, project, target_dir, build_dir, ctx, stats, running_builds
):
    print(f"Entered download and build for project: {name}")
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
    if ctx.cfg["build"]["keep_source_files"] == "False":
        # delete source folder
        shutil.rmtree(project["source"]["dir"], ignore_errors=True)
    print("| DONE building {}".format(name))

    # copy build artifacts to spcltorage server
    proj_build_dir = join(build_dir, basename(project["source"]["dir"]))
    ast_dir = join(target_dir, name, "AST")
    bitcodes_dir = join(target_dir, name, "bitcodes")
    # features_dir = join(target_dir, "features", name)

    if ctx.cfg["build"]["store_to_remote_server"] == "True":
        print(f"Storing project {name} artifacts to remote server...")
        nr_asts = send_to_remote_server(ctx, name, proj_build_dir, ast_dir, bitcodes_dir, project)
        if "build" in new_project:
            new_project["build"]["nr_asts"] = nr_asts
        
    if ctx.cfg["build"]["remove_local_artifacts"] == "True":
        print(f"Removing local artifacts of project {name}...")
        # shutil.rmtree(proj_build_dir, ignore_errors=True)
        # recursively delete files in the build folder except the logs
        # all_files = glob.glob(join(proj_build_dir, "**/*"), recursive = True)
        # all_files = recursively_get_files(proj_build_dir)
        all_files = os.listdir(proj_build_dir)
        for file in all_files:
            full_filename = join(proj_build_dir, file)
            if not os.path.exists(full_filename):
                continue
            if not full_filename.endswith(".log"):
                if isdir(full_filename):
                    shutil.rmtree(full_filename, ignore_errors=True)
                else:
                    os.remove(full_filename)
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

    previous_all_repositories = dict()
    if exists(os.path.join(build_dir, "all_built.json")):
        with open(os.path.join(build_dir, "all_built.json"), "r") as fin:
            previous_all_repositories = json.load(fin)
    
    
    if exists(os.path.join(build_dir, "intermediate_all_built.json")):
        with open(os.path.join(build_dir, "intermediate_all_built.json"), "r") as fin:
            temp_data = json.load(fin)
            previous_all_repositories.update(temp_data)
    
    # print(f"Builds left: {running_builds['builds_left']}")
    # print(f"Previous all repo: {json.dumps(previous_all_repositories, indent=2)}")
    with concurrent.futures.ProcessPoolExecutor(threads_count) as pool:
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

            projects_to_build = random.sample(list(repositories.items()), len(list(repositories.items())))
            projects_to_build = [(name, proj) for name, proj in projects_to_build if name not in previous_all_repositories] #TODO remove this in the end
            
            running_builds["builds_left"] = len(projects_to_build)
            
            futures = []
            idx_in_source = 0

            while len(futures) < min(threads_count, len(projects_to_build)) and idx_in_source < len(projects_to_build):
                name, proj = projects_to_build[idx_in_source]
                if name in previous_all_repositories:
                    idx_in_source += 1
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
                futures.append(future)
                idx += 1
                idx_in_source += 1
            
            while running_builds["builds_left"] > 0:
                completed_futures, _ = concurrent.futures.wait(futures, return_when=concurrent.futures.FIRST_COMPLETED)

                for future in completed_futures:
                    future_idx, future_name, future_project = future.result()
                    futures.remove(future)

                    all_repositories[future_name] = future_project
                    previous_all_repositories[future_name] = future_project
                    print(f"Got back the result of the {future_name} project future. Writing to file...", flush = True)

                    print(f"Writing intermediate_all_built to {os.path.join(build_dir, 'intermediate_all_built.json')}")
                    with open(os.path.join(build_dir, "intermediate_all_built.json"), "w") as o:
                        o.write(json.dumps(previous_all_repositories, indent = 2))

                    if running_builds["builds_left"] % 5 == 0:
                        print(f"Builds left: {running_builds['builds_left']}")

                    start_stats_update = time()
                    try:
                        print(f"[{future_idx}/{projects_count}] stats for {future_name}")
                        stats.update(future_project, future_name)
                    except Exception as e:
                        print("Error updating stats: {}".format(e))
                    
                    if not isdir(log_dir):
                        makedirs(log_dir)
                    timestamp = cfg["output"]["time"]
                    stats.save_rebuild_json(log_dir, timestamp)
                    stats.save_errors_json()
                    stats.save_errorstat_json(log_dir, timestamp)
                    stats.save_dependencies_json(log_dir, timestamp)
    
                    end_stats_update = time()
                    print(f"Stats update for {future_name} took {end_stats_update - start_stats_update} seconds")

                while idx_in_source < len(projects_to_build) and len(futures) < threads_count:
                    name, proj = projects_to_build[idx_in_source]
                    if name in previous_all_repositories:
                        idx_in_source += 1
                        idx += 1
                        running_builds["builds_left"] -= 1
                        continue
                    futures.append(pool.submit(
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
                    ))
                    idx += 1
                    idx_in_source += 1
                
    end = time()
    print("Process repositorites in %f [s]" % (end - start))
    start = time()
    
    with open(os.path.join(build_dir, "all_built.json"), "w") as o:
        o.write(json.dumps(previous_all_repositories, indent = 2))

    with open(os.path.join(build_dir, "current_build.json"), "w",) as o:
        o.write(json.dumps(all_repositories, indent=2))
        o.flush()

        saved = False
        tries = 0
        while saved and tries < 5:
            try:
                c = Connection(host = ctx.cfg["remote"]["host"], user = ctx.cfg["remote"]["user"])
                c.put(o.name, remote = f'{ctx.cfg["remote"]["artifacts_target_folder"]}/run_{ctx.cfg["output"]["time"]}/build_summary.json')
                saved = True
            except:
                tries += 1
                sleep(1)
        
        if saved is False:
            print("Failed to save build summary to remote storage server")

    # try:
    #     for (i, (name, proj)) in enumerate(all_repositories.items()):
    #         print("[{}/{}] stats for {}".format(i, projects_count, name))
    #         stats.update(proj, name)
    # except Exception as e:
    #     print("Error updating stats: {}".format(e))
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
