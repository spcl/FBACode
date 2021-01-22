import yaml
import os
import urllib.request
import stat
from subprocess import PIPE
import json
from os.path import isfile, join
from yaml.composer import ComposerError

# try:
# not all distros have the FullLoader yet...
# from yaml.loader import FullLoader

# module path is different inside docker image
try:
    from build_systems.environment import get_c_compiler, get_cxx_compiler  # type: ignore
except ModuleNotFoundError:
    from code_builder.build_systems.environment import get_c_compiler, get_cxx_compiler

from .ci_helper import append_script, apt_install, run, set_env_vars, run_scripts


class Context:
    def __init__(self, cfg):
        self.cfg = cfg

    def set_loggers(self, out, err):
        self.out_log = out
        self.err_log = err


class CiSystem:
    def __init__(
        self, repo_dir, build_dir, idx, ctx, name, project, use_build_dir=False
    ):
        self.repository_path = repo_dir
        self.build_dir = build_dir
        self.idx = idx
        self.ctx = ctx
        self.output_log = ctx.out_log
        self.error_log = ctx.err_log
        self.project = project
        self.travis_dir = build_dir if use_build_dir else repo_dir

    def install(self):
        # open the .travis.yml file
        # TODO: collect all scripts and then run them in a single instance
        self.big_script = []
        print("installing dependencies using travis")
        try:
            with open(join(self.travis_dir, ".travis.yml"), "r") as f:
                # try:
                #     yml = yaml.load(f, Loader=FullLoader)
                # except:
                yml = yaml.safe_load(f)
                self.yml = yml
        except ComposerError as e:
            self.error_log.print_error(
                self.idx, "Error parsing .travis.yml:\n  {}".format(e)
            )
            return False
        except FileNotFoundError:
            self.error_log.print_error(
                self.idx, "Could not find {}/.travis.yml".format(self.travis_dir)
            )
            return False

        # set global env vars specified in the yaml
        if isinstance(self.yml.get("env"), list):
            for var in self.yml.get("env"):
                if isinstance(var, str):
                    set_env_vars(var)
                    break
        elif isinstance(self.yml.get("env"), str):
            set_env_vars(self.yml.get("env"))
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
        os.environ["TRAVIS_OS"] = "linux"
        # look for a good configuration of env or jobs or matrix:
        c_compiler = get_c_compiler()
        cxx_compiler = get_cxx_compiler()
        os.environ["CXX"] = cxx_compiler
        os.environ["CXX_FOR_BUILD"] = cxx_compiler
        os.environ["CC"] = c_compiler
        os.environ["CC_FOR_BUILD"] = c_compiler

        # package addons
        if yml.get("addons") is not None:
            if not self.travis_addons(yml["addons"]):
                return False
        #  TODO: pick a configuration from the env and rest of matrix
        # cache components
        # i dont think there is anything to do
        # run the before_install script, if any

        if yml.get("before_install") is not None:
            print("TRAVIS: running before_install")
            append_script(self.big_script, yml["before_install"])

            # if not run_scripts(self, yml["before_install"], cwd=self.travis_dir):
            #     return False
        # run the install
        if yml.get("install") is not None:
            print("TRAVIS: running install")
            append_script(self.big_script, yml["install"])
            # if not run_scripts(self, yml["install"], cwd=self.travis_dir):
            #     return False
        # run the before_script part
        if yml.get("before_script") is not None:
            print("TRAVIS: running before_script")
            append_script(self.big_script, yml["before_script"])
            # if not run_scripts(self, yml["before_script"], cwd=self.travis_dir):
            #     return False

        jobs = yml.get("jobs", yml.get("matrix"))
        if isinstance(jobs, dict):
            jobs = jobs.get("include", None)
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
                print("TRAVIS: running stage\n{}".format(stage[0]))
                if stage[0].get("env", None) is not None:
                    for var in stage[0]["env"]:
                        set_env_vars(var)
                if stage[0].get("addons") is not None:
                    if not self.travis_addons(stage[0]["addons"]):
                        return False
                if stage[0].get("before_install") is not None:
                    append_script(self.big_script, stage[0]["before_install"])
                    # if not run_scripts(self, stage[0]["before_install"], cwd=self.travis_dir):
                    #     return False
                # run the install
                if stage[0].get("install") is not None:
                    append_script(self.big_script, stage[0]["install"])
                    # if not run_scripts(self, stage[0]["install"], cwd=self.travis_dir):
                    #     return False
                # run the before_script part
                if stage[0].get("before_script") is not None:
                    append_script(self.big_script, stage[0]["before_script"])
                    # if not run_scripts(self, stage[0]["before_script"], cwd=self.travis_dir):
                    #     return False
                if stage[0].get("script") is not None:
                    append_script(self.big_script, stage[0]["script"])
                    # if not run_scripts(self, stage[0]["script"], cwd=self.travis_dir):
                    #     return False
        # run the accumulated script
        # print("bigass script:")
        script_file = join(self.travis_dir, "combined_script.sh")
        with open(script_file, "w") as f:
            f.write("#!/bin/bash\n")
            for s in self.big_script:
                f.write(s)
                f.write("\n")
        # make it executable
        st = os.stat(script_file)
        os.chmod(script_file, st.st_mode | stat.S_IEXEC)

        # run the script:
        out = run([script_file], cwd=self.travis_dir, stdout=PIPE, stderr=PIPE)
        if out.returncode != 0:
            self.error_log.print_error(
                self.idx,
                "TRAVIS combined_script.sh failed (error {}):\n{}".format(
                    out.returncode, out.stderr
                ),
            )
            self.error_log.print_info(self.idx, out.stdout)
            return False
        else:
            print(
                "TRAVIS combined_script.sh:\n{}\nstderr:\n{}".format(
                    out.stdout, out.stderr
                )
            )
        return True
        # replacements = [
        #     (";;", ";"),
        #     ("&;", "&")
        # ]
        # runnable_script = ""
        # for s in self.big_script:
        #     runnable_script += s
        #     if runnable_script[-1] not in {";", "&"}:

        # runnable_script = "; ".join(self.big_script).replace(";;", ";")
        # return run_scripts(self, runnable_script, cwd=self.travis_dir)
        # return True

    def travis_addons(self, addons):
        apt = addons.get("apt")
        # in case it's just a string or list of strings
        if apt and (
            isinstance(apt, str)
            or isinstance(apt, list)
            and all(isinstance(i, str) for i in apt)
        ):
            if not apt_install(self, apt, self.project):
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
                        safelist_entry = [i for i in safelist if i["alias"] == source]
                        if not safelist_entry:
                            # found nothing in safelist, try to use this string as url
                            source_url = source
                        else:
                            key_url = safelist_entry[0].get("canonical_key_url", None)
                            source_url = safelist_entry[0].get("sourceline")
                    else:
                        key_url = source.get("key_url", None)
                        source_url = source.get("sourceline")
                    if key_url:
                        cmd = [
                            "bash",
                            "-c",
                            "wget -qO - {} | apt-key add -".format(key_url),
                        ]
                        out = run(cmd, cwd=self.travis_dir, stderr=PIPE)
                        if out.returncode != 0:
                            self.error_log.print_error(
                                self.idx, "adding key to repo failed"
                            )
                            self.error_log.print_error(
                                self.idx, "{}:\n{}".format(out.args, out.stderr)
                            )
                            return False
                    if source_url is None:
                        self.error_log.print_error(
                            self.idx, "wrong format of sourceline in travis"
                        )
                        return False
                    cmd = ["add-apt-repository", source_url]
                    out = run(cmd, cwd=self.travis_dir, stderr=PIPE)
                    if out.returncode != 0:
                        self.error_log.print_error(self.idx, "adding repo failed")
                        self.error_log.print_error(
                            self.idx, "{}:\n{}".format(out.args, out.stderr)
                        )
                        return False
            if apt.get("update") or do_update:
                cmd = ["apt-get", "update"]
                out = run(cmd, stderr=PIPE)
                if out.returncode != 0:
                    self.error_log.print_error(
                        self.idx, "apt update from .travis.yml failed"
                    )
                    self.error_log.print_error(
                        self.idx, "{}:\n{}".format(out.args, out.stderr)
                    )
                    return False
            # lol, apt.get
            if apt.get("packages") is not None:
                apt_install(self, apt.get("packages"), self.project)

        apt_packages = addons.get("apt_packages")
        if apt_packages:
            apt_install(self, apt_packages, self.project)
        # run the snap module
        snaps = addons.get("snaps")
        if snaps is not None:

            if isinstance(snaps, str):
                cmd = ["bash", "-c", "snap install " + snaps]
                out = run(cmd, stderr=PIPE)
                if out.returncode != 0:
                    self.error_log.print_error(
                        self.idx, "snap install from .travis.yml failed"
                    )
                    self.error_log.print_error(
                        self.idx, "{}:\n{}".format(out.args, out.stderr)
                    )
                    return False
            else:
                for snap in snaps:
                    if isinstance(snap, str):
                        cmd = "snap install " + snap
                    else:
                        if "name" not in snap:
                            self.error_log.print_error(
                                self.idx, "invalid yaml file, snap name missing"
                            )
                            return False
                        cmd = "snap install " + snap["name"]
                        if snap.get("confinement") is not None:
                            cmd += " --{}".format(snap["confinement"])
                        if snap.get("channel") is not None:
                            cmd += " --channel={}".format(snap["channel"])
                    out = run(["bash", "-c", cmd], cwd=self.travis_dir, stderr=PIPE)
                    if out.returncode != 0:
                        self.error_log.print_error(
                            self.idx, "snap install from .travis.yml failed"
                        )
                        self.error_log.print_error(
                            self.idx, "{}:\n{}".format(out.args, out.stderr)
                        )
                        return False
        return True

    def build(self):
        # run the script
        try:
            with open(join(self.travis_dir, ".travis.yml"), "r") as f:
                yml = yaml.safe_load(f)
                self.yml = yml
        except ComposerError as e:
            self.error_log.print_error(
                self.idx, "Error parsing .travis.yml:\n  {}".format(e)
            )
            return False
        except FileNotFoundError:
            self.error_log.print_error(
                self.idx, "Could not find {}/.travis.yml".format(self.travis_dir)
            )
            return False
        if self.yml.get("script") is not None:
            print("TRAVIS: running script")
            if not run_scripts(self, self.yml["script"], cwd=self.build_dir):
                return False
        return True

    @staticmethod
    def recognize(repo_dir):
        return isfile(join(repo_dir, ".travis.yml"))

    @staticmethod
    def get_docker_image(repo_dir, clang_version=9):
        # no trusty since it does not support clang 9
        # trusty will run with clang 8, some packages require trusty
        # no, fuck trusty
        supported_dists = ["focal", "bionic", "xenial"]
        yml = None
        try:
            with open(join(repo_dir, ".travis.yml"), "r") as f:
                # yml = yaml.load(f, Loader=FullLoader)
                yml = yaml.safe_load(f)
        except ComposerError as e:
            print("Error parsing .travis.yml:\n  {}".format(e))
            return False
        except FileNotFoundError:
            print("Could not find {}/.travis.yml".format(repo_dir))
            return False
        if "dist" in yml and yml.get("dist") in supported_dists:
            return "mcopik/fbacode:ubuntu-{}-clang-{}".format(
                yml.get("dist"), clang_version
            )
        else:
            # default is xenial
            return "mcopik/fbacode:ubuntu-xenial-clang-{}".format(clang_version)
