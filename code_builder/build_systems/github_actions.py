import shutil
import subprocess
import os
import yaml
import urllib.request
import json

from os.path import abspath, join, isfile, dirname, isdir
from os import listdir, makedirs, mkdir, remove
from subprocess import PIPE
from shutil import rmtree
from sys import version_info
from re import search
import pathlib
from .dependency_installer import travis_addons

from yaml.loader import FullLoader

from .environment import get_c_compiler, get_cxx_compiler


def run(command, cwd=None, stdout=None, stderr=None):

    # Python 3.5+ - subprocess.run
    # older - subprocess.call
    # TODO: capture_output added in 3.7 - verify it works
    print(" ".join(command))
    if version_info.major >= 3 and version_info.minor >= 5:
        return subprocess.run(command, cwd=cwd, stdout=stdout, stderr=stderr)
    else:
        return subprocess.call(command, cwd=cwd, stdout=stdout, stderr=stderr)


class Context:
    def __init__(self, cfg):
        self.cfg = cfg

    def set_loggers(self, out, err):
        self.out_log = out
        self.err_log = err


class Project:
    CONTAINER_NAME = "mcopik/fbacode:ubuntu-2004-travis"

    def __init__(self, repo_dir, build_dir, idx, ctx, project):
        self.repository_path = repo_dir
        self.build_dir = build_dir
        self.idx = idx
        self.ctx = ctx
        self.output_log = ctx.out_log
        self.error_log = ctx.err_log
        self.project = project
    
    def set_env_vars(self, var):
        if not isinstance(var, str):
            return False
        env_vars = var.split(" ")
        for env_var in env_vars:
            env_var = env_var.split("=")
            if len(env_var) >= 2:
                os.environ[env_var[0]] = env_var[1]
        return True

    def run_scripts(self, script_list):
        if isinstance(script_list, str):
            script_list = [script_list]
        elif not isinstance(script_list, list):
            self.error_log.print_error(self.idx, "travis script not string or list: {}".format(script_list))
            return True
        for cmd in script_list:
            print("TRAVIS: {}".format(cmd))
            out = run(["bash", "-c", cmd], cwd=self.build_dir, stderr=subprocess.PIPE)
            if out.returncode != 0:
                self.error_log.print_error(self.idx, "running command \n{}\nfailed".format(cmd))
                self.error_log.print_error(self.idx, "{}:\n{}".format(out.args, out.stderr.decode("utf-8")))
                return False
        return True
    
    def configure(self, force_update=True):
        return True
        # open the .travis.yml file
        if len(listdir(self.build_dir)) == 0 or force_update:
            # clean build dir and copy source over
            # we cant always build in separate directory from build
            for f in listdir(self.build_dir):
                if ".log" in f:
                    continue
                p = join(self.build_dir, f)
                if isdir(p):
                    try:
                        shutil.rmtree(p)
                    except FileNotFoundError:
                        run(["rm", "-rf", p])
                else:
                    remove(p)
            cmd = ["bash", "-c", "shopt -s dotglob; cp -a {}/* {}".format(self.repository_path, self.build_dir)]
            out = run(cmd, cwd=self.repository_path, stderr=subprocess.PIPE)
            if out.returncode != 0:
                self.error_log.print_error(self.idx, "{}:\n{}".format(out.args, out.stderr.decode("utf-8")))
                return False
        return True

    def build(self):
        # run the script
        return True
        # i think deploy parts can be ignored

    def generate_bitcodes(self, target_dir):
        for file in pathlib.Path(self.build_dir).glob("**/*.bc"):
            # CMake file format: {build_dir}/../CMakeFiles/{dir}.dir/relative_bc_location
            res = search(r"{}".format(self.build_dir), str(file))
            if res is None:
                self.error_log.print_error(self.idx, "error while globbing for .bc files: {}".format(file))
                continue
            local_path = str(file)[res.end(0) + 1:]
            makedirs(join(target_dir, dirname(local_path)), exist_ok=True)
            # os.rename does not work for target and destinations being
            # on different filesystems
            # we might operate on different volumes in Docker
            shutil.move(file, join(target_dir, local_path))

    def generate_ast(self, target_dir):
        for file in pathlib.Path(self.build_dir).glob("**/*.ast"):
            res = search(r"{}".format(self.build_dir), str(file))
            if res is None:
                self.error_log.print_error(self.idx, "error while globbing for .bc files: {}".format(file))
                continue
            local_path = str(file)[res.end(0) + 1:]
            makedirs(join(target_dir, dirname(local_path)), exist_ok=True)
            shutil.move(file, join(target_dir, local_path))
        return True

    def clean(self):
        build_dir = self.repository_path + "_build"
        rmtree(build_dir)
        mkdir(build_dir)

    @staticmethod
    def recognize(repo_dir):
        return isdir(join(repo_dir, ".github/workflows"))