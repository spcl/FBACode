
from json import dump
from os import environ, mkdir
from os.path import join, exists
from datetime import datetime

from .cmake import CMakeProject, isCmakeProject
from .project import GitProject
from .environment import Environment, get_c_compiler, get_cxx_compiler
from .logger import create_logger

def export_projects(projects, name, time):
    with open('%s_%s.json' % (name, time), 'w') as outfile:
        dump(projects, outfile)

def import_projects(build_dir, target_dir, specification):

    if not exists(build_dir):
        mkdir(build_dir)
    if not exists(target_dir):
        mkdir(target_dir)

    projects_count = len(specification)
    current_time = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
    output_log = create_logger('output', current_time, projects_count)
    error_log = create_logger('error', current_time, projects_count)

    correct_projects = 0
    incorrect_projects = 0
    unrecognized_projects = 0

    env = Environment()
    env.overwrite_environment()

    for repo, spec in specification.items():

        repository_path = spec['repository']

        if 'status' in spec:
            # works -> check for updates
            # unrecognized -> nothing
            # fails -> check for updates, maybe try again
            if spec['status'] == 'unrecognized':
                unrecognized_projects += 1

        # note; extend here for non-git repos
        project = GitProject(repository_path, output_log)
        project.clone(build_dir)
        # classify repository
        source_dir = project.source_dir()
        if isCmakeProject(source_dir):
            cmake_repo = CMakeProject(source_dir, output_log, error_log)
            returnval = cmake_repo.configure(
                    c_compiler = get_c_compiler(),
                    cxx_compiler = get_cxx_compiler(),
                    force_update = True
                    )
            if not returnval:
                returnval = cmake_repo.build()
            if not returnval:
                cmake_repo.generate_bitcodes( join(target_dir, project.name()) )
            if returnval:
                incorrect_projects += 1
                spec['status'] = 'fails'
            else:
                correct_projects += 1
                spec['status'] = 'works'
        else:
            output_log.info('Unrecognized project %s' % source_dir)
            unrecognized_projects += 1
            spec['status'] = 'unrecognized'

        output_log.next()
        error_log.next()

    env.reset_environment()
    print('Succesfull builds: %d' % correct_projects)
    print('Build errors: %d' % incorrect_projects)
    print('Unrecognized builds: %d' % unrecognized_projects)

    export_projects(specification, 'build_projects', current_time)
