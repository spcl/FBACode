
import json

from argparse import ArgumentParser
from sys import argv, stdout, stderr
from configparser import ConfigParser
from datetime import datetime
from os import path

from code_builder import logger
from code_builder.fetcher import fetch_projects
from code_builder.code_builder import build_projects
from code_builder.driver import open_config, open_logfiles

# https://stackoverflow.com/questions/5574702/how-to-print-to-stderr-in-python
def error_print(*args, **kwargs):
    print(*args, file=stderr, **kwargs)

def export_projects(projects, name):
    with open(name, mode='w') as outfile:
        json.dump(projects, outfile, indent = 2)

parser = ArgumentParser(description='Code builder')
parser.add_argument('repositories_db', type=str, help='Load repositories database from file')
parser.add_argument('--build-force-update', dest='build_force_update', action='store_true',
        help='Enforce update of configuration for repositories in database')
parser.add_argument('--source-dir', dest='source_dir', default='source', action='store',
        help='Directory used to store source codes')
parser.add_argument('--build-dir', dest='build_dir', default='build', action='store',
        help='Directory used to build projects')
parser.add_argument('--results-dir', dest='results_dir', default='bitcodes', action='store',
        help='Directory used to store resulting bitcodes')
parser.add_argument('--user-config-file', dest='user_config_file', default='user.cfg', action='store',
        help='User config file')
parser.add_argument('--config-file', dest='config_file', default='build.cfg', action='store',
        help='Application config file')
parser.add_argument('--export-repositories', dest='export_repos', action='store',
        help='Export updated database of processed repositories as JSON file')
parser.add_argument('--log-to-file', dest='out_to_file', action='store',
        help='Store output and error logs to a file')
parser.add_argument('--verbose', dest='verbose', action='store_true',
        help='Verbose output.')
parser.add_argument('--output', dest='output', default='', action='store',
        help='Output.')

parsed_args = parser.parse_args(argv[1:])
cfg = open_config(parsed_args, path.dirname(path.realpath(__file__)))
cfg['output'] = {'verbose' : parsed_args.verbose}
if parsed_args.out_to_file:
    cfg['output']['file'] = parsed_args.out_to_file
cfg['output']['time'] = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')

with open(parsed_args.repositories_db) as repo_db:
    repositories = json.load(repo_db)

repositories = build_projects(  source_dir = parsed_args.source_dir, 
                                build_dir = parsed_args.build_dir,
                                target_dir = parsed_args.results_dir,
                                repositories_db = repositories,
                                force_update = parsed_args.build_force_update,
                                cfg = cfg,
                                output = parsed_args.output)

if parsed_args.export_repos is not None:
    export_projects(repositories, parsed_args.export_repos)
