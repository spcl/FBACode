import shutil
import subprocess
import os
import json

from os.path import join, isfile, dirname, isdir
from os import listdir, makedirs, remove
from re import search, escape
import pathlib
from time import time
from shutil import copyfile, copy2

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
        self.COPY_SRC_TO_BUILD = False

    def copy_src(self):
        # debian is a special case, if we move the files from the downloaded dir the build might fail
        # we use the self.temp_build_dir to build the project, which is the downloaded location
        # we don't have anything in the build dir yet, but its ok, since the
        # debian dep installer does not need any source files
        # we just download the source here
        temp = join(self.build_dir, "..")
        start = time()
        # mkdir(temp)
        out = run(
            ["apt-get", "source", "-y", self.name],
            cwd=temp,
            # stdout=subprocess.PIPE,
            # stderr=subprocess.PIPE,
            capture_output=True,
            text=True,
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
                "shopt -s dotglob; cp -ap {}/* {}".format(
                    sourcedir, self.repository_path
                ),
            ],
            cwd=temp,
            stderr=subprocess.PIPE,
        )
        if out.returncode != 0:
            self.error_log.print_error(self.idx, "{}:\n{}".format(out.args, out.stderr))
            return False
        end = time()
        self.project["build"]["clone_time"] = end - start
        return True

    def configure(self, force_update=False):
        # we can not distinguish between a configure step and a build step
        # with dpkg-buildpackage. we run the command in build.
        return True

    def build(self):
        # basically run debian/rules
        # dpgk-source -b
        # out = run([join("debian", "rules"), "build"],
        #           cwd=self.build_dir,
        #           stderr=subprocess.PIPE)
        # we skip build dependencies so we can detect the diff from missing -> installed
        # -i to ignore changes
        jobs_count = os.environ.get("JOBS", 1)

        # https://www.man7.org/linux/man-pages/man1/dpkg-buildpackage.1.html
        # we want to modify the clang calls only during the build stage of the build
        # the buildinfo stage is the one that immediately follows the build stage
        out = run(
            [
                "dpkg-buildpackage",
                "-b", # skip Debian bureaucracy, just build the binary
                "--no-sign",
                "--no-check-builddeps",
                '-i="*"',
                "-j{}".format(jobs_count),
            ],
            cwd=self.temp_build_dir,
            stderr=subprocess.PIPE,
        )
        if out.returncode != 0:
            self.error_log.print_error(self.idx, str(out.stderr))
            return False
        self.error_log.print_info(self.idx, str(out.stderr))
        self.output_log.print_info(self.idx, "{}:\n{}".format(out.args, out.stderr))
        # move build files to attached volume
        for f in listdir(self.build_dir):
            if ".log" in f or f == "header_dependencies":
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
                "shopt -s dotglob; cp -ap {}/* {}".format(
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
        counter = 0
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
            counter += 1
        print(f"Globbed {counter} bitcode files")
        return True

    def generate_ast(self, target_dir):
        counter = 0
        for file in pathlib.Path(self.build_dir).glob("**/*.ast"):
            res = search(r"{}".format(self.build_dir), str(file))
            if res is None:
                self.error_log.print_error(
                    self.idx, "error while globbing for .ast files: {}".format(file)
                )
                continue
            local_path = str(file)[res.end(0) + 1 :]
            makedirs(join(target_dir, dirname(local_path)), exist_ok=True)
            shutil.move(str(file), join(target_dir, local_path))
            # shutil.copy(str(file), join(target_dir, local_path))
            counter += 1
        print(f"Globbed {counter} AST files")
        return True
    
    def save_header_files(self, headers_dir):
        if not os.path.exists(headers_dir):
            os.makedirs(headers_dir)
        # Save the referenced AST files
        relevant_header_files_mapping = dict()

        with open(os.path.join(self.build_dir, "header_dependencies.log"), "w") as fout:
            # go through all files in the header_dependencies/ folder
            for file in os.listdir(os.path.join(self.build_dir, "header_dependencies")):
                if not file.endswith(".log"):
                    continue

                try:
                    with open(os.path.join(self.build_dir, "header_dependencies", file), "r") as fin:
                        content = fin.read()

                        if "\n#" in content:
                            raise Exception("Header dependency file contains comments")

                        fout.write(content)
                        # fout.write('\n\n')
                except Exception as e:
                    print(f"Failed to read header dependency file: {file}")
                    print(e)
                    return False

        # if not os.path.exists(os.path.join(self.build_dir, "header_dependencies.log")):
        #     print("header_dependencies.log file does not exist")
        #     return relevant_header_files_mapping

        with open(os.path.join(self.build_dir, "header_dependencies.log"), "r") as fin:
            header_dependencies_content = fin.read().strip().split('\n\n')

        clang_call_cwd = []
        clang_dependencies_content = []

        for clang_call in header_dependencies_content:
            clang_call_lines = clang_call.split('\n')
            if len(clang_call_lines) < 2:
                continue
            if clang_call_lines[1].startswith("programs:"):
                # some weird format that i don't know how to parse or what to do with it
                continue
            clang_call_cwd.append(clang_call_lines[0])
            clang_dependencies_content.append('\n'.join(clang_call_lines[1:]))
        
        all_headers = []

        for idx, (cwd, clang_dependencies) in enumerate(zip(clang_call_cwd, clang_dependencies_content)):
            tokens = clang_dependencies.split()[1:] # skip the first since its the target name "test.o: ..."
            tokens = [x for x in tokens if not '\\' in x]

            for token in tokens:
                if os.path.isabs(token):
                    all_headers.append(os.path.normpath(token))
                else:
                    all_headers.append(os.path.normpath(os.path.join(cwd, token)))

        all_headers = list(set(all_headers))

        print(f"Found {len(all_headers)} header files that should be saved")

        header_idx = 0
        for header_path in all_headers:
            if not os.path.exists(header_path):
                print("Header file does not actually exist: {}".format(header_path))
                continue
                
            relevant_header_files_mapping[header_idx] = header_path
            # copy2 in order to preserve metadata
            copy2(header_path, os.path.join(headers_dir, str(header_idx)), follow_symlinks=True)
            header_idx += 1

            if header_idx % 50 == 0:
                print(f"Saved {header_idx} header files")
        
        return relevant_header_files_mapping

    def clean(self):
        out = run(["debian/rules", "clean"], cwd=self.repository_path)
        return out.returncode == 0

    @staticmethod
    def recognize(repo_dir):
        # if this file exists, we can build it using debian tools
        # we created this file in database.py so we can recognize it now
        return isfile(join(repo_dir, ".debianbuild"))

    @staticmethod
    def get_docker_image(repo_dir, clang_version=9):
        return "spcleth/fbacode:debian-bookworm-clang-{}".format(clang_version)
