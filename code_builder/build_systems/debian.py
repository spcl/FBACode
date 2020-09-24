import shutil
import subprocess

from os.path import abspath, join, isfile, dirname, isdir, exists
from os import listdir, makedirs, mkdir, remove
from sys import version_info
from glob import iglob
from re import search, escape


def decode(stream):
    return stream.decode("utf-8")


def run(command, cwd=None, stdout=None, stderr=None):

    # Python 3.5+ - subprocess.run
    # older - subprocess.call
    # TODO: capture_output added in 3.7 - verify it works
    if version_info.major >= 3 and version_info.minor >= 5:
        return subprocess.run(
            command, cwd=cwd,
            stdout=stdout,
            stderr=stderr,
            text=True
        )
    else:
        return subprocess.call(
            command,
            cwd=cwd,
            stdout=stdout,
            stderr=stderr,
            text=True
        )


class Context:
    def __init__(self, cfg):
        self.cfg = cfg

    def set_loggers(self, out, err):
        self.out_log = out
        self.err_log = err


class Project:
    CONTAINER_NAME = "mcopik/fbacode:debian-buster"

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
        # c_compiler = get_c_compiler()
        # cxx_compiler = get_cxx_compiler()
        temp = join(self.build_dir, "..")
        # mkdir(temp)
        out = run(["apt-get", "source", "-y", self.name],
                  cwd=temp, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if out.returncode != 0:
            self.error_log.print_error(self.idx, str(out.stderr))
            return False
        self.output_log.print_info(self.idx, str(out))
        # find out the name of the source code folder
        out = out.stdout
        replace_name = search(r"(?<=Picking ').*(?=' as source package instead of \'{0}\')".format(self.name), out)
        if replace_name:
            # apt chose a package with a different name:
            self.name = replace_name[0]
            print(replace_name[0])
        version = search(r"(?<= {0} ).*(?= \(dsc\) )".format(escape(self.name)), out)[0]

        sourcedir = search(r"(?<=extracting {0} in ).*(?=\n)".format(escape(self.name)), out)[0]

        sourcedir = join(temp, sourcedir)
        # TODO delete everything except logs from source directory
        buildfiles = listdir(self.build_dir)
        sourcefiles = listdir(self.repository_path)
        try:
            for f in buildfiles:
                if ".log" in f:
                    continue
                p = join(self.build_dir, f)
                if isdir(p):
                    shutil.rmtree(p)
                else:
                    remove(p)
            # delete source dir, othewise mv fails
            for f in sourcefiles:
                p = join(self.repository_path, f)
                if isdir(p):
                    shutil.rmtree(p)
                else:
                    remove(p)
            # # copy sources into the build volume
            # sources = listdir(sourcedir)
            # self.output_log.print_debug(self.idx, sources)
            # for f in sources:
            #     dest = join(self.build_dir, f)
            #     src = join(sourcedir, f)
            #     if isdir(src):
            #         # if exists(dest):
            #         #     shutil.rmtree(dest)
            #         # self.output_log.print_debug(self.idx, "copying directory {} to {}".format(dest, src))
            #         shutil.copytree(src, dest, symlinks=False)
            #     else:
            #         # if exists(dest):
            #         #     remove(dest)
            #         # self.output_log.print_debug(self.idx, "copying file {} to {}".format(dest, src))
            #         shutil.copy(src, dest, follow_symlinks=False)
            # # and move to sources volume
            # for f in sources:
            #     src = join(sourcedir, f)
            #     repo_dest = join(self.repository_path, f)
            #     if isdir(src):
            #         if exists(repo_dest):
            #             shutil.rmtree(repo_dest)
            #         shutil.move(src, repo_dest)
            #     else:
            #         if exists(repo_dest):
            #             remove(repo_dest)
            #         shutil.move(src, repo_dest)
        except Exception as e:
            self.error_log.print_error(self.idx, e)
            return False
        # try copying using the shell instead of shutil, since we know we use linux and 
        # this seems to work better regarding symlinks
        # use sh -c "cp ..."here, so we can use globbing
        
        out = run(["sh", "-c", "cp -a {}/* {}".format(sourcedir, self.build_dir)], cwd=temp, stderr=subprocess.PIPE)
        if out.returncode != 0:
            self.error_log.print_error(self.idx, str(out))
            return False
        out = run(["mv", sourcedir, self.repository_path], cwd=temp, stderr=subprocess.PIPE)
        if out.returncode != 0:
            self.error_log.print_error(self.idx, str(out.stderr))
            return False
        # fetch dependencies
        
        out = run(["apt-get", "build-dep", "-y", self.name],
                  cwd=self.repository_path,
                  stderr=subprocess.PIPE)
        if out.returncode != 0:
            self.error_log.print_error(self.idx, str(out.stderr))
            return False
        self.output_log.print_info(self.idx, str(out))
        # https://stackoverflow.com/questions/33278928/how-to-overcome-aclocal-1-15-is-missing-on-your-system-warning
        # this sometimes fails, but no big deal
        try:
            out = run(["autoreconf", "-f", "-i"], cwd=self.build_dir,
                      stderr=subprocess.PIPE)
            if out.returncode != 0:
                self.output_log.print_error(self.idx, str(out))
            else:
                self.output_log.print_info(self.idx, str(out))
        except Exception as e:
            self.output_log.print_info(self.idx, "autoreconf is not installed, error: {}".format(e))
        out = run([join("debian", "rules"), "clean"],
                  cwd=self.build_dir, 
                  stderr=subprocess.PIPE)
        if out.returncode != 0:
            self.error_log.print_error(self.idx, str(out.stderr))
            return False
        self.output_log.print_info(self.idx, str(out))
        return version

    def build(self):
        # basically run debian/rules
        out = run([join("debian", "rules"), "build"],
                  cwd=self.build_dir, 
                  stderr=subprocess.PIPE)
        if out.returncode != 0:
            self.error_log.print_error(self.idx, str(out.stderr))
            return False
        self.error_log.print_info(self.idx, str(out.stderr))
        self.output_log.print_info(self.idx, str(out))
        return True

    def generate_bitcodes(self, target_dir):
        # maybe copy from cmake.py?

        for file in iglob("{0}/**/*.bc".format(self.build_dir), recursive=True):
            # debian has .bc files in normal build dir
            res = search(r"{}".format(self.build_dir), file)
            local_path = file[res.end(0) + 1:]
            makedirs(join(target_dir, dirname(local_path)), exist_ok=True)
            # os.rename does not work for target and destinations being on
            # different filesystems
            # we might operate on different volumes in Docker
            shutil.move(file, join(target_dir, local_path))
        return True
    
    def generate_ast(self, target_dir):
        for file in iglob("{0}/**/*.ast".format(self.build_dir), recursive=True):
            # debian has .bc files in normal build dir
            res = search(r"{}".format(self.build_dir), file)
            local_path = file[res.end(0) + 1:]
            makedirs(join(target_dir, dirname(local_path)), exist_ok=True)
            # os.rename does not work for target and destinations being on
            # ifferent filesystems
            # we might operate on different volumes in Docker
            shutil.move(file, join(target_dir, local_path))
        return True

    def clean(self):
        out = run(["debian/rules", "clean"], cwd=self.repository_path)
        return out.returncode == 0

    @staticmethod
    def recognize(repo_dir):
        # if this file exists, we can build it using debian tools
        # we created this file in database.py so we can recognize it now
        return isfile(join(repo_dir, ".debianbuild"))
