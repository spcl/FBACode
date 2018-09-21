
import json

from argparse import ArgumentParser
from sys import argv, stderr
from configparser import ConfigParser

from code_builder.fetcher import fetch_projects
from code_builder.code_builder import build_projects

# https://stackoverflow.com/questions/5574702/how-to-print-to-stderr-in-python
def error_print(*args, **kwargs):
    print(*args, file=stderr, **kwargs)

parser = ArgumentParser(description='Code fetcher and builder')
parser.add_argument('--fetch', dest='fetch', action='store_true',
        help='Fetch new repositories from Github')
parser.add_argument('--fetch-repos-max', dest='fetch_max', type=int, action='store',
        help='Number of repositories to fetch')
parser.add_argument('--repositories', dest='repo_db', action='store',
        help='Load repositories database from file')
parser.add_argument('--build-dir', dest='build_dir', default='build', action='store',
        help='Directory used to build projects')
parser.add_argument('--results-dir', dest='results_dir', default='bitcodes', action='store',
        help='Directory used to store resulting bitcodes')
parser.add_argument('--user-config-file', dest='user_config_file', default='user.cfg', action='store',
        help='User config file')
parser.add_argument('--config-file', dest='config_file', default='default.cfg', action='store',
        help='Application config file')
parser.add_argument('--export-repositories', dest='export_repos', default='', action='store',
        help='Export database of processed repositories as JSON file.')
parsed_args = parser.parse_args(argv[1:])

timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
output_log = create_logger('output', timestamp)
error_log = create_logger('error', timestamp)

cfg = ConfigParser()
cfg.read(parsed_args.user_config_file, parsed_args.config_file)

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
        repositories = fetch_projects(cfg, output_log, error_log, parse_args.max_repos)

build_projects(parsed_args.build_dir, parsed_args.results_dir, repositories, output_log, error_log) 
