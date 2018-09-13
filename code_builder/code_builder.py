
import json
from os import environ, mkdir
from os.path import join, exists

from .cmake import CMakeProject, isCmakeProject
from .project import GitProject
from .environment import Environment, get_c_compiler, get_cxx_compiler
from .logger import create_logger

def import_projects(build_dir, target_dir, specification):

    if not exists(build_dir):
        mkdir(build_dir)
    if not exists(target_dir):
        mkdir(target_dir)

    projects_count = len(specification)
    output_log = create_logger('output', projects_count)
    error_log = create_logger('error', projects_count)

    env = Environment()
    env.overwrite_environment()

    for repo, spec in specification.items():

        repository_path = spec['repository']
        # note; extend here for non-git repos
        project = GitProject(repository_path, output_log)
        project.clone(build_dir)
        # classify repository
        source_dir = project.source_dir()
        if isCmakeProject(source_dir):
            cmake_repo = CMakeProject(source_dir, output_log, error_log)
            cmake_repo.configure(
                    c_compiler = get_c_compiler(),
                    cxx_compiler = get_cxx_compiler(),
                    force_update = True
                    )
            cmake_repo.build()
            cmake_repo.generate_bitcodes( join(target_dir, project.name()) )

        output_log.next()

    env.reset_environment()

