import subprocess
import os
import docker
import io
import tarfile
import json
import tempfile
import re

from os.path import abspath, join, exists, basename
from os import mkdir
from glob import iglob
# from re import search
from subprocess import PIPE
from sys import version_info
from time import sleep, time
from datetime import datetime, timedelta
from requests.exceptions import Timeout

from . import cmake, debian, autotools, make, travis, github_actions, circleci


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
    "travis": travis.Project,
    "circleci": circleci.Project,
    "github_actions": github_actions.Project
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
            json.dump({
                "idx": idx,
                "name": name,
                "verbose": ctx.cfg["output"]["verbose"]
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
                "BITCODES_DIR={}".format(abspath(target_dir))
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
            # TODO: maybe configure a timeout?
            # TODO: do a loop and check if the docker exited and check the logs
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
                    "The build process failed! Return code {}, output: \n".format(
                        return_code)
                )
                docker_log = container.logs()
                timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
                docker_log_file = "container_{}_{}.log".format(name.replace("/", "_"), timestamp)
                with open(join(abspath(build_dir), docker_log_file), "w") as f:
                    f.write(docker_log.decode())
                project["status"] = "crash"
                return (idx, name, project)
            docker_log = container.logs()
            timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
            docker_log_file = "container_{}_{}.log".format(name.replace("/", "_"), timestamp)
            with open(join(abspath(build_dir), docker_log_file), "w") as f:
                f.write(docker_log.decode())
            # Get output JSON
            binary_data, _ = container.get_archive(
                "/home/fba_code/output.json")
            tar_file = tarfile.open(fileobj=io.BytesIO(next(binary_data)))
            data = tar_file.extractfile(tar_file.getmember("output.json"))
            project = {**project, **json.loads(data.read())["project"]}
            end = time()
            project["build"]["time"] = end - start

            container.remove()

            # Generate summary and stats data
            
            project["build"]["docker_log"] = docker_log_file
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
    else:
        project["build"]["time"] = end - start
    return (idx, name, project)
