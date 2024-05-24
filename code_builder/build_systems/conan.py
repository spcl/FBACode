import shutil
import subprocess
import yaml

from os.path import join, isfile, dirname, isdir, exists
from os import listdir, makedirs, remove
from re import search, escape
from shutil import rmtree
import pathlib
import os
from time import time

from .utils import run
from git import Repo, GitCommandError, InvalidGitRepositoryError


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

        self.name = name[: name.rfind("@")]
        self.name_and_version = name

        self.project = project
        self.COPY_SRC_TO_BUILD = False
        self.version = project["build"]["version"]
        self.conanfile = None
        self.remote_package_folder = None

    def get_remote_package_folder(self):
        return self.remote_package_folder

    def _get_recipe(self):
        # How do I clone a subdirectory only of a Git repository?
        # https://stackoverflow.com/questions/600079/how-do-i-clone-a-subdirectory-only-of-a-git-repository
        repository_path = "https://github.com/conan-io/conan-center-index.git"
        repository_branch = "origin/master"

        repo_location = "/tmp/conan-center-index"
        self.ctx.out_log.print_info(
            self.idx, f"Cloning the recipe {self.name_and_version} from conan-center-index"
        )

        if exists(repo_location):
            try:
                self.cloned_repo = Repo(repo_location)
            except InvalidGitRepositoryError:
                # the existing directory is not a git repo...
                # let's delete it and redownload
                self.ctx.out_log.print_info(
                    self.idx,
                    "source directory exists but is not git repo, redownloading conan-center-index",
                )
                rmtree(repo_location)
        if not exists(repo_location):
            conan_center_repo = Repo.clone_from(
                repository_path, repo_location, depth=1, no_checkout=True
            )
            conan_center_repo.git.checkout(
                repository_branch, "--", f"recipes/{self.name}"
            )
        
        with open(join(repo_location, "recipes", self.name, "config.yml"), "r") as fin:
            try:
                data = yaml.safe_load(fin)
                self.remote_package_folder = join(repo_location, "recipes", self.name, data["versions"][self.version]["folder"])
            except yaml.YAMLError as e:
                print(f"Error reading YAML file: {e}")
                return False
            except Exception as e:
                # file doesn't exist, is corrupted, etc...
                print(f"Error processing file: {e}")
                return False

        return join(repo_location, "recipes", self.name)

    def copy_src(self):
        # we are using the conanfile.py recipe and auxiliary files from the conan-center-index repository
        # we need to download the recipe first:
        temp = join(self.build_dir, "..")
        start = time()

        recipe_path = self._get_recipe()
        if recipe_path is False:
            return False
        # recipe_path = join(
        #     recipe_path, self.remote_package_folder
        # )

        # then we use "conan source" to get the actual source code:
        out = run(
            f"conan source --version={self.version} .".split(),
            # ["conan", "source", f"--version={self.version}", "."],
            cwd=self.remote_package_folder,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if out.returncode != 0:
            self.error_log.print_error(self.idx, out.stderr)
            return False

        self.output_log.print_info(self.idx, "{}:\n{}".format(out.args, out.stderr))
        # find out the name of the source code folder
        sourcedir = join(self.remote_package_folder, "src")
        self.conanfile = join(self.remote_package_folder, "conanfile.py")
        self.project["build"]["built_version"] = self.version

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
        end = time()
        self.project["build"]["clone_time"] = end - start
        return True

    def configure(self, force_update=False):
        cmd = f"echo \"tools.build.jobs={os.environ.get('JOBS', 1)}\" >> $(conan config home)/global.conf"
        out = run(cmd.split(), stderr=subprocess.PIPE)
        if out.returncode != 0:
            self.error_log.print_error(self.idx, f"{out.args}:\n{out.stderr}")
            return False

        return True

    def build(self):
        self.output_log.print_info(self.idx, "Calling conan build in {}".format(self.remote_package_folder))
        out = run(
            # f"conan build -of={self.build_dir} --version={self.version} -s compiler=clang -s compiler.cppstd=gnu20 -s compiler.version=18 .".split(),
            f"conan build --version={self.version} -s compiler=clang -s compiler.cppstd=gnu20 -s compiler.version=18 .".split(),
            cwd=self.remote_package_folder,
            stderr=subprocess.PIPE,
        )
        if out.returncode != 0:
            self.error_log.print_error(self.idx, "{}:\n{}".format(out.args, out.stderr))
            return False
        self.error_log.print_info(self.idx, str(out.stderr))
        self.output_log.print_info(self.idx, "{}:\n{}".format(out.args, out.stderr))

        # need to build in the directory of the recipe, cannot pass -of=self build_dir
        # because conan build will look for the patches in the build folder...

        # move build files to attached volume
        for f in listdir(self.build_dir):
            if ".log" in f:
                continue
            p = join(self.build_dir, f)
            if isdir(p):
                shutil.rmtree(p)
            else:
                remove(p)
        # temp = join(self.build_dir, "..")
        out = run(
            [
                "bash",
                "-c",
                "shopt -s dotglob; cp -a {}/build*/* {}".format(
                    self.remote_package_folder, self.build_dir
                ),
            ],
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
            shutil.copy(str(file), join(target_dir, local_path))
            counter += 1
        
        print(f"Globbed {counter} AST files")
        return True

    def clean(self):
        return True
        out = run(["debian/rules", "clean"], cwd=self.repository_path)
        return out.returncode == 0

    @staticmethod
    def recognize(repo_dir):
        # if this file exists, we can build it using debian tools
        # we created this file in database.py so we can recognize it now
        return isfile(join(repo_dir, ".conanbuild"))

    @staticmethod
    def get_docker_image(repo_dir, clang_version=9):
        return "spcleth/fbacode:ubuntu-2204-clang-{}".format(clang_version)
        # return "spcleth/fbacode:debian-bookworm-clang-{}".format(clang_version)
        # return "spcleth/fbacode:debian-bullseye-clang-{}".format(clang_version)
        # return "mcopik/fbacode:debian-buster-clang-{}".format(clang_version)
