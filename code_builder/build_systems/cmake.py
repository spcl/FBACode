import shutil
import pathlib
import os

from os.path import abspath, join, isfile, dirname
from os import listdir, makedirs, mkdir
from subprocess import PIPE
from shutil import rmtree
from re import search

from .environment import get_c_compiler, get_cxx_compiler
from .utils import run


class Context:
    def __init__(self, cfg):
        self.cfg = cfg

    def set_loggers(self, out, err):
        self.out_log = out
        self.err_log = err


class Project:

    def __init__(self, repo_dir, build_dir, idx, ctx, name, project):
        self.repository_path = repo_dir
        self.build_dir = build_dir
        self.idx = idx
        self.ctx = ctx
        self.output_log = ctx.out_log
        self.error_log = ctx.err_log
        self.name = name
        self.project = project

    def configure(self, force_update=True):
        c_compiler = get_c_compiler()
        cxx_compiler = get_cxx_compiler()
        if len(listdir(self.build_dir)) == 0 or force_update:
            # check if we have a travis file and use it to install dependencies
            # if isfile(join(self.repository_path, ".travis.yml")):
            #     if not parse_travis(self, self.repository_path):
            #         self.error_log.print_error(
            #             self.idx,
            #             "error trying to install dependencies using travis!")
            #     else:
            #         self.project["build"]["travis_installer"] = True
            c_compiler_opt = "-DCMAKE_C_COMPILER=" + c_compiler
            cpp_compiler_opt = "-DCMAKE_CXX_COMPILER=" + cxx_compiler
            # cmake_prefix_path = "-DCMAKE_PREFIX_PATH=/usr/lib/llvm-9:{}".format(os.environ.get("CMAKE_PREFIX_PATH", ""))
            # print("CMAKE PATH =", os.environ.get("CMAKE_PREFIX_PATH", ""))
            cmd = [
                "cmake",
                abspath(self.repository_path),
                c_compiler_opt,
                cpp_compiler_opt,
                # cmake_prefix_path,
            ]
            ret = run(cmd, cwd=self.build_dir, stdout=PIPE, stderr=PIPE)
            if ret.returncode:
                self.error_log.print_info(
                    self.idx, "Failed CMake configure command: %s" % " ".join(cmd)
                )
                self.error_log.print_error(self.idx, ret.stderr)
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
                self.output_log.print_debug(self.idx, ret.stdout)
            return True
        return True

    def build(self):
        j = os.environ.get("JOBS", 1)
        cmd = ["cmake", "--build", ".", "-j", str(j)]
        ret = run(cmd, cwd=self.build_dir, stderr=PIPE)
        if ret.returncode:
            self.error_log.print_error(self.idx, "failed cmake build --build command")
            self.error_log.print_error(self.idx, ret.stderr)
            return False
        else:
            self.output_log.print_info(self.idx, "Build in %s" % self.build_dir)
            self.output_log.print_debug(
                self.idx, "CMake build command: %s" % " ".join(cmd)
            )
            # self.output_log.print_debug(self.idx, ret.stdout)
            return True

    def generate_bitcodes(self, target_dir):
        for file in pathlib.Path(self.build_dir).glob("**/*.bc"):
            # CMake file format: {build_dir}/../CMakeFiles/{dir}.dir/relative_bc_location
            res = search(r"CMakeFiles/.*\.dir", str(file))
            if res is None:
                # CMake file format: {build_dir}/../CMakeFiles/relative_bc_location
                res = search(r"CMakeFiles", str(file))
            if res is None:
                # sometimes they are not in the CMakeFiles folder...
                res = search(r"{}".format(self.build_dir), str(file))
            if res is None:
                self.error_log.print_error(
                    self.idx, "error while globbing for .bc files: {}".format(file)
                )
                continue
            local_path = str(file)[res.end(0) + 1 :]
            makedirs(join(target_dir, dirname(local_path)), exist_ok=True)
            # os.rename does not work for target and destinations being
            # on different filesystems
            # we might operate on different volumes in Docker
            shutil.move(str(file), join(target_dir, local_path))

    def generate_ast(self, target_dir):
        for file in pathlib.Path(self.build_dir).glob("**/*.ast"):
            # CMake file format: {build_dir}/../CMakeFiles/{dir}.dir/relative_bc_location
            res = search(r"CMakeFiles/.*\.dir", str(file))
            if res is None:
                # CMake file format: {build_dir}/../CMakeFiles/{dir}.dir/relative_bc_location
                res = search(r"CMakeFiles", str(file))
            if res is None:
                # sometimes they are not in the CMakeFiles folder...
                res = search(r"{}".format(self.build_dir), str(file))
            if res is None:
                self.error_log.print_error(
                    self.idx, "error while globbing for .bc files: {}".format(file)
                )
                continue
            local_path = str(file)[res.end(0) + 1 :]
            makedirs(join(target_dir, dirname(local_path)), exist_ok=True)
            shutil.move(str(file), join(target_dir, local_path))
        return True

    def clean(self):
        build_dir = self.repository_path + "_build"
        rmtree(build_dir)
        mkdir(build_dir)

    @staticmethod
    def recognize(repo_dir):
        return isfile(join(repo_dir, "CMakeLists.txt"))

    @staticmethod
    def get_docker_image(repo_dir, clang_version=9):
        return "mcopik/fbacode:ubuntu-2004-clang-{}".format(clang_version)
