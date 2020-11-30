import yaml
import os
import urllib
from subprocess import PIPE
import json
from os import listdir, remove
from os.path import isdir, isfile, join
from yaml.loader import FullLoader

# figure out how to import this.. maybe, not sure if needed
# from ..build_systems.environment import get_c_compiler, get_cxx_compiler

from .ci_helper import run, run_scripts, set_env_vars


class Context:
    def __init__(self, cfg):
        self.cfg = cfg

    def set_loggers(self, out, err):
        self.out_log = out
        self.err_log = err


class CiSystem:
    def __init__(self, repo_dir, build_dir, idx, ctx, project):
        self.repository_path = repo_dir
        self.build_dir = build_dir
        self.idx = idx
        self.ctx = ctx
        self.output_log = ctx.out_log
        self.error_log = ctx.err_log
        self.project = project
        self.travis_dir = repo_dir

    def install(self):
        # open the .travis.yml file
        print("installing dependencies using travis")
        try:
            with open(join(self.travis_dir, ".travis.yml"), 'r') as f:
                yml = yaml.load(f, Loader=FullLoader)
                self.yml = yml
        except yaml.composer.ComposerError as e:
            self.error_log.print_error(
                self.idx, "Error parsing .travis.yml:\n  {}".format(e))
            return False
        except FileNotFoundError:
            self.error_log.print_error(
                self.idx, "Could not find {}/.travis.yml".format(self.travis_dir))
            return False

        # set global env vars specified in the yaml
        if isinstance(self.yml.get("env"), list):
            for var in self.yml.get("env"):
                if isinstance(var, str):
                    set_env_vars(var)
                    break
        elif isinstance(self.yml.get("env"), str):
            self.set_env_vars(self.yml.get("env"))
        else:
            for var in self.yml.get("env", {}).get("global", []):
                set_env_vars(var)
            # take the first configuration, idk
            for var in self.yml.get("env", {}).get("jobs", []):
                if isinstance(var, str):
                    set_env_vars(var)
                    break
            for var in self.yml.get("env", {}).get("matrix", []):
                if isinstance(var, str):
                    set_env_vars(var)
                    break
        # https://docs.travis-ci.com/user/environment-variables/#default-environment-variables
        os.environ["TRAVIS_BUILD_DIR"] = self.travis_dir
        os.environ["CI"] = "true"
        os.environ["TRAVIS"] = "true"
        os.environ["TRAVIS_OS"] = "linux"

        # look for a good configuration of env or jobs or matrix:

        # package addons
        if yml.get("addons") is not None:
            if not self.travis_addons(yml["addons"]):
                return False
        #  TODO: pick a configuration from the env and rest of matrix
        # cache components
        # i dont think there is anything to do
        # run the before_install script, if any
        # c_compiler = get_c_compiler()
        # cxx_compiler = get_cxx_compiler()
        # os.environ["CXX"] = cxx_compiler
        # os.environ["CXX_FOR_BUILD"] = cxx_compiler
        # os.environ["CC"] = c_compiler
        # os.environ["CC_FOR_BUILD"] = c_compiler

        if yml.get("before_install") is not None:
            print("TRAVIS: running before_install")
            if not run_scripts(self, yml["before_install"], cwd=self.travis_dir):
                return False
        # run the install
        if yml.get("install") is not None:
            print("TRAVIS: running install")
            if not run_scripts(self, yml["install"], cwd=self.travis_dir):
                return False
        # run the before_script part
        if yml.get("before_script") is not None:
            print("TRAVIS: running before_script")
            if not run_scripts(self, yml["before_script"], cwd=self.travis_dir):
                return False

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
                print("TRAVIS: running stage\n{}\n".format(stage[0]))
                if stage[0].get("env", None) is not None:
                    for var in stage[0]["env"]:
                        set_env_vars(var)
                if stage[0].get("addons") is not None:
                    if not self.travis_addons(stage[0]["addons"]):
                        return False
                if stage[0].get("before_install") is not None:
                    if not run_scripts(self, stage[0]["before_install"], cwd=self.travis_dir):
                        return False
                # run the install
                if stage[0].get("install") is not None:
                    if not run_scripts(self, stage[0]["install"], cwd=self.travis_dir):
                        return False
                # run the before_script part
                if stage[0].get("before_script") is not None:
                    if not run_scripts(self, stage[0]["before_script"], cwd=self.travis_dir):
                        return False
                if stage[0].get("script") is not None:
                    if not run_scripts(self, stage[0]["script"], cwd=self.travis_dir):
                        return False
        return True

    def travis_addons(self, addons):
        apt = addons.get("apt")
        # in case it's just a string or list of strings
        if apt and (isinstance(apt, str) or
                    isinstance(apt, list) and all(isinstance(i, str) for i in apt)):
            cmd = ["apt-get", "install", "-y", "--force-yes",
                   "--no-install-recommends"]
            if isinstance(apt, str):
                cmd.append(apt)
            elif isinstance(apt, list):
                cmd.extend(apt)
            out = run(cmd, stderr=PIPE)
            if out.returncode != 0:
                self.error_log.print_error(
                    self.idx, "apt_packages install from .travis.yml failed")
                self.error_log.print_error(self.idx, "{}:\n{}".format(
                    out.args, out.stderr.decode("utf-8")))
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
                        safelist_entry = [
                            i for i in safelist if i["alias"] == source]
                        if not safelist_entry:
                            # found nothing in safelist, try to use this string as url
                            source_url = source
                        else:
                            key_url = safelist_entry[0].get(
                                "canonical_key_url", None)
                            source_url = safelist_entry[0].get("sourceline")
                    else:
                        key_url = source.get("key_url", None)
                        source_url = source.get("sourceline")
                    if key_url:
                        cmd = ["sh", "-c",
                               "wget -q0 - {} | apt-key add -".format(key_url)]
                        out = run(cmd, cwd=self.travis_dir, stderr=PIPE)
                        if out.returncode != 0:
                            self.error_log.print_error(
                                self.idx, "adding key to repo failed")
                            self.error_log.print_error(self.idx, "{}:\n{}".format(
                                out.args, out.stderr.decode("utf-8")))
                            return False
                    if source_url is None:
                        self.error_log.print_error(
                            self.idx, "wrong format of sourceline in travis")
                        return False
                    cmd = ["add-apt-repository", source_url]
                    out = run(cmd, cwd=self.travis_dir, stderr=PIPE)
                    if out.returncode != 0:
                        self.error_log.print_error(
                            self.idx, "adding repo failed")
                        self.error_log.print_error(self.idx, "{}:\n{}".format(
                            out.args, out.stderr.decode("utf-8")))
                        return False
            if apt.get("update") or do_update:
                cmd = ["apt-get", "update"]
                out = run(cmd, stderr=PIPE)
                if out.returncode != 0:
                    self.error_log.print_error(
                        self.idx, "apt update from .travis.yml failed")
                    self.error_log.print_error(self.idx, "{}:\n{}".format(
                        out.args, out.stderr.decode("utf-8")))
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
                out = run(cmd, stderr=PIPE)
                if out.returncode != 0:
                    self.error_log.print_error(
                        self.idx, "apt install from .travis.yml failed")
                    self.error_log.print_error(self.idx, "{}:\n{}".format(
                        out.args, out.stderr.decode("utf-8")))
                    return False

        apt_packages = addons.get("apt_packages")
        if apt_packages:
            cmd = ["apt-get", "install", "-y", "--force-yes",
                   "--no-install-recommends"]
            if isinstance(apt_packages, str):
                cmd.append(apt_packages)
            elif isinstance(apt_packages, list):
                cmd.extend(apt_packages)
            print(cmd)
            out = run(cmd, stderr=PIPE)
            if out.returncode != 0:
                self.error_log.print_error(
                    self.idx, "apt_packages install from .travis.yml failed")
                self.error_log.print_error(self.idx, "{}:\n{}".format(
                    out.args, out.stderr.decode("utf-8")))
                return False
        # run the snap module
        snaps = addons.get("snaps")
        if snaps is not None:

            if isinstance(snaps, str):
                cmd = ["snap", "install", snaps]
                out = run(cmd, stderr=PIPE)
                if out.returncode != 0:
                    self.error_log.print_error(
                        self.idx, "snap install from .travis.yml failed")
                    self.error_log.print_error(self.idx, "{}:\n{}".format(
                        out.args, out.stderr.decode("utf-8")))
                    return False
            else:
                for snap in snaps:
                    if isinstance(snap, str):
                        cmd = ["snap", "install", snap]
                    else:
                        if "name" not in snap:
                            self.error_log.print_error(
                                self.idx, "invalid yaml file, snap name missing")
                            return False
                        cmd = ["snap", "install", snap["name"]]
                        if snap.get("confinement") is not None:
                            cmd.append("--{}".format(snap["confinement"]))
                        if snap.get("channel") is not None:
                            cmd.append("--channel={}".format(snap["channel"]))
                    out = run(cmd, cwd=self.travis_dir, stderr=PIPE)
                    if out.returncode != 0:
                        self.error_log.print_error(
                            self.idx, "snap install from .travis.yml failed")
                        self.error_log.print_error(self.idx, "{}:\n{}".format(
                            out.args, out.stderr.decode("utf-8")))
                        return False
        return True

    @staticmethod
    def recognize(repo_dir):
        return isfile(join(repo_dir, ".travis.yml"))
