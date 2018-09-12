
from os.path import abspath, realpath, join
from os import pardir, environ


def get_c_compiler():
    script_path = abspath(join(join(realpath(__file__), pardir), pardir))
    return join(script_path, "clang-wrapper")

def get_cxx_compiler():
    script_path = abspath(join(join(realpath(__file__), pardir), pardir))
    return join(script_path, "clang++-wrapper")

class Environment:

    def overwrite_environment(self):
        self.old_c_compiler = environ.get('CC', None)
        self.old_cxx_compiler = environ.get('CXX', None)
        environ['CC'] = get_c_compiler()
        environ['CXX'] = get_cxx_compiler()

    def reset_environment(self):
        if self.old_c_compiler:
            environ['CC'] = self.old_c_compiler
        else:
            del environ['CC']
        if self.old_cxx_compiler:
            environ['CXX'] = self.old_cxx_compiler
        else:
            del environ['CXX']

