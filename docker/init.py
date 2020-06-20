import json
import sys
import os
import importlib
import glob

from time import time
from shutil import move
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
idx = json_input['idx']
name = json_input['name']
verbose = json_input['verbose']
builder_mod = importlib.import_module('build_systems.{}'.format(build_system))
#builder_mod = imp.load_source(build_system, os.path.join('build_systems', build_system + '.py'))
builder_class = getattr(builder_mod, 'project')

cfg = { 'output' : { 'verbose' : verbose, 'file' : '/home/fba_code/' }}
ctx = Context(cfg)
timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
ctx.set_loggers(*open_logfiles(cfg, name.replace('/', '_'), timestamp=timestamp))


# Updated -> Configure
project = { 'status': 'configure', 'build' : {'dir' : external_build_dir}}
start = time()
builder = builder_class(source_dir, build_dir, idx, ctx)
if not builder.configure(build_dir):
    project['build']['configure'] = 'fail'
    failure = True
else:
    project['build']['configure'] = 'success'
    # Configure -> Build
    project['status'] = 'build'
    if not builder.build():
        project['build']['build'] = 'fail'
        project['status'] = 'fail'
        failure = True
    else:
        project['status'] = 'success'
        project['build']['build'] = 'success'
        project['bitcodes'] = {'dir' : external_bitcodes_dir}
        builder.generate_bitcodes(bitcodes_dir)
end = time()
project['build']['time'] = end - start
ctx.out_log.print_info(idx, 'Finish processing %s in %f [s]' % (name, end - start))

out = { 'idx' : idx, 'name' : name, 'project' : project }
# save output JSON
print(json.dumps(out, indent=2), file=open('output.json', 'w'))
# move logs to build directory
for file in glob.glob('*.log'):
    move(file, 'build')

