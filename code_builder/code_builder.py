
import logging, json
from datetime import datetime
from os import environ, mkdir
from os.path import join, exists

from .cmake import CMakeProject, isCmakeProject
from .project import GitProject
from .environment import Environment, get_c_compiler, get_cxx_compiler

def import_projects(build_dir, target_dir, specification):

    if not exists(build_dir):
        mkdir(build_dir)
    if not exists(target_dir):
        mkdir(target_dir)

    current_time = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
    handler = logging.FileHandler('code_builder_{0}.log'.format(current_time))
    #logging.addHandler(handler)

    env = Environment()
    env.overwrite_environment()

    for repo, spec in specification.items():

        repository_path = spec['repository']
        # note; extend here for non-git repos
        project = GitProject(repository_path)
        project.clone(build_dir)
        #print( "Clone project {0} from {1} to {2}".format(repo, repository_path, os.path.join(build_dir, project_name)))

        # classify repository
        source_dir = project.source_dir()
        if isCmakeProject(source_dir):
            cmake_repo = CMakeProject(source_dir)
            cmake_repo.build(
                    c_compiler = get_c_compiler(),
                    cxx_compiler = get_cxx_compiler(),
                    force_update = True
                    )
            cmake_repo.generate_bitcodes( join(target_dir, project.name()) )

    env.reset_environment()

