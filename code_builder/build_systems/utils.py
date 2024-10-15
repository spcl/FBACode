import subprocess
import os
import sys
import shutil
from sys import version_info
from subprocess import CalledProcessError, CompletedProcess
from os import path

def decode(stream):
    if isinstance(stream, bytes) or isinstance(stream, bytearray):
        return stream.decode("utf-8")
    else:
        return stream


def run(command, cwd=None, capture_output = False, text = False, stdout = None, stderr = None) -> CompletedProcess:
    # Python 3.5+ - subprocess.run
    # older - subprocess.call
    # TODO: capture_output added in 3.7 - verify it works
    if version_info.major >= 3 and version_info.minor >= 7:
        out = subprocess.run(command, cwd=cwd, capture_output = capture_output, text = text)
        return CompletedProcess(
            out.args, out.returncode, stdout = decode(out.stdout), stderr = decode(out.stderr)
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

def recursively_get_dirs(directory):
    directories = []
    for root, dirs, filenames in os.walk(directory):
        for d in dirs:
            directories.append(path.join(root, d))
    return directories
