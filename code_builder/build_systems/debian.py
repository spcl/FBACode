import shutil
import subprocess

from os.path import join, isfile, dirname, isdir
from os import listdir, makedirs, remove
from re import search, escape
import pathlib

from .utils import run


class Context:
    def __init__(self, cfg):
        self.cfg = cfg

    def set_loggers(self, out, err):
        self.out_log = out
        self.err_log = err


class Project:
    CONTAINER_NAME = "mcopik/fbacode:debian-buster"

    def __init__(self, repo_dir, build_dir, idx, ctx, name, project):
        self.repository_path = repo_dir
        self.build_dir = build_dir
        self.idx = idx
        self.ctx = ctx
        self.output_log = ctx.out_log
        self.error_log = ctx.err_log
        self.name = name
        self.project = project

    def configure(self, force_update=False):
        # fetch the source code and dependencies
        # c_compiler = get_c_compiler()
        # cxx_compiler = get_cxx_compiler()
        temp = join(self.build_dir, "..")
        # mkdir(temp)
        out = run(
            ["apt-get", "source", "-y", self.name],
            cwd=temp,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if out.returncode != 0:
            self.error_log.print_error(self.idx, out.stderr)
            return False
        self.output_log.print_info(self.idx, "{}:\n{}".format(out.args, out.stderr))
        # find out the name of the source code folder
        out = out.stdout
        replace_name = search(
            r"(?<=Picking ').*(?=' as source package instead of \'{0}\')".format(
                escape(self.name)
            ),
            out,
        )
        if replace_name:
            # apt chose a package with a different name:
            self.name = replace_name[0]
            print(replace_name[0])
        version = search(r"(?<= {0} ).*(?= \(dsc\) )".format(escape(self.name)), out)[0]
        self.project["build"]["built_version"] = version
        sourcedir = search(
            r"(?<=extracting {0} in ).*(?=\n)".format(escape(self.name)), out
        )[0]

        sourcedir = join(temp, sourcedir)
        self.temp_build_dir = sourcedir
        # delete everything except logs from source directory
        # buildfiles = listdir(self.build_dir)
        sourcefiles = listdir(self.repository_path)
        try:
            for f in sourcefiles:
                p = join(self.repository_path, f)
                if isdir(p):
                    shutil.rmtree(p)
                else:
                    remove(p)

        except Exception as e:
            self.error_log.print_error(self.idx, e)
            return False
        # try copying using the shell instead of shutil, since we know we use linux and
        # this seems to work better regarding symlinks
        # use sh -c "cp ..."here, so we can use globbing

        out = run(
            [
                "bash",
                "-c",
                "shopt -s dotglob; cp -a {}/* {}".format(
                    sourcedir, self.repository_path
                ),
            ],
            cwd=temp,
            stderr=subprocess.PIPE,
        )
        if out.returncode != 0:
            self.error_log.print_error(self.idx, "{}:\n{}".format(out.args, out.stderr))
            return False
        return version

    def build(self):
        # basically run debian/rules
        # dpgk-source -b
        # out = run([join("debian", "rules"), "build"],
        #           cwd=self.build_dir,
        #           stderr=subprocess.PIPE)
        print("starting actual build...")
        # we skip build dependencies so we can detect the diff from missing -> installed
        # -i to ignore changes
        out = run(
            ["dpkg-buildpackage", "--no-sign", "--no-check-builddeps", '-i="*"'],
            cwd=self.temp_build_dir,
            stderr=subprocess.PIPE,
        )
        print("done building")
        print(out.stderr)
        if out.returncode != 0:
            self.error_log.print_error(self.idx, str(out.stderr))
            return False
        self.error_log.print_info(self.idx, str(out.stderr))
        self.output_log.print_info(self.idx, "{}:\n{}".format(out.args, out.stderr))
        # move build files to attached volume
        for f in listdir(self.build_dir):
            if ".log" in f:
                continue
            p = join(self.build_dir, f)
            if isdir(p):
                shutil.rmtree(p)
            else:
                remove(p)
        temp = join(self.build_dir, "..")
        out = run(
            [
                "bash",
                "-c",
                "shopt -s dotglob; mv -f {}/* {}".format(
                    self.temp_build_dir, self.build_dir
                ),
            ],
            cwd=temp,
            stderr=subprocess.PIPE,
        )
        if out.returncode != 0:
            self.error_log.print_error(self.idx, "{}:\n{}".format(out.args, out.stderr))
            return False
        return True

    def generate_bitcodes(self, target_dir):
        for file in pathlib.Path(self.build_dir).glob("**/*.bc"):
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

    def generate_ast(self, target_dir):
        for file in pathlib.Path(self.build_dir).glob("**/*.ast"):
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
        out = run(["debian/rules", "clean"], cwd=self.repository_path)
        return out.returncode == 0

    @staticmethod
    def recognize(repo_dir):
        # if this file exists, we can build it using debian tools
        # we created this file in database.py so we can recognize it now
        return isfile(join(repo_dir, ".debianbuild"))
