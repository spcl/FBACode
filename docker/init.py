import json
import sys
import os
import importlib
import glob
import subprocess

from time import time
from shutil import move, copyfile
from datetime import datetime

from utils.driver import open_logfiles

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
# print(json_input)

# Updated -> Configure
project = {
    'status': 'configure',
    'build': {
        'dir': external_build_dir,
        'stdout': os.path.basename(loggers.stdout_file),
        'stderr': os.path.basename(loggers.stderr_file)
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
