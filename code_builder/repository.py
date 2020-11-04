from os.path import join, exists
from git import Repo, GitCommandError


class GitProject:
    def __init__(self, repository_path, branch, cfg, output_log):
        self.cfg = cfg
        self.branch = branch
        self.output_log = output_log
        last_slash = repository_path.rfind("/") + 1
        project_name = repository_path[last_slash: repository_path.rfind(".git")]
        # repository format is: git@server:user/project.git
        # or https://server/user/project.git
        user_start = repository_path.rfind("/", 0, last_slash - 1)
        if user_start == -1:
            user_start = repository_path.rfind(":", 0, last_slash - 1)
        user_name = repository_path[user_start + 1: last_slash - 1]
        self.project_name = "{0}_{1}".format(user_name, project_name)
        self.repository_path = repository_path

    def info(self, idx, msg):
        if idx:
            self.output_log.print_info(idx, msg)
        else:
            self.output_log.info(msg)

    def clone(self, build_dir, idx=0):
        repo_location = join(build_dir, self.project_name)
        self.info(
            idx,
            "Clone %s repository from %s to %s"
            % (self.project_name, self.repository_path, repo_location),
        )
        if exists(repo_location):
            self.cloned_repo = Repo(repo_location)
        else:
            try:
                self.cloned_repo = Repo.clone_from(
                    self.repository_path, repo_location, recursive=True
                )
                submodules_count = len(self.cloned_repo.submodules)
                if submodules_count:
                    self.info(
                        idx,
                        "Initialized %d submodules in %s"
                        % (submodules_count, repo_location),
                    )
                self.cloned_repo.git.checkout(self.branch)
            # TODO: why do I need this? when can it fail?
            except GitCommandError:
                self.cloned_repo = Repo(repo_location)
        return repo_location

    def source_dir(self):
        return self.cloned_repo.working_tree_dir

    def name(self):
        return self.project_name
