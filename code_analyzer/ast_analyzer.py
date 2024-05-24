import subprocess
import os
import docker
import io
import tarfile
import json
import tempfile
import copy
import string
import time
import concurrent.futures
import shutil
import traceback
import random
import sys

from os.path import abspath, join, exists, basename, dirname
from os import makedirs, mkdir
from glob import iglob
from sys import version_info
from time import sleep, time
from datetime import datetime, timedelta, timezone
from fabric import Connection
from multiprocessing import Manager

DOCKER_MOUNT_POINT = '/home/fba_code'

class Context:
    def __init__(self, cfg):
        self.cfg = cfg
        # self.stats = Statistics()
        # self.projects_count = projects_count
        self.timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")



    def set_loggers(self, out, err):
        self.out_log = out
        self.err_log = err

def initializer_func(ctx, f, args):
    # global init, loggers
    # if not init:
    #     init = True
    #     loggers = open_logfiles(ctx.cfg, getpid())
    #     for log in (loggers.stdout, loggers.stderr):
    #         log.set_counter(ctx.projects_count)
    #     ctx.set_loggers(loggers.stdout, loggers.stderr)
    # else:
    #     ctx.set_loggers(loggers.stdout, loggers.stderr)
    return f(*args)

def get_dockerfile(project_info, ctx):
    clang_version = ctx.cfg["analyze"]["clang_version"]
    # return "spcleth/fbacode:debian-bookworm-cxxlangstat-{}".format(clang_version)
    return "spcleth/fbacode:debian-bookworm-cxxlangstat-test-{}".format(clang_version)
    # if project_info["type"] == "debian":
        # return "spcleth/fbacode:debian-bookworm-cxxlangstat-{}".format(clang_version)
    # raise NotImplementedError("Dockerfile for {} not implemented".format(project_info["type"]))


def dump_logs(container, name, results_dir):
    docker_log = container.logs()
    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    docker_log_file = "container_{}_{}.log".format(
        name.replace("/", "_"), timestamp
    )
    with open(join(abspath(results_dir), docker_log_file), "w") as f:
        f.write(docker_log.decode())
    return docker_log_file


def start_docker(
    idx,
    project_name,
    project,
    ctx,
    results_dir,
    ast_archive,
    features_dir,
    dockerfile
):
    print(f"Entered start_docker for project {project_name}")
    try:
        docker_client = docker.from_env(timeout = 120)  # type: ignore
    except Exception as e:
        print(f"Failed to get docker client: {e}")
        print(f"TRACEBACK: {traceback.format_exc()}")
        return False
    docker_timeout = int(ctx.cfg["analyze"].get("docker_timeout", 30))
    tmp_file = tempfile.NamedTemporaryFile(mode="w")
    json.dump(
        {
            "idx": idx,
            "name": project_name,
            # "verbose": ctx.cfg["output"]["verbose"],
            "project": project,
        },
        tmp_file,
    )
    tmp_file.flush()
    volumes = {}
    # changed source to rw, need to write into for debian
    # since fetching happens in container
    # volumes[join(abspath(ast_archive), project_name + ".tar.gz")] = {
    volumes[join(abspath(ast_archive))] = {
        "mode": "rw",
        "bind": f"{DOCKER_MOUNT_POINT}/ast_archive",
    }
    volumes[abspath(results_dir)] = {"mode": "rw", "bind": f"{DOCKER_MOUNT_POINT}/analyze"}
    volumes[abspath(tmp_file.name)] = {
        "mode": "ro",
        "bind": f"{DOCKER_MOUNT_POINT}/input.json",
    }

    # TODO: this corresponds to the results_dir of builder.py
    # Make sure it is the same, instead of hardcoding it
    ast_dir = f"{DOCKER_MOUNT_POINT}/compiler_output/AST"
    environment = [
        "RESULTS_DIR={}".format(abspath(results_dir)),
        "AST_DIR={}".format(abspath(ast_dir)),
        "JOBS={}".format(str(ctx.cfg["analyze"]["jobs"])),
        "ANALYSES={}".format(str(ctx.cfg["analyze"]["analyses"])),
    ]

    print(f"Got dockerfile for project {project_name}, running container...")

    container_created = False
    container_run_fail = 0
    while not container_created and container_run_fail < 5:
        try:
            container = docker_client.containers.run(
                dockerfile,
                detach=True,
                environment=environment,
                volumes=volumes,
                auto_remove=False,
                remove=False,
                # mem_limit="3g"  # limit memory to 3GB to protect the host
            )
            container_created = True
        except Exception as e:
            container_run_fail += 1
            print(f"Failed {container_run_fail} times to create container for project {project_name}: {e}")
            print(f"TRACEBACK: {traceback.format_exc()}")
            try:
                container.remove(force = True)
            except:
                pass
            return False

    print(f"Created container {container.name} for project {project_name}")

    # wait for container to switch from create to running
    elapsed_time = 0
    wait_time = 3 # seconds
    reload_fail = 0
    while reload_fail < 3 and container.status == "created" and elapsed_time < docker_timeout * 60: # docker_timeout is in minutes
        sleep(wait_time)
        elapsed_time += wait_time
        try:
            container.reload()
            reload_fail = 0
        except Exception as e:
            reload_fail += 1
            print(f"container.reload failed (status = created) {reload_fail} times for container {container.name} project {project_name}")
            print(f"Reason: {e}")
            print(f"TRACEBACK: {traceback.format_exc()}")
    
    if reload_fail == 3:
        print(f"Failed to start container {container.name} for project {project_name}")
        container.remove(force = True) # force remove the container
        return False

    print(f"Started container {container.name} for {project_name}")
    
    while reload_fail < 3 and container.status == "running":
        timeout = datetime.now(timezone.utc) - timedelta(minutes = docker_timeout)
        logs = container.logs(since=timeout.timestamp(), tail=10)
        # ctx.out_log.print_info(idx, logs)
        if logs == b"":
            # ctx.out_log.print_info(idx, "stopping container, no progress in 30min")
            print(f"Stopping container {container.name} for project {project_name}, no progress in {docker_timeout} minutes")
            try:
                container.stop(timeout = 3)
            except Exception as e:
                print(f"Failed to stop container {container.name} for project {project_name}")
                print(f"Exception is: {e}")
                print(f"TRACEBACK: {traceback.format_exc()}")
            break
        sleep(10)
        try:
            container.reload()
            reload_fail = 0
        except Exception as e:
            reload_fail += 1
            print(f"container.reload failed (status = running) {reload_fail} times for container {container.name} project {project_name}")
            print(f"Reason: {e}")
            print(f"TRACEBACK: {traceback.format_exc()}")
    
    if reload_fail == 3:
        print(f"Failed to reload container {container.name} for project {project_name} {reload_fail} times in a row")
        container.remove(force = True)
        return False

    # just use this to get exit code. at this point, container.status != "running"
    try:
        return_code = container.wait(timeout = 10)
    except Exception as e:
        print(f"Container error happened during project {project_name}. Error: {e}")
        print(f"TRACEBACK: {traceback.format_exc()}")
        try:
            container.remove(force = True)
        except Exception as e:
            print(f"Failed to remove container {container.name} for project {project_name}")
            print(f"Exception is: {e}")
            print(f"TRACEBACK: {traceback.format_exc()}")
        return False

    if return_code["StatusCode"]:
        # the init.py or the docker container crashed unexpectadly
        # ctx.err_log.print_error(
        #     idx,
        #     "The analyze process failed! Return code {}, output: {}\n".format(
        #         return_code, container.logs(tail=10).decode("utf-8")
        #     ),
        # )
        
        docker_log_file = dump_logs(container, project_name, results_dir)
        project["status"] = "crash"
        project["crash_reason"] = "analyzer docker container crashed"
        container.remove(force = True)
        return False
    docker_log_file = dump_logs(container, project_name, results_dir)

    # Get output JSON
    try:
        binary_data, _ = container.get_archive(f"{DOCKER_MOUNT_POINT}/output.json")
        # with next(binary_data) not the whole thing is loaded if file is big
        bin = b"".join(list(binary_data))
        tar_file = tarfile.open(fileobj=io.BytesIO(bin))
        data = tar_file.extractfile(tar_file.getmember("output.json"))
        project.update(json.loads(data.read())["project"])

        # data.seek(0)
        # print(f"Contents of output.json: {json.loads(data.read())}")
    except Exception as e:
        # ctx.err_log.print_error(
        #     idx,
        #     "Failure retrieving the output json from docker:\n{}".format(str(e)),
        # )
        print(f"Exception happened when retrieving output from container {container.name} for project {project_name}: {e}")
        print(f"TRACEBACK: {traceback.format_exc()}")
        project["status"] = "crash"
        project["crash_reason"] = "docker output.json not found or invalid archive"
        container.remove(force = True)
        return False
    container.remove(force = True)

    if "analyze" not in project:
        project["analyze"] = {}
    project["analyze"]["docker_log"] = docker_log_file
    return True

def analyze_project(idx, path_to_collection, ast_archive_root, project_name, project, ctx):
    pass

def fetch_AST_and_analyze(idx, path_to_collection, ast_archive_root, results_dir_root, project_name, project, ctx):
    print(f"Analyzing {project_name}")

    results_dir = join(results_dir_root, project_name)
    if not exists(results_dir):
        mkdir(results_dir)
    ast_archive = join(ast_archive_root, project_name)
    if not exists(ast_archive):
        mkdir(ast_archive)
    # features_dir = join(results_dir, project_name)
    # if not exists(features_dir):
    #     mkdir(features_dir)
    features_dir = results_dir

    if not exists(join(ast_archive, project_name + '.tar.gz')):
        # copy the tar.gz from the remote server to local
        # TODO: also make it work if the artifacts are stored locally
        try:
            with Connection(host = 'spclstorage.inf.ethz.ch', user = ctx.cfg["analyze"]["user"], connect_timeout = 5) as conn:
                # print(f"Remote path: {join(path_to_collection, project_name + '.tar.gz')}")
                # print(f"Local path: {join(ctx.cfg['analyze']['ast_archive'], project_name, project_name + '.tar.gz')}")
                conn.get(remote = join(path_to_collection, project_name + '.tar.gz'), 
                        local = join(ast_archive, project_name + '.tar.gz'))
        except Exception as e:
            print(f"Failed to fetch {project_name} from storage server: {e}")
            print(f"TRACEBACK: {traceback.format_exc()}")
            # print(f"Remote path: {join(path_to_collection, project_name + '.tar.gz')}")
            # print(f"Local path: {join(ast_archive, project_name, project_name + '.tar.gz')}")
            project["analysis"] = "fetch fail"
            return project_name, project

    # start a docker machine and transfer the tar.gz to it
    print(f"Got the tar.gz for {project_name}, getting the dockerfile image now")
    
    try:
        dockerfile = get_dockerfile(project, ctx)
    except Exception as e:
        print(f"Failed to get dockerfile for {project_name}: {e}")
        print(f"TRACEBACK: {traceback.format_exc()}")
        project["analysis"] = "docker fail"
        return project_name, project
    # print(f"Got the dockerfile for {project_name}, starting docker now")
    docker_conf = {
        "results_dir": results_dir,
        "ast_archive": ast_archive,
        "features_dir": features_dir,
        "dockerfile": dockerfile,
    }
    print(f"Before starting docker, results_dir = {abspath(results_dir)}")
    try:
        result = start_docker(idx, project_name, project, ctx, **docker_conf)
    except Exception as e:
        print(f"Something went wrong in the docker for project {project_name}: {e}")
        print(f"TRACEBACK: {traceback.format_exc()}")
        project["analysis"] = "docker fail"
        result = False
    print(f"After exiting docker of {project_name}: {result}")

    # store the features locally or remotely? locally should be ok for now, they are not big, but should also make it so that they are sent to the storage server

    # remove the archive from local storage
    shutil.rmtree(ast_archive, ignore_errors=True)
    print(f"Removed ASTs of {project_name}")

    if result == False:
        shutil.rmtree(results_dir, ignore_errors=True)
        print(f"Removed results of {project_name}")
        project["analysis"] = "start_docker fail"
    else:
        project["analysis"] = "success"
    return project_name, project

def analyze_projects(path_to_collection, ast_archive_root, results_dir_root, projects_info, cfg):
    if not exists(ast_archive_root):
        mkdir(ast_archive_root)
    if not exists(results_dir_root):
        mkdir(results_dir_root)
    if not exists(join(results_dir_root, "analyze_summary.json")):
        with open(join(results_dir_root, "analyze_summary.json"), "w") as f:
            f.write(json.dumps({}))

    try:
        threads_count = int(cfg["docker"]["jobs"])
    except:
        threads_count = 1
    print(f"Number of docker containers: {threads_count}")

    ctx = Context(cfg)
    jobs_left = len(projects_info.keys())

    with open(join(results_dir_root, "analyze_summary.json"), "r") as f:
        analyze_summary = json.load(f)
    
    manager = Manager()
    # analyze_summary = manager.dict({})
    analyze_summary_lock = manager.Lock()

    # with open("cache_no_asts.json", "r") as fin:
    #     cache_no_asts = json.load(fin)

    with concurrent.futures.ProcessPoolExecutor(threads_count) as pool:
        futures = []
        start = time()


        projects_info_as_list = list(projects_info.items())
        print(f"len of projects info in the beginning: {len(projects_info_as_list)}")
        projects_info_as_list = [(pname, pp) for (pname, pp) in projects_info_as_list if "telegram" not in pname]
        projects_info_as_list = [(pname, pp) for (pname, pp) in projects_info_as_list if "trilinos" not in pname]
        projects_info_as_list = [(pname, pp) for (pname, pp) in projects_info_as_list if "ifcplus" not in pname]
        projects_info_as_list = [(pname, pp) for (pname, pp) in projects_info_as_list if "kicad" not in pname]
        projects_info_as_list = [(pname, pp) for (pname, pp) in projects_info_as_list if "quantlib" not in pname]
        projects_info_as_list = [(pname, pp) for (pname, pp) in projects_info_as_list if "cvc4" not in pname]
        projects_info_as_list = [(pname, pp) for (pname, pp) in projects_info_as_list if "gthumb" not in pname]
        projects_info_as_list = [(pname, pp) for (pname, pp) in projects_info_as_list if "meshlab" not in pname]

        projects_info_as_list = [(project_name, project) for (project_name, project) in projects_info_as_list if project["status"] == "success" and \
                    (project_name not in analyze_summary or analyze_summary[project_name]["analysis"] != "success")]
        
        # projects_info_as_list = [(pname, pp) for (pname, pp) in projects_info_as_list if "abseil" in pname]
        
        # projects_info_as_list = [(project_name, project) for (project_name, project) in projects_info_as_list if "nr_asts" in project["build"] and project["build"]["nr_asts"] > 0]
        # projects_info_as_list = [(project_name, project) for (project_name, project) in projects_info_as_list if "archive_size" in project and project["archive_size"] > 10 * 1024 * 1024 * 1024]

        random.shuffle(projects_info_as_list)
        jobs_left = len(projects_info_as_list)
        print(f"len of projects info: {len(projects_info_as_list)}")
        idx = 0
        while len(futures) < min(threads_count, len(projects_info_as_list)):
            if idx >= len(projects_info_as_list):
                break
            project_name, project = projects_info_as_list[idx]
            # if "nr_asts" in project["build"] and project["build"]["nr_asts"] == 0:
            #     print(f"Project {project_name} has no ASTs, skipping")
            #     idx += 1
            #     jobs_left -= 1
            #     continue
            futures.append(pool.submit(
                initializer_func,
                ctx,
                fetch_AST_and_analyze,
                (
                    idx,
                    path_to_collection,
                    ast_archive_root,
                    results_dir_root,
                    project_name,
                    project,
                    ctx
                ),
            ))
            idx += 1
            sleep(0.5) # each fetch runs an ssh connection to the storage server. too many connections at once cause the server to refuse the connection

        # incomplete_futures = True
        # when one finishes, increment counter and add a new one to the queue
        while jobs_left > 0:
            completed_futures, _ = concurrent.futures.wait(futures, return_when=concurrent.futures.FIRST_COMPLETED)

            for future in completed_futures:
                project_name, project = future.result()
                futures.remove(future)

                analyze_summary[project_name] = project

                with open(join(results_dir_root, "analyze_summary.json"), "w") as f:
                    f.write(json.dumps(analyze_summary, indent=2))

                jobs_left -= 1
                if jobs_left % 5 == 0:
                    print(f"{jobs_left} analysis jobs left")
            
            while idx < len(projects_info_as_list) and len(futures) < threads_count:
                project_name, project = projects_info_as_list[idx]
                # if "nr_asts" in project["build"] and project["build"]["nr_asts"] == 0:
                #     print(f"Project {project_name} has no ASTs, skipping")
                #     idx += 1
                #     jobs_left -= 1
                #     continue
                futures.append(pool.submit(
                    initializer_func,
                    ctx,
                    fetch_AST_and_analyze,
                    (
                        idx,
                        path_to_collection,
                        ast_archive_root,
                        results_dir_root,
                        project_name,
                        project,
                        ctx
                    ),
                ))
                idx += 1
                sleep(0.5) # each fetch runs an ssh connection to the storage server. too many connections at once cause the server to refuse the connection
        end = time()

        # saving the results
        with open(join(results_dir_root, "analyze_summary.json"), "w") as f:
            f.write(json.dumps(analyze_summary, indent=2))

        print(f"Analyzed {len(projects_info_as_list)} projects in {end - start} [s]")
