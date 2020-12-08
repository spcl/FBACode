import sys
import subprocess
import os
import re
from subprocess import PIPE
from itertools import chain


def run(command, cwd=None, stdout=None, stderr=None):

    # Python 3.5+ - subprocess.run
    # older - subprocess.call
    # TODO: capture_output added in 3.7 - verify it works
    print(" ".join(command))
    if sys.version_info.major >= 3 and sys.version_info.minor >= 5:
        return subprocess.run(command, cwd=cwd, stdout=stdout, stderr=stderr)
    else:
        return subprocess.call(command, cwd=cwd, stdout=stdout, stderr=stderr)


def set_env_vars(var):
    if not isinstance(var, str):
        return False
    env_vars = var.split(" ")
    for env_var in env_vars:
        env_var = env_var.split("=")
        if len(env_var) >= 2:
            os.environ[env_var[0]] = env_var[1]
    return True


def append_script(script_list: list, snippet):
    if isinstance(snippet, str):
        script_list.append(snippet)
    elif isinstance(snippet, list):
        script_list.extend(snippet)
    else:
        print("travis script not string or list: {}".format(snippet))


def run_scripts(logger, script_list, cwd=None):
    if isinstance(script_list, str):
        script_list = [script_list]
    elif not isinstance(script_list, list):
        logger.err_log.print_error(
            logger.idx, "travis script not string or list")
        logger.output_log.print_error(
            logger.idx, "travis script not string or list: {}".format(script_list))
        return True
    for cmd in script_list:
        substitution = run(
            ["bash", "-c", 'echo "{}"'.format(cmd)], stdout=PIPE, stderr=PIPE)
        print("TRAVIS: {}".format(substitution.stdout.decode("utf-8")))
        out = run(["bash", "-c", cmd], cwd,
                  stderr=subprocess.PIPE)
        if out.returncode != 0:
            logger.output_log.print_error(
                logger.idx, "running command \n{}   failed: {}".format(
                    substitution.stdout.decode("utf-8"), out.stderr.decode("utf-8")))
            logger.error_log.print_error(
                logger.idx, "bash command execution failed: {}".format(out.stderr.decode("utf-8")))
            return False
    return True


def apt_install(logger, pkgs):
    cmd = ["apt-get", "install", "-y", "--force-yes",
           "--no-install-recommends"]
    if isinstance(pkgs, str):
        cmd.append(pkgs)
    elif isinstance(pkgs, list):
        pkgs = list(chain(pkgs))
        if all(isinstance(i, str) for i in pkgs):
            cmd.append(" ".join(pkgs))
        else:
            logger.error_log.print_error(
                logger.idx, "apt installer was not str or list[str]")
    else:
        logger.error_log.print_error(
            logger.idx, "apt installer was not str or list[str]")
        return False
    out = run(cmd, stderr=PIPE)
    if out.returncode != 0:
        if "Unable to locate package " in out.stderr.decode("utf-8"):
            # some packages could not be found, let's remove them
            for l in out.stderr.decode("utf-8").splitlines():
                index = l.find("Unable to locate package ")
                if index >= 0:
                    pkg = l[index + len("Unable to locate package "):].strip()
                    cmd[-1] = cmd[-1].replace(pkg, "")
                    print("retrying without {}".format(pkg))
            out = run(cmd, stderr=PIPE)
            if out.returncode == 0:
                return True
        if "has no installation candidate" in out.stderr.decode("utf-8"):
            for l in out.stderr.decode("utf-8").splitlines():
                pattern = re.escape("E: Package '") + r"(.*)" + \
                    re.escape("' has no installation candidate")
                r = re.search(pattern, l)
                if r:
                    cmd[-1] = cmd[-1].replace(r[1], "")
                    print("retrying without {}".format(r[1]))
            out = run(cmd, stderr=PIPE)
            if out.returncode == 0:
                return True
        logger.error_log.print_error(
            logger.idx, "apt_packages install from .travis.yml failed")
        logger.error_log.print_error(logger.idx, "{}:\n{}".format(
            out.args, out.stderr.decode("utf-8")))
        return False
    return True
