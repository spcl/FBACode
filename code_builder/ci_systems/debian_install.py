from .ci_helper import run
from subprocess import PIPE

# different paths inside docker
try:
    from build_systems import debian  # type: ignore just for linter
except ModuleNotFoundError:
    from code_builder.build_systems import debian


class Context:
    def __init__(self, cfg):
        self.cfg = cfg

    def set_loggers(self, out, err):
        self.out_log = out
        self.err_log = err


class CiSystem:
    def __init__(
        self, repo_dir, build_dir, idx, ctx, name, project, use_build_dir=False
    ):
        self.repository_path = repo_dir
        self.build_dir = build_dir
        self.idx = idx
        self.ctx = ctx
        self.output_log = ctx.out_log
        self.error_log = ctx.err_log
        self.project = project
        self.name = name

    def install(self, builder = None):
        out = run(
            ["apt-get", "update", "-y"],
            cwd=self.repository_path,
            stderr=PIPE,
        )
        if out.returncode != 0:
            self.error_log.print_error(
                self.idx, "error in apt uppdate: {}".format(out.stderr)
            )
            return False
        out = run(
            ["apt-get", "build-dep", "-y", self.name],
            cwd=self.repository_path,
            stderr=PIPE,
        )
        if out.returncode != 0:
            self.error_log.print_error(
                self.idx, "error in apt build-dep: {}".format(out.stderr)
            )
            return False
        self.output_log.print_info(
            self.idx, "installed debian deps {}:\n{}".format(out.args, out.stderr)
        )
        return True

    @staticmethod
    def recognize(repo_dir):
        return debian.Project.recognize(repo_dir)

    @staticmethod
    def get_docker_image(repo_dir, clang_version=9):
        return debian.Project.get_docker_image(repo_dir, clang_version)
