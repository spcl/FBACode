#!/usr/bin/env python3

import sys
import json
import glob
import os
from os.path import join

from sys import argv
from argparse import ArgumentParser

from code_analyzer.ast_analyzer import typeref_in_file
from code_analyzer.ast_analyzer import callexp_in_file


parser = ArgumentParser(description='Analyze the AST')
parser.add_argument('build_output', type=str,
                    help='output json of the builder')
parser.add_argument('--search', dest='search_str',
                    help='the string or name to look for in the AST')
parser.add_argument('--type', dest="search_type",
                    help="the type of AST node to look for")
parser.add_argument('--from-ast', dest="ast_file", action="store_true",
                    help="parse the ast files from a previous build, not the source files")

parsed_args = parser.parse_args(argv[1:])

# call with 1st arg: json output of build, 2nd arg: class you're looking for
results = {}
print("looking for {}".format(parsed_args.search_str))
with open(parsed_args.build_output) as f:
    project_data = json.load(f)
    if(parsed_args.ast_file):
        for name, data in project_data.items():
            print("analyzing {}".format(name))
            # only take those who downloaded successfully
            results[name] = {"query": parsed_args.search_str, "count": 0}
            if data["build"]["configure"] == "success":
                path = data["ast_files"]["dir"]
                ast_files = glob.glob(join(path, "**/*.ast"), recursive=True)
                for ast in ast_files:
                    result = callexp_in_file(ast, parsed_args.search_str, ast=True)
                    if result:
                        # print("found {} in {}".format(parsed_args.search_str, ast))
                        results[name]["count"] += 1
                    # else:
                        # print("no {} found in {}".format(parsed_args.search_str, ast))

    else:
        for name, data in project_data.items():
            print("analyzing {}".format(name))
            results[name] = {"query": parsed_args.search_str, "count": 0}
            # only take those who downloaded successfully
            if data["build"]["configure"] == "success":
                path = data["source"]["dir"]
                c_files = glob.glob(join(path, "**/*.cc"), recursive=True)
                c_files.extend(glob.glob(join(path, "**/*.cpp"), recursive=True))
                c_files.extend(glob.glob(join(path, "**/*.c"), recursive=True))
                # ast_files = glob.glob(join(path, "**/*.ast"), recursive=True)
                for c_file in c_files:
                    result = callexp_in_file(c_file, parsed_args.search_str)
                    if result:
                        # print("found {} in {}".format(parsed_args.search_str, c_file))
                        results[name]["count"] += 1
                    # else:
                        # print("no {} found in {}".format(parsed_args.search_str, c_file))
print(json.dumps(results, indent=2))
