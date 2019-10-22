
import subprocess

import os
from os.path import abspath, join, exists, isfile, dirname, basename
from os import listdir, makedirs, mkdir, rename
from shutil import rmtree
from glob import iglob
from re import search
from subprocess import PIPE
from sys import version_info
from time import time

from .environment import get_c_compiler, get_cxx_compiler

from . import cmake

def run(command, cwd = None, stdout = None, stderr = None):

    # Python 3.5+ - subprocess.run
    # older - subprocess.call
    # TODO: capture_output added in 3.7 - verify it works
    if version_info.major >= 3 and version_info.minor >= 5:
        return subprocess.run(command, cwd=cwd, stdout = stdout, stderr = stderr)
    else:
        return subprocess.call(command, cwd=cwd, stdout = stdout, stderr = stderr)


build_systems = {
        'CMake' : cmake.project
    }


def recognize_and_build(idx, name, project, target_dir, ctx):

    if project['status'] == 'unrecognized':
        ctx.stats.unrecognized()
    if 'build' in project:
        # update if needed
        return (idx, name, project)
    source_dir = project['source']['dir']
    failure = False
    start = time()
    for build_name, build_system in build_systems.items():
        if build_system.recognize(source_dir):
            build_dir = source_dir + "_build"
            if not exists(build_dir):
                mkdir(build_dir)
            project['build'] = {'system' : build_name, 'dir' : build_dir}
            project['status'] = 'fail'
            builder = build_system(source_dir, build_dir, idx, ctx)
            if not builder.configure(build_dir):
                project['build']['configure'] = 'fail'
                failure = True
                continue
            project['build']['configure'] = 'success'
            if not builder.build():
                project['build']['build'] = 'fail'
                failure = True
                continue
            project['build']['build'] = 'success'
            project['status'] = 'success'
            builder.generate_bitcodes(join(abspath(target_dir), name))

            #build_system(source_dir, out_log, err_log).configure()
    #    if isCmakeProject(source_dir):
    #        cmake_repo = CMakeProject(source_dir, out_log, error_log)
    #        returnval = cmake_repo.configure(
    #                c_compiler = get_c_compiler(),
    #                cxx_compiler = get_cxx_compiler(),
    #                force_update = True
    #                )
    #        if not returnval:
    #            returnval = cmake_repo.build()
    #        if not returnval:
    #            cmake_repo.generate_bitcodes( join(target_dir, project.name()) )
    #        if returnval:
    #            incorrect_projects += 1
    #            spec['status'] = 'fails'
    #        else:
    #            correct_projects += 1
    #            spec['status'] = 'works'
    #    else:
    #        out_log.info('Unrecognized project %s' % source_dir)
    #        unrecognized_projects += 1
    #        spec['status'] = 'unrecognized'
            end = time()
            project['build']['time'] = end - start
            ctx.out_log.print_info(idx, 'Finish processing %s in %f [s]' % (name, end - start))
            return (idx, name, project)
    end = time()
    # nothing matched
    if not failure:
        ctx.out_log.print_info(idx, 'Unrecognized project %s in %s' % (name, source_dir))
    else:
        project['build']['time'] = end - start
    return (idx, name, project)
