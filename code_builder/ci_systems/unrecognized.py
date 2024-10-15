# what to do when there is no recognized ci system?
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

    def install(self, builder = None):
        # let's try to install using previous dependencies (if there are any)
        pass

    @staticmethod
    def get_docker_image(repo_dir, clang_version=9):
        return False
