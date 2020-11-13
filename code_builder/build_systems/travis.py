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
        for cmd in script_list:
            out = run(["bash", "-c", cmd], cwd=self.build_dir, stderr=subprocess.PIPE)
            if out.returncode != 0:
                self.error_log.print_error(self.idx, "running command \n{}\nfailed".format(cmd))
                self.error_log.print_error(self.idx, "{}:\n{}".format(out.args, out.stderr.decode("utf-8")))
                return False
        return True
    '''
    def run_addons(self, addons):
        apt = addons.get("apt")
        # in case its just a string or list of strings
        if apt and (isinstance(apt, str) or
                    isinstance(apt, list) and all(isinstance(i, str) for i in apt)):
            cmd = ["apt-get", "install", "-y", "--force-yes",
                   "--no-install-recommends", apt]
            out = run(cmd, cwd=self.build_dir, stderr=subprocess.PIPE)
            if out.returncode != 0:
                self.error_log.print_error(self.idx, "apt_packages install from .travis.yml failed")
                self.error_log.print_error(self.idx, "{}:\n{}".format(out.args, out.stderr.decode("utf-8")))
                return False
        # in case it is more complicated
        elif apt:
            do_update = False
            if apt.get("sources", None) is not None:
                # add apt sources accoring to the yaml
                do_update = True
                # download apt source safelist file
                safelist = None
                url = "https://raw.githubusercontent.com/travis-ci/apt-source-safelist/master/ubuntu.json"
                with urllib.request.urlopen(url) as resp:
                    safelist = json.loads(resp.read().decode())
                for source in apt.get("sources", []):
                    key_url = None
                    source_url = None
                    if isinstance(source, str):
                        # this should be in safelist
                        safelist_entry = next(i for i in safelist if safelist["alias"] == source)
                        key_url = safelist_entry.get("canonical_key_url", None)
                        source_url = safelist_entry.get("sourceline")
                    else:
                        key_url = source.get("key_url", None)
                        source_url = source.get("sourceline")
                    if key_url:
                        cmd = ["sh", "-c", "wget -q0 - {} | apt-key add -".format(key_url)]
                        out = run(cmd, cwd=self.build_dir, stderr=subprocess.PIPE)
                        if out.returncode != 0:
                            self.error_log.print_error(self.idx, "adding key to repo failed")
                            self.error_log.print_error(self.idx, "{}:\n{}".format(out.args, out.stderr.decode("utf-8")))
                            return False
                    if source_url is None:
                        self.error_log.print_error(self.idx, "wrong format of sourceline in travis")
                        return False
                    cmd = ["add-apt-repository", source_url]
                    out = run(cmd, cwd=self.build_dir, stderr=subprocess.PIPE)
                    if out.returncode != 0:
                        self.error_log.print_error(self.idx, "adding repo failed")
                        self.error_log.print_error(self.idx, "{}:\n{}".format(out.args, out.stderr.decode("utf-8")))
                        return False
            if apt.get("update") or do_update:
                cmd = ["apt-get", "update"]
                out = run(cmd, stderr=subprocess.PIPE)
                if out.returncode != 0:
                    self.error_log.print_error(self.idx, "apt update from .travis.yml failed")
                    self.error_log.print_error(self.idx, "{}:\n{}".format(out.args, out.stderr.decode("utf-8")))
                    return False
            if apt.get("packages") is not None:
                if isinstance(apt["packages"], str):
                    print("am string")
                    cmd = ["apt-get", "install", "-y", "--force-yes",
                           "--no-install-recommends", apt["packages"]]
                else:
                    # we have a list of packages
                    print("am not string, am {}".format(type(apt["packages"])))
                    cmd = ["apt-get", "install", "-yq", "--force-yes",
                           "--no-install-recommends"]
                    cmd.extend(apt["packages"])
                print(cmd)
                out = run(cmd, stderr=subprocess.PIPE)
                if out.returncode != 0:
                    self.error_log.print_error(self.idx, "apt install from .travis.yml failed")
                    self.error_log.print_error(self.idx, "{}:\n{}".format(out.args, out.stderr.decode("utf-8")))
                    return False

        apt_packages = addons.get("apt_packages")
        if apt_packages:
            cmd = ["apt-get", "install", "-y", "--force-yes",
                   "--no-install-recommends", apt]
            out = run(cmd, stderr=subprocess.PIPE)
            if out.returncode != 0:
                self.error_log.print_error(self.idx, "apt_packages install from .travis.yml failed")
                self.error_log.print_error(self.idx, "{}:\n{}".format(out.args, out.stderr.decode("utf-8")))
                return False
        # run the snap module
        snaps = addons.get("snaps")
        if snaps is not None:

            if isinstance(snaps, str):
                cmd = ["snap", "install", snaps]
                out = run(cmd, stderr=subprocess.PIPE)
                if out.returncode != 0:
                    self.error_log.print_error(self.idx, "snap install from .travis.yml failed")
                    self.error_log.print_error(self.idx, "{}:\n{}".format(out.args, out.stderr.decode("utf-8")))
                    return False
            else:
                for snap in snaps:
                    if isinstance(snap, str):
                        cmd = ["snap", "install", snap]
                    else:
                        if "name" not in snap:
                            self.error_log.print_error(self.idx, "invalid yaml file, snap name missing")
                            return False
                        cmd = ["snap", "install", snap["name"]]
                        if snap.get("confinement") is not None:
                            cmd.append("--{}".format(snap["confinement"]))
                        if snap.get("channel") is not None:
                            cmd.append("--channel={}".format(snap["channel"]))
                    out = run(cmd, cwd=self.build_dir, stderr=subprocess.PIPE)
                    if out.returncode != 0:
                        self.error_log.print_error(self.idx, "snap install from .travis.yml failed")
                        self.error_log.print_error(self.idx, "{}:\n{}".format(out.args, out.stderr.decode("utf-8")))
                        return False
        return True
    '''
    def configure(self, force_update=True):
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
        with open(join(self.build_dir, ".travis.yml"), 'r') as f:
            yml = yaml.load(f, Loader=FullLoader)
            self.yml = yml
        # set global env vars specified in the yaml
        if isinstance(self.yml.get("env"), list):
            for var in self.yml.get("env"):
                if isinstance(var, str):
                    self.set_env_vars(var)
                    break
        else:
            for var in self.yml.get("env", {}).get("global", []):
                self.set_env_vars(var)
            # take the first configuration, idk
            for var in self.yml.get("env", {}).get("jobs", []):
                if isinstance(var, str):
                    self.set_env_vars(var)
                    break
            for var in self.yml.get("env", {}).get("matrix", []):
                if isinstance(var, str):
                    self.set_env_vars(var)
                    break
        # https://docs.travis-ci.com/user/environment-variables/#default-environment-variables
        os.environ["TRAVIS_BUILD_DIR"] = self.build_dir
        os.environ["CI"] = "true"
        os.environ["TRAVIS"] = "true"
        
        # look for a good configuration of env or jobs or matrix:
        jobs = yml.get("jobs", yml.get("matrix", {})).get("include", None)
        if jobs and isinstance(jobs, list):
            # split this list into stages, since each stage need to be run afaik
            travis_stages = [[]]
            i = 0
            for job in jobs:
                if "stage" in job:
                    if len(travis_stages[0]) > 0:
                        i += 1
                        travis_stages.append([])
                    travis_stages[i].append(job)
                else:
                    travis_stages[i].append(job)
            for stage in travis_stages:
                # try and filter out amd64, linux and clang jobs
                amd64_jobs = [i for i in stage if i.get("os") == "amd64"]
                if len(amd64_jobs) > 0:
                    stage = amd64_jobs
                linux_jobs = [i for i in stage if i.get("os") == "linux"]
                if len(linux_jobs) > 0:
                    stage = linux_jobs
                clang_jobs = [i for i in stage if i.get("compiler") == "clang"]
                if len(clang_jobs) > 0:
                    stage = clang_jobs
                # pick the first one of the matrix, idk how to handle it
                if stage[0].get("env", None) is not None:
                    for var in stage[0]["env"]:
                        self.set_env_vars(var)
                if stage[0].get("addons") is not None:
                    if not travis_addons(self, stage[0]["addons"]):
                        return False
                if stage[0].get("before_install") is not None:
                    if not self.run_scripts(stage[0]["before_install"]):
                        return False
                # run the install
                if stage[0].get("install") is not None:
                    if not self.run_scripts(stage[0]["install"]):
                        return False
                # run the before_script part
                if stage[0].get("before_script") is not None:
                    if not self.run_scripts(stage[0]["before_script"]):
                        return False
                if stage[0].get("script") is not None:
                    if not self.run_scripts(stage[0]["script"]):
                        return False

        # package addons
        if yml.get("addons") is not None:
            if not travis_addons(self, yml["addons"]):
                return False
        #  TODO: pick a configuration from the env and rest of matrix
        # cache components
        # i dont think there is anything to do
        # run the before_install script, if any
        c_compiler = get_c_compiler()
        cxx_compiler = get_cxx_compiler()
        os.environ["CXX"] = cxx_compiler
        os.environ["CXX_FOR_BUILD"] = cxx_compiler
        os.environ["CC"] = c_compiler
        os.environ["CC_FOR_BUILD"] = c_compiler
        
        if yml.get("before_install") is not None:
            if not self.run_scripts(yml["before_install"]):
                return False
        # run the install
        if yml.get("install") is not None:
            if not self.run_scripts(yml["install"]):
                return False
        # run the before_script part
        if yml.get("before_script") is not None:
            if not self.run_scripts(yml["before_script"]):
                return False
        return True

    def build(self):
        # run the script
        if self.yml.get("script") is not None:
            if not self.run_scripts(self.yml["script"]):
                return False

        return True
        # before_cache would be run here, look into this

        # maybe do after_success of after_failure?
        # i think deploy parts can be ignored

    def generate_bitcodes(self, target_dir):
        for file in pathlib.Path(self.build_dir).glob("**/*.bc"):
            # CMake file format: {build_dir}/../CMakeFiles/{dir}.dir/relative_bc_location
            res = search(r"{}".format(self.build_dir), str(file))
            local_path = str(file)[res.end(0) + 1:]
            makedirs(join(target_dir, dirname(local_path)), exist_ok=True)
            # os.rename does not work for target and destinations being
            # on different filesystems
            # we might operate on different volumes in Docker
            shutil.move(file, join(target_dir, local_path))

    def generate_ast(self, target_dir):
        for file in pathlib.Path(self.build_dir).glob("**/*.ast"):
            res = search(r"{}".format(self.build_dir), str(file))
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
        return isfile(join(repo_dir, ".travis.yml"))
