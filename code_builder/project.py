
from os.path import join, exists
from git import Repo, GitCommandError

class GitProject:

    def __init__(self, repository_path):
        last_slash = repository_path.rfind('/') + 1
        project_name = repository_path[last_slash:repository_path.rfind('.git')]
        prev_slash = repository_path.rfind('/', last_slash - 1, 0)
        user_name = repository_path[prev_slash:last_slash]
        self.project_name = '{0}_{1}'.format(user_name, project_name)
        self.repository_path = repository_path

    def clone(self, build_dir):
        repo_location = join(build_dir, self.project_name)
        if exists(repo_location):
            self.cloned_repo = Repo(repo_location)
        else:
            try:
                self.cloned_repo = Repo.clone_from(self.repository_path, repo_location)
            except GitCommandError:
                self.cloned_repo = Repo(repo_location)

    def source_dir(self):
        return self.cloned_repo.working_tree_dir

    def name(self):
        return self.project_name



