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


source_dir = "/home/fba_code/source"
build_dir = "/home/fba_code/build"
bitcodes_dir = "/home/fba_code/bitcodes"
dependency_map = "/home/fba_code/dep_mapping.json"
build_system = os.environ["BUILD_SYSTEM"]
ci_system = os.environ["CI_SYSTEM"]
external_build_dir = os.environ["BUILD_DIR"]
external_bitcodes_dir = os.environ["BITCODES_DIR"]
install_deps = not os.environ["DEPENDENCY_INSTALL"] == "False"
skip_build = os.environ["SKIP_BUILD"] == "True"

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
chown_dirs = [build_dir]

cfg = {"output": {"verbose": verbose, "file": "/home/fba_code/"}}
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
    },
}

builder = builder_class(source_dir, build_dir, idx, ctx, name, project)
if install_deps:
    print_section(idx, ctx, "insalling dependencies with {}".format(ci_system))

    # by default, get dependencies with ci system
    ci = ci_class(source_dir, build_dir, idx, ctx, name, project)
    start = time()
    success = ci.install()
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
project["build"]["configure_time"] = end - start
start = time()
if not configured:
    project["build"]["configure"] = "fail"
    failure = True
    print_section(idx, ctx, "configuration failed")
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
    else:
        project["skipped_build"] = False
        if not builder.build():
            print_section(idx, ctx, "build failed")
            project["build"]["build"] = "fail"
            project["status"] = "fail"
            failure = True
        else:
            print_section(idx, ctx, "build success!")
            project["status"] = "success"
            project["build"]["build"] = "success"
            if os.environ.get("save_ir") != "False":
                project["bitcodes"] = {"dir": external_bitcodes_dir}
                builder.generate_bitcodes(bitcodes_dir)
                chown_dirs.append(bitcodes_dir)
            if os.environ.get("save_ast") != "False":
                project["ast_files"] = {
                    "dir": os.path.join(external_bitcodes_dir, "AST")
                }
                builder.generate_ast(os.path.join(bitcodes_dir, "AST"))
                chown_dirs.append(bitcodes_dir)
project["build"]["time"] = end - start
ctx.out_log.print_info(idx, "Finish processing %s in %f [s]" % (name, end - start))

# get installed packages after build
out = run(["dpkg", "--get-selections"], stderr=PIPE, stdout=PIPE)
installed_pkgs = out.stdout.splitlines()
installed_pkgs = [
    i.replace("install", "").strip() for i in installed_pkgs if "deinstall" not in i
]
new_pkgs = list(set(installed_pkgs) - set(preinstalled_pkgs))
project["build"]["installed"].extend(new_pkgs)
out = {"idx": idx, "name": name, "project": project}
# save output JSON
with open("output.json", "w") as f:
    json.dump(out, f, indent=2)

# if os.environ.get("keep_build_files") == "False":
#     # delete everything
#     run(["rm", "-rf", build_dir])
#     run(["mkdir", build_dir])
# if os.environ.get("keep_source_files") == "False":
#     run(["rm", "-rf", source_dir])
#     # run(["mkdir", source_dir])
# else:
chown_dirs.append(source_dir)

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
