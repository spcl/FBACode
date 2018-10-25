
import json

from argparse import ArgumentParser
from sys import argv, stderr
from configparser import ConfigParser
from datetime import datetime
from os import path

from code_builder.fetcher import fetch_projects
from code_builder.code_builder import build_projects
from code_builder.logger import create_logger

# https://stackoverflow.com/questions/5574702/how-to-print-to-stderr-in-python
def error_print(*args, **kwargs):
    print(*args, file=stderr, **kwargs)

def export_projects(projects, name):
    with open(name, mode='w') as outfile:
        json.dump(projects, outfile, indent = 2)

parser = ArgumentParser(description='Code fetcher and builder')
parser.add_argument('--fetch', dest='fetch', action='store_true',
        help='Fetch new repositories from Github')
parser.add_argument('--fetch-repos-max', dest='fetch_max', type=int, action='store',
        help='Number of repositories to fetch')
parser.add_argument('--repositories', dest='repo_db', action='store',
        help='Load repositories database from file')
parser.add_argument('--build', dest='build', action='store_true',
        help='Build repositories in database')
parser.add_argument('--build-force-update', dest='build_force_update', action='store_true',
        help='Enforce update of configuration for repositories in database')
parser.add_argument('--build-dir', dest='build_dir', default='build', action='store',
        help='Directory used to build projects')
parser.add_argument('--results-dir', dest='results_dir', default='bitcodes', action='store',
        help='Directory used to store resulting bitcodes')
parser.add_argument('--user-config-file', dest='user_config_file', default='user.cfg', action='store',
        help='User config file')
parser.add_argument('--config-file', dest='config_file', default='default.cfg', action='store',
        help='Application config file')
parser.add_argument('--export-repositories', dest='export_repos', action='store',
        help='Export database of processed repositories as JSON file')
parsed_args = parser.parse_args(argv[1:])

timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
output_log = create_logger('output', timestamp)
error_log = create_logger('error', timestamp)

cfg = ConfigParser()
default_cfg = parsed_args.config_file
# if file not provided, use the one located in top project directory
if not path.exists(default_cfg):
    default_cfg = path.join( path.dirname(path.realpath(__file__)), 'default.cfg')
print(default_cfg)
cfg.read([parsed_args.user_config_file, default_cfg])

# fetch new data, possibley updating
if parsed_args.repo_db is not None:
    with open(parsed_args.repo_db) as repo_db:
        repositories = json.load(repo_db)
    if parsed_args.fetch:
        # TODO: update database
        pass
else:
    if not parsed_args.fetch:
        error_print('No repository database supplied (--repositories) '
                'and --fetch option not selected - nothing to do!')
        parser.print_help()
        exit()
    else:
        repositories = fetch_projects(cfg, output_log, error_log, parsed_args.fetch_max)
if parsed_args.build:
    build_projects( build_dir = parsed_args.build_dir,
                    target_dir = parsed_args.results_dir,
                    repositories_db = repositories,
                    force_update = parsed_args.build_force_update,
                    out_log = output_log,
                    error_log = error_log) 

if parsed_args.export_repos is not None:
    export_projects(repositories, parsed_args.export_repos)
