import sys
import subprocess
import os
from sys import stderr


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


def run_scripts(logger, script_list):
    if isinstance(script_list, str):
        script_list = [script_list]
    elif not isinstance(script_list, list):
        logger.error_log.print_error(
            logger.idx, "travis script not string or list: {}".format(script_list))
        return True
    for cmd in script_list:
        substitution = run(["bash", "-c", 'echo "{}"'.format(cmd)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("TRAVIS: {}".format(substitution.stdout.decode("utf-8")))
        out = run(["bash", "-c", cmd], cwd=logger.build_dir,
                  stderr=subprocess.PIPE)
        if out.returncode != 0:
            logger.error_log.print_error(
                logger.idx, "running command \n{}\nfailed".format(substitution.stdout.decode("utf-8")))
            logger.error_log.print_error(logger.idx, "{}:\n{}".format(
                out.args, out.stderr.decode("utf-8")))
            return False
    return True
