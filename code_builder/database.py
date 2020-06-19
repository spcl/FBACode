import sys, os
from os import path
from time import time

from .repository import GitProject
from .utils.logger import create_stream_logger


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
        if not "source" in project:
            project["source"] = { "dir": os.path.abspath(source_dir) }
        end = time()
        project["source"]["time"] = end - start
        self.ctx.out_log.print_info(
            idx, "Cloned project %s from GitHub in %f seconds" % (name, end - start)
        )
        return (idx, name, project)


databases = {"github.org": GitHub}


def get_database(name):
    return databases[name]
