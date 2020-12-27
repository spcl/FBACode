import json
from .ci_helper import apt_install


class Context:
    def __init__(self, cfg):
        self.cfg = cfg

    def set_loggers(self, out, err):
        self.out_log = out
        self.err_log = err


class Installer:
    def __init__(
        self, repo_dir, build_dir, idx, ctx, name, project, dep_mapping_path, missing
    ):
        self.repository_path = repo_dir
        self.build_dir = build_dir
        self.idx = idx
        self.ctx = ctx
        self.output_log = ctx.out_log
        self.error_log = ctx.err_log
        self.project = project
        with open(dep_mapping_path, "r") as f:
            self.dependency_map = json.load(f)
        
        self.missing = missing

    def install(self):
        # let's try to install using previous dependencies (if there are any)
        if self.missing == []:
            print("no depencencies to install")
            return
        pkgs_to_install = []
        for m in self.missing:
            if m in self.dependency_map:
                # we can install the pkgs in here, maybe take those with more than min number of installs
                installs = [i for _, i in self.dependency_map[m].items()]
                for pkg, number in self.dependency_map[m].items():
                    # for now, install only max
                    if number == max(installs):
                        pkgs_to_install.append(pkg)

            else:
                # maybe just try, problem is that apt search is garbage
                # an API to search would be nice.
                pkgs_to_install.append(m)

        success = apt_install(self, pkgs_to_install)
        return success
