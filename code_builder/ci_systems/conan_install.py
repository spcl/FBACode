from .ci_helper import run
from subprocess import PIPE
from os.path import join

# different paths inside docker
try:
    from build_systems import conan  # type: ignore just for linter
except ModuleNotFoundError:
    from code_builder.build_systems import conan


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
        self.name = name[: name.rfind("@")]
        self.name_and_version = name
        self.version = project["build"]["version"]

    def install(self, builder = None):
        conanfile_path = join(builder.get_remote_package_folder(), "conanfile.py")
        print(f"conanfile_path={conanfile_path}")
        out = run(
            f"conan install --version={self.version} -s compiler=clang -s compiler.cppstd=gnu20 -s compiler.version=18 --build=never {conanfile_path}".split(),
            stderr=PIPE,
        )
        if out.returncode != 0:
            self.error_log.print_error(
                self.idx, "error in conan install: {}".format(out.stderr)
            )
            return False
        self.output_log.print_info(
            self.idx, "installed conan deps {}:\n{}".format(out.args, out.stderr)
        )
        return True

    @staticmethod
    def recognize(repo_dir):
        return conan.Project.recognize(repo_dir)

    @staticmethod
    def get_docker_image(repo_dir, clang_version=9):
        return conan.Project.get_docker_image(repo_dir, clang_version)
