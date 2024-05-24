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
from os.path import basename

from utils.driver import open_logfiles, recursively_get_files, recursively_get_dirs  # type: ignore
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
    print(f"[IDX {idx}]: {to_print}")

def run_command(cmd, cwd, stdout = PIPE, stderr = PIPE):
    print_section(idx, ctx, "running command: {}".format(" ".join(cmd)))
    ret = run(cmd, cwd=cwd, stdout=stdout, stderr=stderr)
    if ret.returncode:
        print(f"Failed to run command '{cmd}', got return code: {ret.returncode}")
        ctx.err_log.print_error(idx, "stderr: {}".format(ret.stderr))
        ctx.out_log.print_info(idx, "stdout: {}".format(ret.stdout))
        print(f"[IDX {idx}]: stdout: {ret.stdout}")
        print(f"[IDX {idx}]: stderr: {ret.stderr}")
    ctx.out_log.print_info(idx, f"command '{cmd}' ran successfully!")
    print(f"[IDX {idx}]: command '{cmd}' ran successfully!")
    return ret

# TODO: this is hardcoded. Make it configurable
ast_dir = f"{DOCKER_MOUNT_POINT}/compiler_output/AST"
results_dir = f"{DOCKER_MOUNT_POINT}/analyze"
external_results_dir = os.environ.get("RESULTS_DIR", "")
analyses_to_run = os.environ.get("ANALYSES", "")  # TODO: validate analysis names

json_input = json.load(open(sys.argv[1], "r"))
idx = json_input["idx"]
name = json_input["name"]
# verbose = json_input["verbose"]

print("python version: {}".format(sys.version))

# directories to be chowned in the end
chown_dirs = [results_dir]

cfg = {"output": {"verbose": True, "file": f"{DOCKER_MOUNT_POINT}/"}}
ctx = Context(cfg)

timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
loggers = open_logfiles(cfg, name.replace("/", "_"), timestamp=timestamp)

ctx.set_loggers(loggers.stdout, loggers.stderr)
# save all installed packages, to get the difference later (newly installed deps)
# assusmes we run debian or ubuntu, maybe put into library in the future
# out = run(["dpkg", "--get-selections"], stderr=PIPE, stdout=PIPE)
# preinstalled_pkgs = out.stdout.splitlines()
# preinstalled_pkgs = [
#     i.replace("install", "").strip() for i in preinstalled_pkgs if "deinstall" not in i
# ]

# Updated -> Configure
project = {
    # "status": "configure",
    "analyze": {
        "dir": external_results_dir,
        "stdout": os.path.basename(loggers.stdout_file),
        "stderr": os.path.basename(loggers.stderr_file),
        "installed": [],
        "-j": os.environ.get("JOBS", 1),
    },
}

# untar the archive
ret = run_command(["tar", "-xzvf", f"{DOCKER_MOUNT_POINT}/ast_archive/{name}.tar.gz"], cwd=DOCKER_MOUNT_POINT)

# remove archive
os.remove(f"{DOCKER_MOUNT_POINT}/ast_archive/{name}.tar.gz")

# installing the system libraries/packages that the project depends on
out = run(
    ["apt-get", "build-dep", "-y", name],
    cwd=DOCKER_MOUNT_POINT,
    stderr=PIPE,
)

out = run(
    [
        "bash",
        "-c",
        "shopt -s dotglob; cp -ap {}/build {}/{}".format(
            DOCKER_MOUNT_POINT, DOCKER_MOUNT_POINT, basename(json_input["project"]["build"]["temp_build_dir"])
        ),
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

ret = run_command("ls -la".split(), cwd=DOCKER_MOUNT_POINT)
print(ret.stdout)

# ret = run_command("cxx-langstat --version".split(), stderr=PIPE, stdout=PIPE, cwd=DOCKER_MOUNT_POINT)
# print("with PIPE:")
# print(ret.stdout)
# print(ret.stderr)

# ret = run_command("cxx-langstat --version".split(), cwd=DOCKER_MOUNT_POINT)
# print("without PIPE:")
# print(ret.stdout)
# print(ret.stderr)

if (
    json_input["project"]["build"]["build"] == "success"
    and analyses_to_run != ""
):
    print_section(idx, ctx, "running cxx-langstat for features")

    j = os.environ.get("JOBS", 1)
    cmd = f"cxx-langstat -analyses={analyses_to_run} -emit-features -indir {ast_dir} -outdir {results_dir}/ -j {j} --".split()
    ret = run(cmd, cwd=DOCKER_MOUNT_POINT, stdout=PIPE, stderr=PIPE)

    print_section(
        idx, ctx, f"cxx-langstat finished with return code: {ret.returncode}"
    )

    ctx.err_log.print_error(idx, f"cxx-langstat stderr: {ret.stderr}")
    ctx.out_log.print_info(idx, f"cxx-langstat stdout: {ret.stdout}")
    
    print(f"[IDX {idx}] cxx-langstat -emit-features stdout: {ret.stdout}")
    print(f"[IDX {idx}] cxx-langstat -emit-features stderr: {ret.stderr}")
    project["features_files"] = {"dir": external_results_dir}
    project["analysis emit-features retcode"] = ret.returncode

    print_section(idx, ctx, "running cxx-langstat for statistics")

    j = os.environ.get("JOBS", 1)
    cmd = f"cxx-langstat -analyses={analyses_to_run} -emit-statistics -indir {results_dir} -out {results_dir}/overall_stats --".split()
    ret = run(cmd, cwd=DOCKER_MOUNT_POINT, stdout=PIPE, stderr=PIPE)

    print_section(
        idx, ctx, f"cxx-langstat emit stats finished with return code: {ret.returncode}"
    )

    ctx.err_log.print_error(idx, f"cxx-langstat stderr: {ret.stderr}")
    ctx.out_log.print_info(idx, f"cxx-langstat stdout: {ret.stdout}")
    print(f"[IDX {idx}] cxx-langstat -emit-statistics stdout: {ret.stdout}")
    print(f"[IDX {idx}] cxx-langstat -emit-statistics stderr: {ret.stderr}")
    project["features_files"] = {"dir": external_results_dir}
    project["analysis emit-stats retcode"] = ret.returncode

out = {"idx": idx, "name": name, "project": project}
# save output JSON
with open("output.json", "w") as f:
    json.dump(out, f, indent=2)


# move logs to build directory
for file in glob.glob("*.log"):
    move(file, results_dir)
copyfile("output.json", os.path.join(results_dir, "output.json"))

# change the user and group to the one of the host, since we are root
host_uid = os.stat(results_dir).st_uid
host_gid = os.stat(results_dir).st_gid

for d in set(chown_dirs):
    print("chowning {}...".format(d))
    out = subprocess.run(["chown", "-R", "{}:{}".format(host_uid, host_gid), d])
    if out.returncode != 0:
        print(out)

total_files = 0
# for file in glob.glob(f"**/*.ast.json"):
for file in recursively_get_files(".", ext=".ast.json"):
    total_files += 1
    # os.remove(file)
print(f"Should have {total_files} ast json files")