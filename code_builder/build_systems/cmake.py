import shutil
import subprocess
import pathlib

from os.path import abspath, join, isfile, dirname
from os import listdir, makedirs, mkdir
from subprocess import PIPE
from shutil import rmtree
from sys import version_info
from glob import iglob
from re import search

from .environment import get_c_compiler, get_cxx_compiler


def decode(stream):
    return stream.decode("utf-8")


def run(command, cwd=None, stdout=None, stderr=None):

    # Python 3.5+ - subprocess.run
    # older - subprocess.call
    # TODO: capture_output added in 3.7 - verify it works
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
    CONTAINER_NAME = "mcopik/fbacode:ubuntu-1804-clang-9"

    def __init__(self, repo_dir, build_dir, idx, ctx):
        self.repository_path = repo_dir
        self.build_dir = build_dir
        self.idx = idx
        self.ctx = ctx
        self.output_log = ctx.out_log
        self.error_log = ctx.err_log

    def configure(self, force_update=False):
        c_compiler = get_c_compiler()
        cxx_compiler = get_cxx_compiler()
        if len(listdir(self.build_dir)) == 0 or force_update:
            c_compiler_opt = "-DCMAKE_C_COMPILER=" + c_compiler
            cpp_compiler_opt = "-DCMAKE_CXX_COMPILER=" + cxx_compiler
            cmd = [
                "cmake",
                abspath(self.repository_path),
                c_compiler_opt,
                cpp_compiler_opt,
            ]
            ret = run(cmd, cwd=self.build_dir, stdout=PIPE, stderr=PIPE)
            if ret.returncode:
                self.error_log.print_info(
                    self.idx, "Failed CMake configure command: %s" % " ".join(cmd)
                )
                self.error_log.print_error(self.idx, decode(ret.stderr))
                return False
            else:
                self.output_log.print_info(
                    self.idx,
                    "Configure %s to build in %s"
                    % (self.repository_path, self.build_dir),
                )
                self.output_log.print_debug(
                    self.idx, "CMake configure command: %s" % " ".join(cmd)
                )
                self.output_log.print_debug(self.idx, decode(ret.stdout))
            return True
        return True

    def build(self):
        cmd = ["cmake", "--build", "."]
        ret = run(cmd, cwd=self.build_dir, stderr=PIPE)
        if ret.returncode:
            self.error_log.print_error(self.idx, ret.stderr.decode("utf-8"))
            return False
        else:
            self.output_log.print_info(self.idx, "Build in %s" % self.build_dir)
            self.output_log.print_debug(
                self.idx, "CMake build command: %s" % " ".join(cmd)
            )
            # self.output_log.print_debug(self.idx, decode(ret.stdout))
            return True

    def generate_bitcodes(self, target_dir):
        for file in iglob("{0}/**/*.bc".format(self.build_dir), recursive=True):
            # CMake file format: {build_dir}/../CMakeFiles/{dir}.dir/relative_bc_location
            res = search(r"CMakeFiles/.*\.dir", file)
            local_path = file[res.end(0) + 1 :]
            makedirs(join(target_dir, dirname(local_path)), exist_ok=True)
            # os.rename does not work for target and destinations being on different filesystems
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
        return isfile(join(repo_dir, "CMakeLists.txt"))
