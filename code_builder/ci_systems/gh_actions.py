from os.path import isdir, join
import os
import yaml
from yaml.loader import FullLoader



class Context:
    def __init__(self, cfg):
        self.cfg = cfg

    def set_loggers(self, out, err):
        self.out_log = out
        self.err_log = err


class CiSystem:
    def __init__(self, repo_dir, build_dir, idx, ctx, project):
        self.repository_path = repo_dir
        self.build_dir = build_dir
        self.idx = idx
        self.ctx = ctx
        self.output_log = ctx.out_log
        self.error_log = ctx.err_log
        self.gh_dir = repo_dir
        self.project = project

    def install(self):
        return True
        yml_files = [f for f in os.listdir(join(self.gh_dir, ".github/workflows"))
                     if ".yml" in f]
        for file in yml_files:
            with open(join(self.gh_dir, ".github/workflows/") + file, "r") as f:
                pass

    @staticmethod
    def recognize(repo_dir):
        return isdir(join(repo_dir, ".github/workflows"))
    
    @staticmethod
    def get_docker_image(repo_dir, clang_version=9):
        return False
