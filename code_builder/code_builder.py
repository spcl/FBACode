
from os import environ, mkdir
from os.path import join, exists

from .cmake import CMakeProject, isCmakeProject
from .project import GitProject
from .environment import Environment, get_c_compiler, get_cxx_compiler

def build_projects(build_dir, target_dir, repositories_db, force_update, out_log, error_log):

    if not exists(build_dir):
        mkdir(build_dir)
    if not exists(target_dir):
        mkdir(target_dir)

    projects_count = len(repositories_db)

    correct_projects = 0
    incorrect_projects = 0
    unrecognized_projects = 0
    out_log.set_counter(projects_count)
    error_log.set_counter(projects_count)

    env = Environment()
    env.overwrite_environment()

    for repo, spec in repositories_db.items():

        repository_path = spec['codebase_data']['git_url']

        if 'status' in spec:
            # works -> check for updates
            # unrecognized -> nothing
            # fails -> check for updates, maybe try again
            if spec['status'] == 'unrecognized':
                unrecognized_projects += 1

        # note; extend here for non-git repos
        project = GitProject(repository_path, out_log)
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
    print('Failed builds: %d' % incorrect_projects)
    print('Unrecognized builds: %d' % unrecognized_projects)

