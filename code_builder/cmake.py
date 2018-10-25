
import subprocess

from os.path import join, exists, isfile, dirname, basename
from os import listdir, makedirs, mkdir, rename
from shutil import rmtree
from glob import iglob
from re import search
from subprocess import PIPE
from sys import version_info

def isCmakeProject(repo_dir):
    return isfile( join(repo_dir, 'CMakeLists.txt') )

def run(command, cwd, stdout, stderr):

    # Python 3.5+ - subprocess.run
    # older - subprocess.call
    # TODO: capture_output added in 3.7 - verify it works
    if version_info.major >= 3 and version_info.minor >= 5:
        return subprocess.run(command, cwd=cwd, stdout = stdout, stderr = stderr)
    else:
        return subprocess.call(command, cwd=cwd, stdout = stdout, stderr = stderr)

class CMakeProject:

    def __init__(self, repo_dir, output_log, error_log):
        self.repository_path = repo_dir
        self.output_log = output_log
        self.error_log = error_log

    def configure(self, c_compiler, cxx_compiler, force_update = False):
        self.build_dir = self.repository_path + "_build"
        if not exists(self.build_dir):
            mkdir(self.build_dir)
        if len(listdir(self.build_dir)) == 0 or force_update:
            c_compiler_opt = "-DCMAKE_C_COMPILER=" + c_compiler
            cpp_compiler_opt = "-DCMAKE_CXX_COMPILER=" + cxx_compiler
            cmd = ["cmake", self.repository_path, c_compiler_opt, cpp_compiler_opt]
            ret = run(
                    cmd,
                    cwd = self.build_dir,
                    stdout = PIPE,
                    stderr = PIPE
                    )
            if ret.returncode:
                self.error_log.error('Failed CMake configure command: %s' % ' '.join(cmd))
                self.error_log.error(ret.stderr.decode('utf-8'))
            else:
                self.output_log.info('Configure %s to build in %s' % (self.repository_path, self.build_dir))
            return ret.returncode
        return False

    def build(self):
        ret = run(
                ["cmake", "--build", "."],
                cwd = self.build_dir,
                stdout = PIPE,
                stderr = PIPE
                )
        if ret.returncode:
            self.error_log.error(ret.stderr.decode('utf-8'))
        else:
            self.output_log.info('Build in %s' % self.build_dir)
        return ret.returncode

    def generate_bitcodes(self, target_dir):
        if not exists(target_dir):
            mkdir(target_dir)
        for file in iglob('{0}/**/*.bc'.format(self.build_dir), recursive=True):
            # CMake file format: {build_dir}/../CMakeFiles/{dir}.dir/relative_bc_location
            res = search(r'CMakeFiles/.*\.dir', file)
            local_path = file[res.end(0) + 1 : ]
            makedirs( join(target_dir, dirname(local_path)), exist_ok = True)
            rename(file, join(target_dir, local_path) )

    def clean(self):
        build_dir = self.repository_path + "_build"
        rmtree(build_dir)
        os.mkdir(build_dir)

