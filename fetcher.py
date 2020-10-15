#!/usr/bin/env python3

import json

from datetime import datetime
from os import path
from sys import argv
from argparse import ArgumentParser

from code_builder.fetcher import fetch_projects
from code_builder.utils.driver import open_logfiles, open_config

def export_projects(projects, name):
    with open(name, mode='w') as outfile:
        json.dump(projects, outfile, indent = 2)

parser = ArgumentParser(description='Code fetcher and builder')
parser.add_argument('--fetch', dest='fetch', action='store_true',
        help='Fetch new repositories')
parser.add_argument('--fetch-repos-max', dest='fetch_max', type=int, action='store',
        help='Number of repositories to fetch')
parser.add_argument('--repositories', dest='repo_db', action='store',
        help='Load repositories database from file for update')
parser.add_argument('--user-config-file', dest='user_config_file',
        default='user.cfg', action='store', help='User config file')
parser.add_argument('--config-file', dest='config_file', default='fetch.cfg', action='store',
        help='Application config file')
parser.add_argument('--export-repositories', dest='export_repos', action='store',
        help='Export database of processed repositories as JSON file')
parser.add_argument('--log-to-file', dest='out_to_file', action='store',
        help='Store output and error logs to a file')
parser.add_argument('--verbose', dest='verbose', action='store_true',
        help='Verbose output.')

parsed_args = parser.parse_args(argv[1:])
cfg = open_config(parsed_args, path.dirname(path.realpath(__file__)))
cfg['output'] = {'verbose' : parsed_args.verbose}
if parsed_args.out_to_file:
    cfg['output']['file'] = parsed_args.out_to_file
cfg['output']['time'] = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
logfiles = open_logfiles(cfg, "fetcher")

# fetch new data, possibley updating
if parsed_args.repo_db is not None:
    with open(parsed_args.repo_db) as repo_db:
        repositories = json.load(repo_db)
    update_projects(repositories, cfg, logfiles.stdout, logfiles.stderr)
else:
    repositories = fetch_projects(cfg, logfiles.stdout, logfiles.stderr,
            parsed_args.fetch_max)

if parsed_args.export_repos is not None:
    export_projects(repositories, parsed_args.export_repos)
