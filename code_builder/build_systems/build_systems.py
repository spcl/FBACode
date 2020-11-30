import subprocess
import os
import docker
import io
import tarfile
import json
import tempfile
import re
import copy

from os.path import abspath, join, exists, basename
from os import mkdir
from glob import iglob
# from re import search
from subprocess import PIPE
from sys import version_info
from time import sleep, time
from datetime import datetime, timedelta
from requests.exceptions import Timeout

from . import cmake, debian, autotools, make  #, travis, github_actions, circleci
from ..ci_systems import travis, circle_ci, gh_actions
from .. import dep_finder, statistics


def run(command, cwd=None, stdout=None, stderr=None):

    # Python 3.5+ - subprocess.run
    # older - subprocess.call
    # TODO: capture_output added in 3.7 - verify it works
    if version_info.major >= 3 and version_info.minor >= 5:
        return subprocess.run(command, cwd=cwd, stdout=stdout, stderr=stderr)
    else:
        return subprocess.call(command, cwd=cwd, stdout=stdout, stderr=stderr)


build_systems = {
    "debian": debian.Project,
    "CMake": cmake.Project,
    "make": make.Project,
    "Autotools": autotools.Project,
    # "travis": travis.Project,
    # "circleci": circleci.Project,
    # "github_actions": github_actions.Project
    }

# continuous integration systems, decreasing priority
ci_systems = {
    "travis": travis.CiSystem,
    "circle_ci": circle_ci.CiSystem,
    "gh_actions": gh_actions.CiSystem
}


def recognize_and_build(idx, name, project, build_dir, target_dir, ctx):

    if project["status"] == "unrecognized":
        ctx.stats.unrecognized()
    if "build" in project:
        # update if needed
        return (idx, name, project)
    source_dir = project["source"]["dir"]
    source_name = basename(source_dir)
    failure = False
    start = time()
    # find out the used ci system
    ci_system = "None"
    project.setdefault("ci_systems", [])
    for ci_name, system in ci_systems.items():
        if system.recognize(source_dir):
            if ci_system == "None":
                ci_system = ci_name
            if ci_name not in project["ci_systems"]:
                project["ci_systems"].append(ci_name)
    for build_name, build_system in build_systems.items():
        if build_system.recognize(source_dir):
            project["build_system"] = build_name.lower()
            # print("{} recognized as {}".format(name, build_name))
            
            build_dir = join(build_dir, source_name)
            target_dir = join(target_dir, source_name)
            if not exists(build_dir):
                mkdir(build_dir)
            docker_client = docker.from_env()
            tmp_file = tempfile.NamedTemporaryFile(mode="w")
            # do not install dpendencies the first time around
            if ci_system == "travis":
                project["install_deps"] = False
            else:
                project["install_deps"] = True
            json.dump({
                "idx": idx,
                "name": name,
                "verbose": ctx.cfg["output"]["verbose"],
                "project": project
            },
                tmp_file.file,
            )
            tmp_file.flush()
            volumes = {}
            # changed source to rw, need to write into for debian
            # since fetching happens in container
            volumes[abspath(source_dir)] = {
                "mode": "rw",
                "bind": "/home/fba_code/source",
            }
            volumes[abspath(build_dir)] = {
                "mode": "rw",
                "bind": "/home/fba_code/build"
            }
            volumes[abspath(target_dir)] = {
                "mode": "rw",
                "bind": "/home/fba_code/bitcodes"
            }
            volumes[abspath(tmp_file.name)] = {
                "mode": "ro",
                "bind": "/home/fba_code/input.json",
            }
            environment = [
                "BUILD_SYSTEM={}".format(build_name.lower()),
                "BUILD_DIR={}".format(abspath(build_dir)),
                "BITCODES_DIR={}".format(abspath(target_dir)),
                "CI_SYSTEM={}".format(ci_system),
                "DEPENDENCY_INSTALL={}".format(str(project["install_deps"])),
                "SKIP_BUILD={}".format(str(ctx.cfg["build"]["skip_build"]))
            ]
            container = docker_client.containers.run(
                build_system.CONTAINER_NAME,
                detach=True,
                # name="{}_{}".format(name, build_name),
                environment=environment,
                volumes=volumes,
                auto_remove=False,
                remove=False,
                # mem_limit="3g"  # limit memory to 3GB to protect the host
            )
            ctx.out_log.print_info(
                idx, "building {} in container {} as {}".format(name, container.name, build_name))
            sleep(10)
            container.reload()
            while(container.status == "running"):
                # get the current time of the container, can differ from host bc timezone
                # time = container.stats(stream=False)["read"]
                # try with utc time, should be faster
                # TODO: make timeout configurable
                timeout = datetime.utcnow() - timedelta(minutes=30)
                logs = container.logs(since=timeout, tail=1)
                # ctx.out_log.print_info(idx, logs)
                if logs == b"":
                    container.stop(timeout=3)
                sleep(10)
                container.reload()
            # just use this to get exit code
            return_code = container.wait()
            if return_code["StatusCode"]:
                # the init.py or the docker container crashed unexpectadly
                ctx.err_log.print_error(
                    idx,
                    "The build process failed! Return code {}, output: {}\n".format(
                        return_code, container.logs(tail=10))
                )
                docker_log = container.logs()
                timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
                docker_log_file = "container_{}_{}.log".format(name.replace("/", "_"), timestamp)
                with open(join(abspath(build_dir), docker_log_file), "w") as f:
                    f.write(docker_log.decode())
                project["status"] = "crash"
                project["crash_reason"] = "docker container crashed"
                return (idx, name, project)
            docker_log = container.logs()
            timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
            docker_log_file = "container_{}_{}.log".format(name.replace("/", "_"), timestamp)
            with open(join(abspath(build_dir), docker_log_file), "w") as f:
                f.write(docker_log.decode())
            # Get output JSON
            try:
                binary_data, _ = container.get_archive(
                    "/home/fba_code/output.json")
                tar_file = tarfile.open(fileobj=io.BytesIO(next(binary_data)))
                data = tar_file.extractfile(tar_file.getmember("output.json"))
                project = {**project, **json.loads(data.read())["project"]}
            except Exception as e:
                ctx.err_log.print_error(
                    idx,
                    "Failure retrieving the Project File from docker:\n{}".format(str(e))
                )
                project["status"] = "crash"
                project["crash_reason"] = "docker output.json not found or invalid archive"
                return (idx, name, project)
            end = time()
            project["build"]["time"] = end - start

            container.remove()
            project["build"]["docker_log"] = docker_log_file
            # if we have a build system that can install packages, rerun with packages
            # at the moment only travis
            if ci_system == "travis":
                stat = statistics.Statistics(0)
                stat.update(project, name)
                finder = dep_finder.DepFinder()
                missing = finder.analyze_logs(project, name)
                project["first_build"] = copy.deepcopy(project["build"])
                project["first_build"]["missing"] = missing
                project["install_deps"] = True
                project["double_build"] = True
                project["build"] = {}
                volumes.pop(abspath(tmp_file.name))
                tmp_file.close()
                tmp_file = tempfile.NamedTemporaryFile(mode="w")
                # rerun the same container but with installing deps
                json.dump({
                    "idx": idx,
                    "name": name,
                    "verbose": ctx.cfg["output"]["verbose"],
                    "project": project
                },
                    tmp_file.file,
                )
                tmp_file.flush()
                volumes[abspath(tmp_file.name)] = {
                    "mode": "ro",
                    "bind": "/home/fba_code/input.json",
                }
                environment = [
                    "BUILD_SYSTEM={}".format(build_name.lower()),
                    "BUILD_DIR={}".format(abspath(build_dir)),
                    "BITCODES_DIR={}".format(abspath(target_dir)),
                    "CI_SYSTEM={}".format(ci_system),
                    "DEPENDENCY_INSTALL={}".format(str(project["install_deps"])),
                    "SKIP_BUILD={}".format(str(ctx.cfg["build"]["skip_build"]))
                ]
                container = docker_client.containers.run(
                    build_system.CONTAINER_NAME,
                    detach=True,
                    # name="{}_{}".format(name, build_name),
                    environment=environment,
                    volumes=volumes,
                    auto_remove=False,
                    remove=False,
                    # mem_limit="3g"  # limit memory to 3GB to protect the host
                )
                ctx.out_log.print_info(
                    idx, "2nd time building {} in container {} as {}".format(name, container.name, build_name))
                sleep(10)
                container.reload()
                while(container.status == "running"):
                    # get the current time of the container, can differ from host bc timezone
                    # time = container.stats(stream=False)["read"]
                    # try with utc time, should be faster
                    # TODO: make timeout configurable
                    timeout = datetime.utcnow() - timedelta(minutes=30)
                    logs = container.logs(since=timeout, tail=1)
                    # ctx.out_log.print_info(idx, logs)
                    if logs == b"":
                        container.stop(timeout=3)
                    sleep(10)
                    container.reload()
                # just use this to get exit code
                return_code = container.wait()
                if return_code["StatusCode"]:
                    # the init.py or the docker container crashed unexpectadly
                    ctx.err_log.print_error(
                        idx,
                        "The build process failed! Return code {}, output: {}\n".format(
                            return_code, container.logs(tail=10))
                    )
                    docker_log = container.logs()
                    timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
                    docker_log_file = "container_{}_{}.log".format(name.replace("/", "_"), timestamp)
                    with open(join(abspath(build_dir), docker_log_file), "w") as f:
                        f.write(docker_log.decode())
                    project["status"] = "crash"
                    project["crash_reason"] = "docker container crashed"
                    end = time()
                    project["build"]["time"] = end - start
                    return (idx, name, project)
                docker_log = container.logs()
                timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
                docker_log_file = "container_{}_{}.log".format(name.replace("/", "_"), timestamp)
                with open(join(abspath(build_dir), docker_log_file), "w") as f:
                    f.write(docker_log.decode())
                # Get output JSON
                try:
                    binary_data, _ = container.get_archive(
                        "/home/fba_code/output.json")
                    tar_file = tarfile.open(fileobj=io.BytesIO(next(binary_data)))
                    data = tar_file.extractfile(tar_file.getmember("output.json"))
                    project = {**project, **json.loads(data.read())["project"]}
                except Exception as e:
                    ctx.err_log.print_error(
                        idx,
                        "Failure retrieving the Project File from docker:\n{}".format(str(e))
                    )
                    project["status"] = "crash"
                    project["crash_reason"] = "docker output.json not found or invalid archive"
                    end = time()
                    project["build"]["time"] = end - start
                    return (idx, name, project)
                end = time()
                project["build"]["time"] = end - start

                container.remove()
                
                # do the comparison of missing deps and installed packages in statistics

                project["build"]["docker_log"] = docker_log_file
            # Generate summary and stats data
            if "bitcodes" in project:
                bitcodes = [
                    x
                    for x in iglob(
                        "{0}/**/*.bc".format(project["bitcodes"]["dir"]),
                        recursive=True
                    )
                ]
                size = sum(os.path.getsize(x) for x in bitcodes)
                project["bitcodes"]["files"] = len(bitcodes)
                project["bitcodes"]["size"] = size

            ctx.out_log.print_info(
                idx, "Finish processing %s in %f [s]" % (name, end - start)
            )
            return (idx, name, project)
    end = time()
    # nothing matched
    if not failure:
        ctx.out_log.print_info(
            idx, "Unrecognized project %s in %s" % (name, source_dir)
        )
        project["status"] = "unrecognized"
        # 
    else:
        project["build"]["time"] = end - start
    return (idx, name, project)
