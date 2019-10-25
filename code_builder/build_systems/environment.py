
from os.path import abspath, realpath, join, dirname, basename
from os import pardir, environ


def get_wrappers_dir():
    return abspath(join(dirname(realpath(__file__)), pardir, 'wrappers'))

def get_c_compiler():
    return join(get_wrappers_dir(), "clang")

def get_cxx_compiler():
    return join(get_wrappers_dir(), "clang++")

# Three ways of overwriting C/CXX compiler
# 1) Build-system specific e.g. CMAKE_C_COMPILER
# 2) Overwrite CC/CXX environment variable. Option for submodules where build setting is not passed.
# 3) Redefine default clang/clang++. Option for projects where compiler is hardcoded.
# The last option could be done with defining shell function with the same name.
# This is not easy from Python, though.
# Instead, PATH is changed to point to our wrappers directory.

class Environment:

    # generic non-bash version?
    def overwrite_environment(self):
        self.old_c_compiler = environ.get('CC', None)
        self.old_cxx_compiler = environ.get('CXX', None)

        c_compiler = get_c_compiler()
        environ['CC'] = c_compiler
        cxx_compiler = get_cxx_compiler()
        environ['CXX'] = cxx_compiler
        self.old_path = environ.get('PATH', None)
        environ['PATH'] = get_wrappers_dir() + ':' + (self.old_path if self.old_path is not None else '')

    def reset_environment(self):
        if self.old_c_compiler:
            environ['CC'] = self.old_c_compiler
        else:
            del environ['CC']

        if self.old_cxx_compiler:
            environ['CXX'] = self.old_cxx_compiler
        else:
            del environ['CXX']

        if self.old_path:
            environ['PATH'] = self.old_path
        else:
            del environ['PATH']

