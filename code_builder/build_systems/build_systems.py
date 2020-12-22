import subprocess
import os
import docker
import io
import tarfile
import json
import tempfile
import copy

from os.path import abspath, join, exists, basename, dirname
from os import mkdir
from glob import iglob
from sys import version_info
from time import sleep, time
from datetime import datetime, timedelta

from . import cmake, debian, autotools, make
from ..ci_systems import travis, circle_ci, gh_actions, debian_install


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
    "debian_install": debian_install.CiSystem,
    "gh_actions": gh_actions.CiSystem,
    "travis": travis.CiSystem,
    "circle_ci": circle_ci.CiSystem,
}

# if any of these, do a build without installing first, then install in second build
double_build_ci = {"travis", "gh_actions", "debian_install"}


def recognize_and_build(idx, name, project, build_dir, target_dir, ctx, stats=None):

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
    ci_system = "unrecognized"
    ci_dockerfile = False
    project.setdefault("ci_systems", [])
    for ci_name, system in ci_systems.items():
        if system.recognize(source_dir):
            if ci_system == "unrecognized":
                ci_system = ci_name
                ci_dockerfile = system.get_docker_image(
                    source_dir, ctx.cfg["build"]["clang_version"]
                )
            if ci_name not in project["ci_systems"]:
                project["ci_systems"].append(ci_name)
    for build_name, build_system in build_systems.items():
        if build_system.recognize(source_dir):
            project["build_system"] = build_name.lower()
            # priority is on CI dockerfile, except for debian. debian needs its special
            # container with source URIs in the /etc/sources.list
            # do workaround for now, don't know what an elegant solution would be
            if ci_dockerfile:
                dockerfile = ci_dockerfile
            else:
                dockerfile = build_system.get_docker_image(
                    source_dir, ctx.cfg["build"]["clang_version"]
                )
            build_dir = join(build_dir, source_name)
            target_dir = join(target_dir, source_name)
            if not exists(build_dir):
                mkdir(build_dir)
            docker_client = docker.from_env()  # type: ignore
            tmp_file = tempfile.NamedTemporaryFile(mode="w")
            # do not install dpendencies the first time around
            if ci_system in double_build_ci:
                project["install_deps"] = False
                project["is_first_build"] = True
            else:
                project["install_deps"] = True
            json.dump(
                {
                    "idx": idx,
                    "name": name,
                    "verbose": ctx.cfg["output"]["verbose"],
                    "project": project,
                },
                tmp_file,
            )
            tmp_file.flush()
            volumes = {}
            # changed source to rw, need to write into for debian
            # since fetching happens in container
            volumes[abspath(source_dir)] = {
                "mode": "rw",
                "bind": "/home/fba_code/source",
            }
            volumes[dirname(__file__) + "/../dep_mapping.json"] = {
                "mode": "ro",
                "bind": "/home/fba_code/dep_mapping.json",
            }
            volumes[abspath(build_dir)] = {"mode": "rw", "bind": "/home/fba_code/build"}
            volumes[abspath(target_dir)] = {
                "mode": "rw",
                "bind": "/home/fba_code/bitcodes",
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
                "SKIP_BUILD={}".format(str(ctx.cfg["build"]["skip_build"])),
                "JOBS={}".format(str(ctx.cfg["build"]["jobs"])),
            ]
            container = docker_client.containers.run(
                dockerfile,
                detach=True,
                # name="{}_{}".format(name, build_name),
                environment=environment,
                volumes=volumes,
                auto_remove=False,
                remove=False,
                # mem_limit="3g"  # limit memory to 3GB to protect the host
            )
            if project.get("is_first_build", False):
                ctx.out_log.print_info(
                    idx,
                    "1/2 building {} in container {} as {} and {}\n    dockerfile:{}".format(
                        name, container.name, build_name, ci_system, dockerfile
                    ),
                )
            else:
                ctx.out_log.print_info(
                    idx,
                    "building {} in container {} as {} and {}\n    dockerfile:{}".format(
                        name, container.name, build_name, ci_system, dockerfile
                    ),
                )
            sleep(10)
            container.reload()
            while container.status == "running":
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
                        return_code, container.logs(tail=10).decode("utf-8")
                    ),
                )
                docker_log = container.logs()
                timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
                docker_log_file = "container_{}_{}.log".format(
                    name.replace("/", "_"), timestamp
                )
                with open(join(abspath(build_dir), docker_log_file), "w") as f:
                    f.write(docker_log.decode())
                project["status"] = "crash"
                project["crash_reason"] = "docker container crashed"
                return (idx, name, project)
            docker_log = container.logs()
            timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
            docker_log_file = "container_{}_{}.log".format(
                name.replace("/", "_"), timestamp
            )
            with open(join(abspath(build_dir), docker_log_file), "w") as f:
                f.write(docker_log.decode())
            # Get output JSON
            try:
                binary_data, _ = container.get_archive("/home/fba_code/output.json")
                # with next(binary_data) not the whole thing is loaded if file is big
                bin = b"".join(list(binary_data))
                tar_file = tarfile.open(fileobj=io.BytesIO(bin))
                data = tar_file.extractfile(tar_file.getmember("output.json"))
                project = {**project, **json.loads(data.read())["project"]}
            except Exception as e:
                ctx.err_log.print_error(
                    idx,
                    "Failure retrieving the Project File from docker (1/2):\n{}".format(
                        str(e)
                    ),
                )
                project["status"] = "crash"
                project[
                    "crash_reason"
                ] = "docker output.json not found or invalid archive"
                return (idx, name, project)
            end = time()
            project["build"]["time"] = end - start

            container.remove()
            project["build"]["docker_log"] = docker_log_file
            # if we have a build system that can install packages, rerun with packages
            # at the moment only travis, can be expended..
            if ci_system in double_build_ci:
                stats.update(project, name)
                project["first_build"] = copy.deepcopy(project["build"])
                project["install_deps"] = True
                project["build"] = {}
                project["double_build"] = True
                project["is_first_build"] = False
                volumes.pop(abspath(tmp_file.name))
                tmp_file.close()
                tmp_file = tempfile.NamedTemporaryFile(mode="w")
                # rerun the same container but with installing deps
                json.dump(
                    {
                        "idx": idx,
                        "name": name,
                        "verbose": ctx.cfg["output"]["verbose"],
                        "project": project,
                    },
                    tmp_file,
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
                    "SKIP_BUILD={}".format(str(ctx.cfg["build"]["skip_build"])),
                    "JOBS={}".format(str(ctx.cfg["build"]["jobs"])),
                ]
                container = docker_client.containers.run(
                    dockerfile,
                    detach=True,
                    # name="{}_{}".format(name, build_name),
                    environment=environment,
                    volumes=volumes,
                    auto_remove=False,
                    remove=False,
                    # mem_limit="3g"  # limit memory to 3GB to protect the host
                )
                ctx.out_log.print_info(
                    idx,
                    "2/2 building {} in container {} as {}".format(
                        name, container.name, build_name
                    ),
                )
                sleep(10)
                container.reload()
                while container.status == "running":
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
                            return_code, container.logs(tail=10).decode()
                        ),
                    )
                    docker_log = container.logs()
                    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
                    docker_log_file = "container_{}_{}.log".format(
                        name.replace("/", "_"), timestamp
                    )
                    with open(join(abspath(build_dir), docker_log_file), "w") as f:
                        f.write(docker_log.decode())
                    project["status"] = "crash"
                    project["crash_reason"] = "docker container crashed"
                    end = time()
                    project["build"]["time"] = end - start
                    return (idx, name, project)
                docker_log = container.logs()
                timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
                docker_log_file = "container_{}_{}.log".format(
                    name.replace("/", "_"), timestamp
                )
                with open(join(abspath(build_dir), docker_log_file), "w") as f:
                    f.write(docker_log.decode())
                # Get output JSON
                try:
                    binary_data, _ = container.get_archive("/home/fba_code/output.json")
                    # maybe if bigger than chunk this fails??
                    # with next(binary_data) not the whole thing is loaded if file is big
                    bin = b"".join(list(binary_data))
                    tar_file = tarfile.open(fileobj=io.BytesIO(bin))
                    data = tar_file.extractfile(tar_file.getmember("output.json"))
                    project = {**project, **json.loads(data.read())["project"]}
                except Exception as e:
                    ctx.err_log.print_error(
                        idx,
                        "Failure retrieving the Project File from docker:\n{}".format(
                            str(e)
                        ),
                    )
                    project["status"] = "crash"
                    project[
                        "crash_reason"
                    ] = "docker output.json not found or invalid archive"
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
                        "{0}/**/*.bc".format(project["bitcodes"]["dir"]), recursive=True
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
