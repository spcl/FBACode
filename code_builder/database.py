import os
from os import makedirs
from time import time
from os.path import join, exists
from shutil import rmtree

from .repository import GitProject
from git import Repo, GitCommandError, InvalidGitRepositoryError


class GitHub:
    def __init__(self, build_dir, ctx):
        self.build_dir = build_dir
        self.ctx = ctx
        self.clone_time = 0

    def clone(self, idx, name, project):

        start = time()
        repository_path = project["codebase_data"]["git_url"]
        git_repo = GitProject(
            repository_path,
            project["codebase_data"]["default_branch"],
            self.ctx.cfg,
            self.ctx.out_log,
        )
        source_dir = git_repo.clone(self.build_dir, idx)
        # check for updates
        if project["status"] == "new":
            project["status"] = "cloned"
        if "source" not in project:
            project["source"] = {"dir": os.path.abspath(source_dir)}
        end = time()
        project["source"]["time"] = end - start
        self.ctx.out_log.print_info(
            idx, "Cloned project %s from GitHub in %f seconds" % (name, end - start)
        )
        return (idx, name, project)


class debian:
    def __init__(self, build_dir, ctx):
        self.build_dir = build_dir
        self.ctx = ctx
        self.clone_time = 0

    def clone(self, idx, name, project):

        # cloning should be done in the docker container
        # also getting dependencies since we maybe wont have access to apt on host
        # TODO: maybe do fetching in separate container to building?
        # would also make it possible to time the download etc.
        # print("cloning debian package {}".format(name))
        # create a file called .debianbuild, so we can recognize later
        if project["status"] == "new":
            project["status"] = "cloned"
        if "source" not in project:
            project["source"] = {"dir": os.path.abspath(join(self.build_dir, name))}
        project["source"]["time"] = 0
        self.ctx.out_log.print_info(idx, "initialized debian package {}".format(name))
        makedirs(join(self.build_dir, name), exist_ok=True)
        open(join(self.build_dir, name, ".debianbuild"), "a").close()
        return (idx, name, project)

class conan_cloner:
    def __init__(self, build_dir, ctx):
        self.build_dir = build_dir
        self.ctx = ctx
        self.clone_time = 0

    def clone(self, idx, name, project):
        # the copy is going to happen in the actual build container

        if project["status"] == "new":
            project["status"] = "cloned"
        if "source" not in project:
            project["source"] = {"dir": os.path.abspath(join(self.build_dir, name))}
        project["source"]["time"] = 0
        self.ctx.out_log.print_info(idx, "initialized conan package {}".format(name))
        makedirs(join(self.build_dir, name), exist_ok=True)
        open(join(self.build_dir, name, ".conanbuild"), "a").close()
        
        # First need to get the conan file from the conan-center-index remote
        start = time()
        _, _, recipe_dir = self._get_recipe(idx, name)
        
        # check for updates
        if project["status"] == "new":
            project["status"] = "cloned"

        
        if "source" not in project:
            project["source"] = {"dir": os.path.abspath(join(self.build_dir, name))}
        end = time()
        project["source"]["time"] = end - start
        self.ctx.out_log.print_info(
            idx, "Cloned project %s from GitHub in %f seconds" % (name, end - start)
        )
        return (idx, name, project)


        if project["status"] == "new":
            project["status"] = "cloned"
        if "source" not in project:
            project["source"] = {"dir": os.path.abspath(join(self.build_dir, name))}
        project["source"]["time"] = 0
        self.ctx.out_log.print_info(idx, "initialized conan package {}".format(name))
        makedirs(join(self.build_dir, name), exist_ok=True)
        # open(join(self.build_dir, name, ".debianbuild"), "a").close()
        return (idx, name, project)

databases = {"github.org": GitHub, "debian": debian, "conan": conan_cloner}


def get_database(name):
    return databases[name]
