import os.path, subprocess

from os.path import join, exists
from os import listdir, mkdir
from shutil import rmtree


class CMake:

    def __init__(self, repo_dir):
        self.repository_path = repo_dir


    def build(self, force_update = False):
        build_dir = self.repository_path + "_build"
        # script is outside package directory
        script_path = os.path.abspath(os.path.join(os.path.realpath(__file__), os.pardir))
        script_path = os.path.abspath(os.path.join(script_path, os.pardir))
        print(script_path)
        c_compiler = join(script_path, "clang-wrapper")
        cpp_compiler = join(script_path, "clang++-wrapper")
        if not exists(build_dir):
            mkdir(build_dir)
        elif len(listdir(build_dir)) == 0 or force_update:
            c_compiler_opt = "-DCMAKE_C_COMPILER=" + c_compiler
            cpp_compiler_opt = "-DCMAKE_CXX_COMPILER=" + cpp_compiler
            subprocess.run(["cmake", self.repository_path, c_compiler_opt, cpp_compiler_opt],
                    cwd=build_dir
                    )
        ret = subprocess.run(["cmake", "--build", "."], cwd=build_dir)

    def clean(self):
        build_dir = self.repository_path + "_build"
        rmtree(build_dir)
        os.mkdir(build_dir)

