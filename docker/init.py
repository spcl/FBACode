# from code_builder.ci_systems.apt_install import Installer
import sys
import os
import importlib
import glob
import subprocess
from subprocess import PIPE
import json

from time import time
from shutil import move, copyfile
from datetime import datetime

from ci_systems.apt_install import Installer  # type: ignore  we are in docker

# paths are different indide docker
from utils.driver import open_logfiles  # type: ignore
from build_systems.utils import run  # type: ignore

DOCKER_MOUNT_POINT = "/home/fba_code"


class Context:
    def __init__(self, cfg):
        self.cfg = cfg

    def set_loggers(self, out, err):
        self.out_log = out
        self.err_log = err


def print_section(idx, ctx, message):
    hashtags = "#" * (len(message) + 4)
    to_print = "\n{0}\n# {1} #\n{0}".format(hashtags, message)
    ctx.err_log.print_info(idx, to_print)
    ctx.out_log.print_info(idx, to_print)
    print(to_print)


source_dir = f"{DOCKER_MOUNT_POINT}/source"
build_dir = f"{DOCKER_MOUNT_POINT}/build"
bitcodes_dir = f"{DOCKER_MOUNT_POINT}/bitcodes"
ast_dir = f"{DOCKER_MOUNT_POINT}/AST"
# features_dir = f"{DOCKER_MOUNT_POINT}/features"
dependency_map = f"{DOCKER_MOUNT_POINT}/dep_mapping.json"
build_system = os.environ.get("BUILD_SYSTEM", "")
ci_system = os.environ.get("CI_SYSTEM", "")
external_build_dir = os.environ.get("BUILD_DIR", "")
external_bitcodes_dir = os.environ.get("BITCODES_DIR", "")
external_ast_dir = os.environ.get("AST_DIR")
# external_features_dir = os.environ.get("FEATURES_DIR")
install_deps = not (os.environ.get("DEPENDENCY_INSTALL", "") == "False")
skip_build = os.environ.get("SKIP_BUILD", "") == "True"

json_input = json.load(open(sys.argv[1], "r"))
idx = json_input["idx"]
name = json_input["name"]
verbose = json_input["verbose"]
builder_mod = importlib.import_module("build_systems.{}".format(build_system))
ci_mod = importlib.import_module("ci_systems.{}".format(ci_system))
builder_class = getattr(builder_mod, "Project")
ci_class = getattr(ci_mod, "CiSystem")

print("Building {} in here using {} and {}".format(name, build_system, ci_system))
print("python version: {}".format(sys.version))

# directories to be chowned in the end
chown_dirs = [build_dir, source_dir]

cfg = {"output": {"verbose": verbose, "file": f"{DOCKER_MOUNT_POINT}/"}}
ctx = Context(cfg)
timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
loggers = open_logfiles(cfg, name.replace("/", "_"), timestamp=timestamp)
ctx.set_loggers(loggers.stdout, loggers.stderr)
# save all installed packages, to get the difference later (newly installed deps)
# assusmes we run debian or ubuntu, maybe put into library in the future
out = run(["dpkg", "--get-selections"], stderr=PIPE, stdout=PIPE)
preinstalled_pkgs = out.stdout.splitlines()
preinstalled_pkgs = [
    i.replace("install", "").strip() for i in preinstalled_pkgs if "deinstall" not in i
]

# Updated -> Configure
project = {
    "status": "configure",
    "build": {
        "dir": external_build_dir,
        "stdout": os.path.basename(loggers.stdout_file),
        "stderr": os.path.basename(loggers.stderr_file),
        "installed": [],
        "-j": os.environ.get("JOBS", 1),
    },
}

if "folder" in json_input["project"]:
    project["build"]["folder"] = json_input["project"]["folder"]
if "version" in json_input["project"]:
    project["build"]["version"] = json_input["project"]["version"]

builder = builder_class(source_dir, build_dir, idx, ctx, name, project)
ci = ci_class(source_dir, build_dir, idx, ctx, name, project, builder.COPY_SRC_TO_BUILD)
start = time()
copied_src = builder.copy_src()
end = time()
copy_time = end - start
if copied_src and install_deps:
    print_section(idx, ctx, "installing dependencies with {}".format(ci_system))
    # by default, get dependencies with ci system
    start = time()
    success = ci.install(builder=builder)
    if not success:
        print("failed installation using {}".format(ci_system))
        project["build"]["install"] = "fail"
    else:
        project["build"]["install"] = ci_system
    end = time()
    project["build"]["install_time"] = end - start
    print_section(idx, ctx, "done installing dependencies")
    # check if there are missing dependencies fields in the project file
    if "missing_deps" in json_input["project"]:
        print_section(idx, ctx, "installing missing dependencies from prev. build")
        installer = Installer(
            source_dir,
            build_dir,
            idx,
            ctx,
            name,
            project,
            dependency_map,
            json_input["project"]["missing_deps"],
        )
        installer.install()
        print_section(idx, ctx, "done installing dependencies from prev. build")

start = time()
print_section(idx, ctx, "starting configuration")
configured = builder.configure(build_dir)
end = time()
project["build"]["configure_time"] = end - start + copy_time
start = time()
if not configured:
    project["build"]["configure"] = "fail"
    failure = True
    print_section(idx, ctx, "configuration failed")
    end = time()
elif not copied_src:
    project["build"]["configure"] = "fail"
    failure = True
    print_section(idx, ctx, "copy_src failed")
    end = time()
else:
    print_section(idx, ctx, "configuration succeeded, starting build")
    project["build"]["configure"] = "success"
    # Configure -> Build
    project["status"] = "build"
    if skip_build:
        project["status"] = "success"
        project["build"]["build"] = "skipped"
        project["skipped_build"] = True
        print_section(idx, ctx, "skipping build")
        end = time()
    else:
        project["skipped_build"] = False
        if not builder.build():
            ci_build = getattr(ci, "build", None)
            # we try to use the ci system to build
            if callable(ci_build):
                print_section(idx, ctx, "trying ci build")
                if ci.build():
                    print_section(idx, ctx, "ci build success!")
                    project["status"] = "success"
                    project["build"]["build"] = "success"
                else:
                    print_section(idx, ctx, "ci build failed too")
                    project["build"]["build"] = "fail"
                    project["status"] = "fail"
                    failure = True
            else:
                print_section(idx, ctx, "build failed")
                project["build"]["build"] = "fail"
                project["status"] = "fail"
                failure = True
            end = time()
        else:
            end = time()
            print_section(idx, ctx, "build success!")
            project["status"] = "success"
            project["build"]["build"] = "success"
        if os.environ.get("SAVE_IR") != "False":
            project["bitcodes"] = {"dir": external_bitcodes_dir}
            builder.generate_bitcodes(bitcodes_dir)
            chown_dirs.append(bitcodes_dir)
        if os.environ.get("SAVE_AST") != "False":
            project["ast_files"] = {"dir": external_ast_dir}
            builder.generate_ast(ast_dir)
            chown_dirs.append(ast_dir)
project["build"]["build_time"] = end - start
ctx.out_log.print_info(idx, "Finish processing %s in %f [s]" % (name, end - start))

# get installed packages after build
out = run(["dpkg", "--get-selections"], stderr=PIPE, stdout=PIPE)
installed_pkgs = out.stdout.splitlines()
installed_pkgs = [
    i.replace("install", "").strip() for i in installed_pkgs if "deinstall" not in i
]
new_pkgs = list(set(installed_pkgs) - set(preinstalled_pkgs))
project["build"]["installed"].extend(new_pkgs)

if builder.temp_build_dir is not None:
    project["build"]["temp_build_dir"] = builder.temp_build_dir

out = {"idx": idx, "name": name, "project": project}
# save output JSON
with open("output.json", "w") as f:
    json.dump(out, f, indent=2)


# move logs to build directory
for file in glob.glob("*.log"):
    move(file, build_dir)
copyfile("output.json", os.path.join(build_dir, "output.json"))

# change the user and group to the one of the host, since we are root
host_uid = os.stat(build_dir).st_uid
host_gid = os.stat(build_dir).st_gid

for d in set(chown_dirs):
    print("chowning {}...".format(d))
    out = subprocess.run(["chown", "-R", "{}:{}".format(host_uid, host_gid), d])
    if out.returncode != 0:
        print(out)
