import sys
import subprocess
import os
import re
from subprocess import CalledProcessError, CompletedProcess, PIPE


def decode(stream):
    if isinstance(stream, bytearray):
        return stream.decode("utf-8")
    else:
        return stream


def run(command, cwd=None, stdout=None, stderr=None) -> CompletedProcess:
    # Python 3.5+ - subprocess.run
    # older - subprocess.call
    # TODO: capture_output added in 3.7 - verify it works
    if sys.version_info.major >= 3 and sys.version_info.minor >= 5:
        out = subprocess.run(
            command, cwd=cwd, stdout=stdout, stderr=stderr, encoding="utf-8"
        )
        return CompletedProcess(
            out.args, out.returncode, decode(out.stdout), decode(out.stderr)
        )
    else:
        print("using legacy runner (python < 3.4)")
        code = 0
        try:
            out = subprocess.check_output(command, cwd=cwd, stderr=subprocess.STDOUT)
        except CalledProcessError as e:
            code = e.returncode
            out = e.output
            return CompletedProcess(command, code, stderr=decode(out))
        return CompletedProcess(command, code, stdout=decode(out))


def flatten(l):
    for el in l:
        if isinstance(el, list) and not isinstance(el, (str, bytes)):
            yield from flatten(el)
        else:
            yield el


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
        script_list.append(snippet.strip())
    elif isinstance(snippet, list):
        stripped = [i.strip() for i in snippet]
        script_list.extend(stripped)
    else:
        print("travis script not string or list: {}".format(snippet))


def run_scripts(logger, script_list, cwd=None):
    if isinstance(script_list, str):
        script_list = [script_list]
    elif not isinstance(script_list, list):
        logger.err_log.print_error(logger.idx, "travis script not string or list")
        logger.output_log.print_error(
            logger.idx, "travis script not string or list: {}".format(script_list)
        )
        return True
    for cmd in script_list:
        substitution = run(
            ["bash", "-c", 'echo "{}"'.format(cmd)], stdout=PIPE, stderr=PIPE
        )
        print("TRAVIS: {}".format(substitution.stdout.decode("utf-8")))
        out = run(
            ["bash", "-c", cmd], cwd, stderr=subprocess.PIPE, stdout=subprocess.PIPE
        )
        if out.returncode != 0:
            logger.output_log.print_error(
                logger.idx,
                "running command \n{}   failed: {}".format(
                    substitution.stdout.decode("utf-8"), out.stderr.decode("utf-8")
                ),
            )
            logger.error_log.print_error(
                logger.idx,
                "bash command execution failed: {}".format(out.stderr.decode("utf-8")),
            )
            logger.error_log.print_info(logger.idx, out.stdout.decode("utf-8"))
            return False
        print(out.stdout.decode("utf-8"))
    return True


def apt_install(logger, pkgs):
    cmd = "apt-get install -y --force-yes --no-install-recommends "
    if isinstance(pkgs, str):
        cmd += pkgs
    elif isinstance(pkgs, list):
        pkgs = list(flatten(pkgs))
        if all(isinstance(i, str) for i in pkgs):
            cmd += " ".join(pkgs)
        else:
            logger.error_log.print_error(
                logger.idx, "apt installer was not str or list[str]: {}".format(pkgs)
            )
            return False
    else:
        logger.error_log.print_error(
            logger.idx, "apt installer was not str or list[str]: {}".format(pkgs)
        )
        return False
    print("APT INSTALL: {}".format(pkgs))
    out = run(["bash", "-c", cmd], stderr=PIPE)
    if out.returncode != 0:
        print(out)
        logger.error_log.print_error(
            logger.idx, "apt_packages install from .travis.yml failed"
        )
        logger.error_log.print_error(
            logger.idx, "{}:\n{}".format(out.args, out.stderr.decode("utf-8"))
        )
        if "Unable to locate package " in out.stderr.decode("utf-8"):
            # some packages could not be found, let's remove them
            for l in out.stderr.decode("utf-8").splitlines():
                index = l.find("Unable to locate package ")
                if index >= 0:
                    pkg = l[index + len("Unable to locate package ") :].strip()
                    cmd = cmd.replace(pkg, "")
                    print("retrying without {}".format(pkg))
            out = run(["bash", "-c", cmd], stderr=PIPE)
            if out.returncode == 0:
                return True
        if "has no installation candidate" in out.stderr.decode("utf-8"):
            for l in out.stderr.decode("utf-8").splitlines():
                pattern = (
                    re.escape("E: Package '")
                    + r"(.*)"
                    + re.escape("' has no installation candidate")
                )
                r = re.search(pattern, l)
                if r:
                    cmd = cmd.replace(r[1], "")
                    print("retrying without {}".format(r[1]))
            out = run(["bash", "-c", cmd], stderr=PIPE)
            if out.returncode == 0:
                return True
        return False
    return True
