import sys
import json
import glob
import os
import tempfile

from datetime import datetime
from os import path
from os.path import join
from sys import argv, stdout, stderr
from argparse import ArgumentParser
from fabric import Connection
from configparser import ConfigParser
from collections import OrderedDict

from code_analyzer.ast_analyzer import analyze_projects

# https://stackoverflow.com/questions/5574702/how-to-print-to-stderr-in-python
def error_print(*args, **kwargs):
    print(*args, file=stderr, **kwargs)

def info_print(*args, **kwargs):
    print(*args, file=stdout, **kwargs)

def export_projects(projects, name):
    with open(name, mode='w') as outfile:
        json.dump(projects, outfile, indent = 2)

# change default behavior of ConfigParser
# instead of overwriting sections with same key,
# accumulate the results
class multidict(OrderedDict):
    def __setitem__(self, key, val):
        if isinstance(val, dict):
            if key in self:
                self.update(key, {**self.get(key), **val})
                return
        OrderedDict.__setitem__(self, key, val)

def open_config(parsed_args, exec_dir):
    cfg = ConfigParser(dict_type = multidict, strict = False)
    default_cfg = parsed_args.config_file
    cfg_file = path.join(exec_dir, default_cfg)
    
    # Main config file
    if path.exists(cfg_file):
        info_print(f"Opening config file {default_cfg}")
    else:
        error_print(f"Config file {default_cfg} not found! Abort.")
        sys.exit(1)

    cfg.read([cfg_file])
    return cfg

def main():
    parser = ArgumentParser(description='Analyze the AST')
    parser.add_argument('collection_path', type=str,
                        help='folder where the AST archives are stored')
    parser.add_argument('--config-file', dest='config_file', default='analyze.cfg', action='store', help='Application config file')
    parser.add_argument('--ast-archive', dest='ast_archive', help='Folder where the AST archives are stored/downloaded to', default="ast_archive")
    parser.add_argument('--results-dir', dest='results_dir', help="Folder where the cxx-langstat output is going to be saved", default='analyze')

    parsed_args = parser.parse_args(argv[1:])
    path_to_collection = join('/home/cdragancea/runs_archived/', parsed_args.collection_path)
    # cfg = open_config(parsed_args, path.dirname(path.realpath(__file__)))
    # cfg['output'] = {'verbose' : parsed_args.verbose}
    # if parsed_args.out_to_file:
    #     cfg['output']['file'] = parsed_args.out_to_file
    # cfg['output']['time'] = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
    # if parsed_args.n_jobs:
    #     cfg["build"]["jobs"] = parsed_args.n_jobs

    cfg = open_config(parsed_args, path.dirname(path.realpath(__file__)))
    if parsed_args.ast_archive:
        cfg['analyze']['ast_archive'] = parsed_args.ast_archive

    try:
        # TODO: for now, the analyzer looks for ASTs on a remote storage server. Make it work for local as well
        USER = cfg['remote']['user']
        HOST = cfg['remote']['host']

        # Create a temporary file using tempfile.mkstemp
        _, temp_file_path = tempfile.mkstemp()
        with Connection(host = HOST, user = USER) as connection:
            # print(connection.run("uname -s").stdout.strip())
            connection.get(remote = join(cfg['remote']['preceding_path_to_collection'], 'build_summary.json'), local = temp_file_path)
        with open(temp_file_path) as tmp_file:
            projects_info = json.load(tmp_file)
        
        os.unlink(temp_file_path)
    except Exception as e:
        error_print(f'Failed to read build_summary: {e}')
        sys.exit(1)


    # return
    result = analyze_projects(path_to_collection = path_to_collection,
                                ast_archive_root = parsed_args.ast_archive,
                                results_dir_root = parsed_args.results_dir,
                                projects_info = projects_info,
                                cfg = cfg)

    # if parsed_args.export_repos is not None:
    #     export_projects(repositories, parsed_args.export_repos)

if __name__ == "__main__":
    main()