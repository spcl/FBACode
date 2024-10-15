import collections
import os
from datetime import datetime
from sys import stdout, stderr, exit
from configparser import ConfigParser
from os import path

import subprocess
from sys import version_info
from subprocess import CalledProcessError, CompletedProcess


from . import logger


def info(*args, **kwargs):
    print(*args, file=stdout, **kwargs)


# https://stackoverflow.com/questions/5574702/how-to-print-to-stderr-in-python
def error(*args, **kwargs):
    print(*args, file=stderr, **kwargs)


def open_logfiles(cfg, name="out.log", timestamp=""):
    verbose = cfg["output"]["verbose"]
    LogFiles = collections.namedtuple('LogFiles', ['stdout', 'stderr', 'stdout_file', 'stderr_file'])
    if "file" in cfg["output"]:
        output_log, output_file = logger.create_file_logger(
            filename="%s_%s" % (path.join(cfg["output"]["file"], "output"), name),
            time=timestamp,
            verbose=verbose,
        )
        error_log, error_file = logger.create_file_logger(
            filename="%s_%s" % (path.join(cfg["output"]["file"], "error"), name),
            time=timestamp,
            verbose=verbose,
        )
        return LogFiles(stdout=output_log, stderr=error_log, stdout_file=output_file, stderr_file=error_file)
    else:
        output_log = logger.create_stream_logger(
            name="output", stream=stdout, verbose=verbose
        )
        error_log = logger.create_stream_logger(
            name="error", stream=stderr, verbose=verbose
        )

        return LogFiles(stdout=output_log, stderr=error_log, stdout_file=None, stderr_file=None)


from collections import OrderedDict

# change default behavior of ConfigParser
# instead of overwriting sections with same key,
# accumulate the results
class multidict(OrderedDict):
    def __setitem__(self, key, val):
        if isinstance(val, dict):
            if key in self:
                self.update(key, {**self.get(key), **val})
                return
        OrderedDict.__setitem__(self, key, val)


def open_config(parsed_args, exec_dir):

    cfg = ConfigParser(dict_type=multidict, strict=False)
    default_cfg = parsed_args.config_file
    user_cfg = parsed_args.user_config_file
    cfg_file = path.join(exec_dir, default_cfg)
    # Main config file
    if path.exists(default_cfg):
        info("Opening config file %s" % default_cfg)
    # if file not provided, use the one located in top project directory
    elif path.exists(path.join(exec_dir, default_cfg)):
        default_cfg = path.join(exec_dir, default_cfg)
        info("Opening default config file %s" % default_cfg)
    else:
        error("Config file %s not found! Abort." % default_cfg)
        exit(1)

    # User config file
    if path.exists(user_cfg):
        info("Opening user config file %s" % user_cfg)
    # if file not provided, use the one located in top project directory
    elif path.exists(path.join(exec_dir, user_cfg)):
        user_cfg = path.join(exec_dir, user_cfg)
        info("Opening default user config file %s" % user_cfg)
    else:
        error("User config file %s not found! Continue." % user_cfg)

    cfg.read([user_cfg, default_cfg])
    return cfg

def decode(stream):
    if isinstance(stream, bytes) or isinstance(stream, bytearray):
        return stream.decode("utf-8")
    else:
        return stream
    
def run(command, cwd=None, stdout=None, stderr=None, capture_output = False, text = False) -> CompletedProcess:
    # Python 3.5+ - subprocess.run
    # older - subprocess.call
    # TODO: capture_output added in 3.7 - verify it works
    if version_info.major >= 3 and version_info.minor >= 7:
        out = subprocess.run(command, cwd=cwd, capture_output=capture_output, text=True)
        return CompletedProcess(
            out.args, out.returncode, stdout=decode(out.stdout), stderr=decode(out.stderr)
        )
    if version_info.major >= 3 and version_info.minor >= 5:
        out = subprocess.run(command, cwd=cwd, stdout=stdout, stderr=stderr)
        return CompletedProcess(
            out.args, out.returncode, decode(out.stdout), decode(out.stderr)
        )
    else:
        code = 0
        try:
            out = subprocess.check_output(command, cwd=cwd, stderr=subprocess.STDOUT)
        except CalledProcessError as e:
            code = e.returncode
            out = e.output
            return CompletedProcess(command, code, stderr=decode(out))
        return CompletedProcess(command, code, stdout=decode(out))

def recursively_get_files(directory, ext = ""):
    files = []
    for root, dirs, filenames in os.walk(directory):
        for filename in filenames:
            if filename.endswith(ext):
                files.append(path.join(root, filename))
    return files

def recursively_get_files_containing(directory, substr = ""):
    files = []
    for root, dirs, filenames in os.walk(directory):
        for filename in filenames:
            if substr in filename:
                files.append(path.join(root, filename))
    return files

def recursively_get_dirs(directory):
    directories = []
    for root, dirs, filenames in os.walk(directory):
        for d in dirs:
            directories.append(path.join(root, d))
    return directories
