import shutil
import subprocess

from os.path import abspath, join, isfile, dirname, isdir
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
        return subprocess.run(command, cwd=cwd, stdout=stdout, stderr=stderr, text=True)
    else:
        return subprocess.call(command, cwd=cwd, stdout=stdout, stderr=stderr, text=True)


class Context:
    def __init__(self, cfg):
        self.cfg = cfg

    def set_loggers(self, out, err):
        self.out_log = out
        self.err_log = err


class project:
    def __init__(self, repo_dir, build_dir, idx, ctx, name):
        self.repository_path = repo_dir
        self.build_dir = build_dir
        self.idx = idx
        self.ctx = ctx
        self.output_log = ctx.out_log
        self.error_log = ctx.err_log
        self.name = name

    def configure(self, force_update=False):
        # fetch the source code and dependencies
        # apt-get source XXX
        # apt-get build-dep XXX
        temp = abspath("temp")
        mkdir(temp)
        out = run(["apt-get", "source", "-y", self.name], cwd=temp, stdout=subprocess.PIPE)
        if out.returncode != 0:
            return False
        # find out the name of the source code folder
        out = out.stdout
        search_str = "extracting {} in ".format(self.name)
        out = out[out.find(search_str)+len(search_str):]
        out = out[:out.find("\n")]
        # out should now contains the name of the source folder
        sourcedir = join(temp, out)
        # move sources into the source volume
        sources = listdir(sourcedir)
        for f in sources:
            if isdir(join(sourcedir, f)):
                shutil.copytree(join(sourcedir, f), join(self.build_dir, f))
            else:
                shutil.copy(join(sourcedir, f), join(self.build_dir))
            # shutil.rmtree(self.repository_path)
            shutil.move(join(sourcedir, f), join(self.repository_path, f))
        # fetch dependencies
        run(["apt-get", "build-dep", "-y", self.name], cwd=self.repository_path)
        return True

    def build(self):
        # basically run debian/rules
        out = run([join("debian", "rules"), "build"], cwd=self.build_dir)
        
        return out.returncode == 0

    def generate_bitcodes(self, target_dir):
        # maybe copy from cmake.py?

        for file in iglob("{0}/**/*.bc".format(self.build_dir), recursive=True):
            # debian has .bc files in normal build dir
            res = search(r"{}".format(self.build_dir), file)
            local_path = file[res.end(0) + 1 :]
            makedirs(join(target_dir, dirname(local_path)), exist_ok=True)
            # os.rename does not work for target and destinations being on different filesystems
            # we might operate on different volumes in Docker
            shutil.move(file, join(target_dir, local_path))
        return True

    def clean(self):
        out = run(["debian/rules", "clean"], cwd=self.repository_path)
        return out.returncode == 0

    def recognize(repo_dir):
        # if this file exists, we can build it using debian tools
        # this will not work since we do not have source downloaded yet...
        return isfile(join(repo_dir, ".debianbuild"))