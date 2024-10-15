import shutil
import subprocess
import os

from os.path import join, isfile, dirname, isdir
from os import listdir, makedirs, mkdir, remove
from subprocess import PIPE
from shutil import rmtree
from re import search
import pathlib

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
        self.COPY_SRC_TO_BUILD = True

    def copy_src(self):
        # clean build dir
        for f in listdir(self.build_dir):
            if ".log" in f:
                continue
            p = join(self.build_dir, f)
            if isdir(p):
                shutil.rmtree(p)
            else:
                remove(p)
        # copy over source files
        cmd = [
            "bash",
            "-c",
            "shopt -s dotglob; cp -a {}/* {}".format(
                self.repository_path, self.build_dir
            ),
        ]
        out = run(cmd, cwd=self.repository_path, stderr=subprocess.PIPE)
        if out.returncode != 0:
            self.error_log.print_error(self.idx, "{}:\n{}".format(out.args, out.stderr))
            return False
        return True

    def configure(self, force_update=True):
        # run autoreconf -i --force
        # then run the ./configure
        c_compiler = get_c_compiler()
        cxx_compiler = get_cxx_compiler()
        os.environ["CC"] = c_compiler
        os.environ["CXX"] = cxx_compiler
        # if isfile(join(self.repository_path, ".travis.yml")):
        #     if not parse_travis(self, self.repository_path):
        #         self.error_log.print_error(
        #             self.idx,
        #             "error trying to install dependencies using travis!")
        #     else:
        #         self.project["build"]["travis_installer"] = True
        if force_update:
            # clean build dir and copy source over
            # we cant always build in separate directory from build
            autogen_failed = False
            if isfile(join(self.build_dir, "autogen.sh")):
                ret = run(
                    ["./autogen.sh"], cwd=self.build_dir, stdout=PIPE, stderr=PIPE
                )
                if ret.returncode:
                    self.error_log.print_error(
                        self.idx, "Failed make autogen.sh command"
                    )
                    self.error_log.print_error(self.idx, ret.stderr)
                    autogen_failed = True
                else:
                    self.output_log.print_info(
                        self.idx,
                        "autogen.sh succeeded".format(
                            self.repository_path, self.build_dir
                        ),
                    )
                    self.output_log.print_debug(self.idx, "autogen.sh:")
                    self.output_log.print_debug(self.idx, ret.stdout)
            if not isfile(join(self.build_dir, "autogen.sh")) or autogen_failed:
                print("no autogen.sh, running autoreconf -i --force")
                cmd = ["autoreconf", "-i", "--force", "--verbose"]
                out = run(cmd, cwd=self.repository_path, stderr=subprocess.PIPE)
                if out.returncode != 0:
                    self.error_log.print_error(
                        self.idx, "{}:\n{}".format(out.args, out.stderr)
                    )
            if isfile(join(self.build_dir, "configure")):
                ret = run(["./configure"], cwd=self.build_dir, stdout=PIPE, stderr=PIPE)
                if ret.returncode:
                    self.error_log.print_error(
                        self.idx, "Failed make configure command"
                    )
                    self.error_log.print_error(self.idx, ret.stderr)
                    return False
                else:
                    self.output_log.print_info(
                        self.idx,
                        "Configure {} to build in {}".format(
                            self.repository_path, self.build_dir
                        ),
                    )
                    self.output_log.print_debug(self.idx, "make configure command")
                    self.output_log.print_debug(self.idx, ret.stdout)
            else:
                self.error_log.print_error(self.idx, "No ./configure, this is not good")
                return True
        return True

    def build(self):
        j = os.environ.get("JOBS", 1)
        cmd = ["make", "-j{}".format(j)]
        ret = run(cmd, cwd=self.build_dir, stderr=PIPE)
        if ret.returncode:
            self.error_log.print_error(self.idx, ret.stderr)
            return False
        else:
            self.output_log.print_info(self.idx, "Build in {}".format(self.build_dir))
            self.output_log.print_debug(
                self.idx, "CMake build command: {}".format(" ".join(cmd))
            )
            # self.output_log.print_debug(self.idx, ret.stdout)
            return True

    def generate_bitcodes(self, target_dir):
        for file in pathlib.Path(self.build_dir).glob("**/*.bc"):
            # CMake file format: {build_dir}/../CMakeFiles/{dir}.dir/relative_bc_location
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
            res = search(r"{}".format(self.build_dir), str(file))
            if res is None:
                self.error_log.print_error(
                    self.idx, "error while globbing for .ast files: {}".format(file)
                )
                continue
            local_path = str(file)[res.end(0) + 1 :]
            makedirs(join(target_dir, dirname(local_path)), exist_ok=True)
            shutil.copy(str(file), join(target_dir, local_path))
        return True

    def clean(self):
        build_dir = self.repository_path + "_build"
        rmtree(build_dir)
        mkdir(build_dir)

    @staticmethod
    def recognize(repo_dir):
        return (
            isfile(join(repo_dir, "Makefile.am"))
            or isfile(join(repo_dir, "configure.in"))
            or isfile(join(repo_dir, "configure.ac"))
        )

    @staticmethod
    def get_docker_image(repo_dir, clang_version=9):
        return "spcleth/fbacode:ubuntu-2004-clang-{}".format(clang_version)
