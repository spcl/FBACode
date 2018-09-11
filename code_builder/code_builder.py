
import os.path, json
from os import environ

from git import Repo, GitCommandError

from .cmake import CMake

def import_projects(build_dir, target_dir, specification):

    if not os.path.exists(build_dir):
        os.mkdir(build_dir)
    if not os.path.exists(target_dir):
        os.mkdir(target_dir)

    # override C++ compilers
    if 'CC' in environ:
        old_c_compiler = environ['CC']
    else:
        old_c_compiler = None
    if 'CXX' in environ:
        old_cxx_compiler = environ['CXX']
    else:
        old_cxx_compiler = None
    script_path = os.path.abspath(os.path.join(os.path.realpath(__file__), os.pardir))
    script_path = os.path.abspath(os.path.join(script_path, os.pardir))
    c_compiler = os.path.join(script_path, "clang-wrapper")
    cxx_compiler = os.path.join(script_path, "clang++-wrapper")
    environ['CC'] = c_compiler
    environ['CXX'] = cxx_compiler

    for repo, spec in specification.items():

        repository_path = spec['repository']
        project_name = repository_path[repository_path.rfind('/')+1 : repository_path.rfind('.git')]
        try:
            print( "Clone project {0} from {1} to {2}".format(repo, repository_path, os.path.join(build_dir, project_name)))
            cloned_repo = Repo.clone_from(repository_path, os.path.join(build_dir, project_name) )
        except GitCommandError:
            cloned_repo = Repo( os.path.join(build_dir, project_name) )

        # classify repository
        if isCmakeProject(cloned_repo.working_tree_dir):
            cmake_repo = CMakeProject(cloned_repo.working_tree_dir)
            cmake_repo.build(c_compiler=c_compiler, cxx_compiler = cxx_compiler, force_update = True)
            cmake_repo.generate_bitcodes(os.path.join(target_dir, project_name))

    if old_c_compiler != None:
        environ['CC'] = old_c_compiler
    else:
        del environ['CC']
    if old_cxx_compiler != None:
        environ['CXX'] = old_cxx_compiler
    else:
        del environ['CXX']

