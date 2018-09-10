
import os.path, json

from git import Repo, GitCommandError

from .cmake import CMake

def import_projects(target_dir, specification):

    if not os.path.exists(target_dir):
        os.mkdir(target_dir)
    for repo, spec in specification.items():

        repository_path = spec['repository']
        project_name = repository_path[repository_path.rfind('/')+1 : repository_path.rfind('.git')]
        try:
            print( "Clone project {0} from {1} to {2}".format(repo, repository_path, os.path.join(target_dir, project_name)))
            cloned_repo = Repo.clone_from(repository_path, os.path.join(target_dir, project_name) )
        except GitCommandError:
            cloned_repo = Repo( os.path.join(target_dir, project_name) )

        # classify repository
        if os.path.isfile( os.path.join(cloned_repo.working_tree_dir, 'CMakeLists.txt') ):
            print('Found Cmake')
            cmake_repo = CMake(cloned_repo.working_tree_dir)
            #cmake_repo.clean()
            cmake_repo.build(force_update = True)


