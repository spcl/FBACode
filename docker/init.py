import json
import sys
import os
import importlib
import glob
import subprocess
from subprocess import PIPE

from time import time
from shutil import move, copyfile
from datetime import datetime

from utils.driver import open_logfiles

from sys import version_info


def run(command, cwd=None, stdout=None, stderr=None):

    # Python 3.5+ - subprocess.run
    # older - subprocess.call
    # TODO: capture_output added in 3.7 - verify it works
    if version_info.major >= 3 and version_info.minor >= 5:
        return subprocess.run(command, cwd=cwd, stdout=stdout, stderr=stderr, text=True)
    else:
        return subprocess.call(command, cwd=cwd, stdout=stdout, stderr=stderr, text=True)


class Context:

    def __init__(self, cfg):
        self.cfg = cfg

    def set_loggers(self, out, err):
        self.out_log = out
        self.err_log = err


source_dir = '/home/fba_code/source'
build_dir = '/home/fba_code/build'
bitcodes_dir = '/home/fba_code/bitcodes'
build_system = os.environ['BUILD_SYSTEM']
external_build_dir = os.environ['BUILD_DIR']
external_bitcodes_dir = os.environ['BITCODES_DIR']

json_input = json.load(open(sys.argv[1], 'r'))
print("listdir:")
print(os.listdir("/home/fba_code"))
idx = json_input['idx']
name = json_input['name']
verbose = json_input['verbose']
builder_mod = importlib.import_module('build_systems.{}'.format(build_system))
# builder_mod = imp.load_source(build_system, os.path.join('build_systems', build_system + '.py'))
builder_class = getattr(builder_mod, 'Project')

print("Building {} in here using {}".format(name, build_system))

cfg = {'output': {'verbose': verbose, 'file': '/home/fba_code/'}}
ctx = Context(cfg)
timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
loggers = open_logfiles(cfg, name.replace('/', '_'), timestamp=timestamp)
ctx.set_loggers(loggers.stdout, loggers.stderr)
# save all installed packages, to get the difference later (newly installed deps)
# assusmes we run debian or ubuntu, maybe put into library in the future
out = run(["dpkg", "--get-selections"], stderr=PIPE, stdout=PIPE)
preinstalled_pkgs = out.stdout.splitlines()
preinstalled_pkgs = [i.replace("install", "").strip()
                     for i in preinstalled_pkgs
                     if "deinstall" not in i]

# Updated -> Configure
project = {
    'status': 'configure',
    'build': {
        'dir': external_build_dir,
        'stdout': os.path.basename(loggers.stdout_file),
        'stderr': os.path.basename(loggers.stderr_file),
        'installed': []
    }
}
start = time()
if build_system == "debian":
    builder = builder_class(source_dir, build_dir, idx, ctx, name)
else:
    builder = builder_class(source_dir, build_dir, idx, ctx)
configured_version = builder.configure(build_dir)
if not configured_version:
    project['build']['configure'] = 'fail'
    failure = True
else:
    project['build']['configure'] = 'success'
    if build_system == "debian":
        project['build']['built_version'] = configured_version
    # Configure -> Build
    project['status'] = 'build'
    # project["status"] = "success"
    # project['build']['build'] = 'success'
    if not builder.build():
        project['build']['build'] = 'fail'
        project['status'] = 'fail'
        failure = True
    else:
        project['status'] = 'success'
        project['build']['build'] = 'success'
        project['bitcodes'] = {'dir': external_bitcodes_dir}
        project['ast_files'] = {
            'dir': os.path.join(external_bitcodes_dir, "AST")}
        builder.generate_bitcodes(bitcodes_dir)
        builder.generate_ast(os.path.join(bitcodes_dir, "AST"))
end = time()
project['build']['time'] = end - start
ctx.out_log.print_info(
    idx, 'Finish processing %s in %f [s]' % (name, end - start))

# get installed packages after build
out = run(["dpkg", "--get-selections"], stderr=PIPE, stdout=PIPE)
installed_pkgs = out.stdout.splitlines()
installed_pkgs = [i.replace("install", "").strip()
                  for i in installed_pkgs
                  if "deinstall" not in i]
new_pkgs = list(set(installed_pkgs) - set(preinstalled_pkgs))
project['build']['installed'].append(new_pkgs)
out = {'idx': idx, 'name': name, 'project': project}
# save output JSON
with open("output.json", "w") as f:
    json.dump(out, f, indent=2)

# move logs to build directory
for file in glob.glob('*.log'):
    move(file, build_dir)
copyfile("output.json", os.path.join(build_dir, "output.json"))

# change the user and group to the one of the host, since we are root
host_uid = os.stat(build_dir).st_uid
host_gid = os.stat(build_dir).st_gid

dirs = [build_dir, bitcodes_dir, source_dir]
for d in dirs:
    print("chowning {}...".format(d))
    out = subprocess.run(["chown", "-R", "{}:{}".format(host_uid, host_gid), d])
    if out.returncode != 0:
        print(out)
