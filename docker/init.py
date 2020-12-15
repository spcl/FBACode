import json
import sys
import os
import importlib
import glob
import subprocess
from subprocess import PIPE

from time import time
from shutil import move, copyfile
from datetime import datetime

# paths are different indide docker
from utils.driver import open_logfiles  # type: ignore
from build_systems.utils import run  # type: ignore


class Context:
    def __init__(self, cfg):
        self.cfg = cfg

    def set_loggers(self, out, err):
        self.out_log = out
        self.err_log = err


source_dir = "/home/fba_code/source"
build_dir = "/home/fba_code/build"
bitcodes_dir = "/home/fba_code/bitcodes"
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
    print("installing dependencies")
    # install_method = getattr(builder, "install", None)
    # if callable(install_method):
    #     # our builder can install deps by themselves:
    #     print("installing dependencies using builder class")
    #     success = install_method()
    #     if success:
    #         print("successfully installed dependencies with build system")

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

start = time()
configured = builder.configure(build_dir)
end = time()
project["build"]["configure_time"] = end - start
start = time()
if not configured:
    project["build"]["configure"] = "fail"
    failure = True
else:
    project["build"]["configure"] = "success"
    # Configure -> Build
    project["status"] = "build"
    if skip_build:
        project["status"] = "success"
        project["build"]["build"] = "skipped"
        print("skipped build")
    else:
        if not builder.build():
            project["build"]["build"] = "fail"
            project["status"] = "fail"
            failure = True
        else:
            project["status"] = "success"
            project["build"]["build"] = "success"
            project["bitcodes"] = {"dir": external_bitcodes_dir}
            project["ast_files"] = {"dir": os.path.join(external_bitcodes_dir, "AST")}
            builder.generate_bitcodes(bitcodes_dir)
            builder.generate_ast(os.path.join(bitcodes_dir, "AST"))
end = time()
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

# move logs to build directory
for file in glob.glob("*.log"):
    move(file, build_dir)
copyfile("output.json", os.path.join(build_dir, "output.json"))

# change the user and group to the one of the host, since we are root
host_uid = os.stat(build_dir).st_uid
host_gid = os.stat(build_dir).st_gid

dirs = [build_dir, bitcodes_dir, source_dir]
for d in dirs:
    print("chowning {}...".format(d))
    out = subprocess.run(["chown", "-R", "{}:{}".format(host_uid, host_gid), d])
    if out.returncode != 0:
        print(out)
