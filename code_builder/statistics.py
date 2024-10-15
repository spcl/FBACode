import json
import re
import copy
import fuzzywuzzy
import shutil
import os.path

from json.decoder import JSONDecodeError
from os.path import join
from datetime import datetime
from collections import OrderedDict
from fuzzywuzzy import process, fuzz
from time import time
from . import dep_finder


class Statistics:

    path_regex = r"(?:\.\.|\.)?(?:[/]*/)+\S*\.\S+(?:\sline\s\d+:?)?(?=\s|$|\.)"

    def __init__(self, project_count):
        self.correct_projects = 0
        self.incorrect_projects = 0
        self.unrecognized_projects = []
        self.clone_time = 0
        self.build_time = 0
        if not os.path.exists("code_builder/errortypes.json"):
            with open("code_builder/errortypes.json", "w") as f:
                f.write("{}")
        try:
            with open("code_builder/errortypes.json", "r") as f:
                self.errors_stdout = json.load(f)
        except FileNotFoundError:
            self.errors_stdout = {}
        except JSONDecodeError:
            print("error decoding errortypes.json, maybe corrupted?")
            self.errors_stdout = {}
            shutil.copy(
                "code_builder/errortypes.json",
                "code_builder/errortypes.json_backup"
                + datetime.now().strftime("%Y_%m_%d_%H_%M_%S"),
            )
        for err in self.errors_stdout:
            if "regex" not in self.errors_stdout[err]:
                self.errors_stdout[err]["regex"] = re.escape(err)
            if "amount" not in self.errors_stdout[err]:
                self.errors_stdout[err]["amount"] = 0
        self.save_errors_json()
        self.errortypes = {"unrecognized": {"amount": 0, "projects": []}}
        # save the failed projects, so we can retry them later
        self.rebuild_projects = {}
        self.unrecognized_errs = []
        self.new_errs = 0
        self.project_count = project_count
        self.dep_finder = dep_finder.DepFinder()
        self.dependencies = {}
        self.build_systems = {}
        self.ci_systems = {}
        self.all_projects = {}
        self.dep_mapping = {}
        if not os.path.exists("code_builder/dep_mapping.json"):
            with open("code_builder/dep_mapping.json", "w") as f:
                f.write("{}")
        try:
            with open("code_builder/dep_mapping.json", "r") as f:
                self.persistent_dep_mapping = json.load(f)
        except FileNotFoundError:
            self.persistent_dep_mapping = {}
        except JSONDecodeError:
            print("error decoding dep_mapping.json, maybe corrupted?")
            self.errors_stdout = {}
            shutil.copy(
                "code_builder/errortypes.json",
                "code_builder/errortypes.json_backup"
                + datetime.now().strftime("%Y_%m_%d_%H_%M_%S"),
            )

        self.stat_time = 0

    def print_stats(self, out):
        print("Repository clone time: %f seconds" % self.clone_time, file=out)
        print("Repository build time: %f seconds" % self.build_time, file=out)
        print("Analyzing time: {} seconds".format(self.stat_time), file=out)
        print("Succesfull builds: %d" % self.correct_projects, file=out)
        print("Failed builds: %d" % self.incorrect_projects, file=out)
        print(
            "Unrecognized builds: {}".format(len(self.unrecognized_projects)), file=out
        )
        print("Build systems:", file=out)
        for name, count in self.build_systems.items():
            print("  {}: {}".format(name, count), file=out)
        print("Continuous integration systems:", file=out)
        for name, count in self.ci_systems.items():
            print("  {}: {}".format(name, count), file=out)
        for p in self.unrecognized_projects:
            print("  {}".format(p), file=out)
        print("newly discovered errors: {}".format(self.new_errs), file=out)
        print("Types of build errors:", file=out)
        self.errortypes = OrderedDict(
            sorted(
                self.errortypes.items(),
                key=lambda i: i[1].get("amount", 0),
                reverse=True,
            )
        )
        for err, data in self.errortypes.items():
            print("{}: {}".format(err, data["amount"]), file=out)
        print("failed packages:", file=out)
        for name, p in self.all_projects.items():
            if p["status"] == "unrecognized":
                print("\n- {}: build system unrecognized".format(name), file=out)
            elif p["status"] != "success":
                print("\n- {}:".format(name), file=out)
                for e in p.get("build", {}).get("errortypes", []):
                    print("    {}".format(e), file=out)

        # print("unrecognized errors:")
        # for err in self.unrecognized_errs:
        #     print(err, file=out)
        # print("\ndetected missing dependencies:", file=out)
        # self.dependencies = OrderedDict(
        #     sorted(
        #         self.dependencies.items(),
        #         key=lambda i: i[1].get("count", 0),
        #         reverse=True,
        #     )
        # )
        # print(json.dumps(self.dependencies, indent=2), file=out)
        # print("\nDependency mapping:", file=out)
        # print(json.dumps(self.dep_mapping, indent=2), file=out)

    def update(self, project, name, final_update=True):
        # update build_systems statistic
        start = time()
        self.all_projects[name] = project
        project["statistics"] = {}
        build_system = project.get("build_system", "unrecognized")
        if build_system not in self.build_systems:
            self.build_systems[build_system] = {"success": 0, "fail": 0}
        # self.build_systems[build_system] = self.build_systems.get(build_system, 0) + 1
        ci_systems = project.get("ci_systems", [])
        if ci_systems == []:
            ci_systems = ["None"]
        for i in ci_systems:
            if i not in self.ci_systems:
                self.ci_systems[i] = {"success": 0, "fail": 0}
        if "build" in project and "clone_time" in project["build"]:
            project["source"]["time"] = project["build"]["clone_time"]
        if "source" in project:
            self.clone_time += project["source"].get("time")
        if "build" in project:
            self.build_time += project["build"]["time"]
        if project.get("double_build_done") and "build" in project and final_update:
            self.map_dependencies(
                project["no_install_build"].get("missing_dependencies", []),
                project["build"].get("installed", []),
                name,
            )
        if project["status"] == "unrecognized":
            self.build_systems[build_system]["fail"] += 1
            for i in ci_systems:
                self.ci_systems[i]["fail"] += 1
            self.add_unrecognized_project(name)
            self.add_rebuild_data(project, name)
        elif project["status"] == "success":
            self.build_systems[build_system]["success"] += 1
            for i in ci_systems:
                self.ci_systems[i]["success"] += 1
            self.add_correct_project()
        elif project["status"] == "crash" or project["status"] == "docker_crash":
            self.build_systems[build_system]["fail"] += 1
            for i in ci_systems:
                self.ci_systems[i]["fail"] += 1
            self.add_incorrect_project()
            self.add_rebuild_data(project, name)
            err = "docker_crash"
            if err not in self.errors_stdout:
                self.errors_stdout[err] = {
                    "name": err,
                    "projects": [name],
                    "origin": "docker",
                    # match to nothing, since crashes are not visible in logs
                    "regex": None,
                    "amount": 1,
                }
            elif name not in self.errors_stdout[err]["projects"]:
                self.errors_stdout[err]["projects"].append(name)
                self.errors_stdout[err]["amount"] += 1
            if err in self.errortypes:
                self.errortypes[err]["amount"] += 1
                if name not in self.errortypes[err]["projects"]:
                    self.errortypes[err]["projects"].append(name)
            else:
                self.errortypes[err] = copy.deepcopy(self.errors_stdout[err])
                self.errortypes[err]["amount"] = 1
                self.errortypes[err]["projects"] = [name]

        else:
            if "build" in project:
                # we pass the error log through all the stages,
                # always removing the found errors from the string
                project["build"]["errortypes"] = []
                # print("\nstarting error analysis for {}".format(name))
                err_log = join(project["build"]["dir"], project["build"]["stderr"])
                with open(err_log, "r") as log:
                    text = log.read()
                text = self.find_confident_errors(project, name, text)
                text = self.match_error_with_regex(project, name, text)
                text = self.match_error_fuzzy(project, name, text)
                text = self.find_new_errors(project, name, text)

                # found no errs yet, check docker log (stdout of build)
                # this file can be big, so try to avoid
                if not project["build"]["errortypes"]:
                    docker_log = join(
                        project["build"]["dir"], project["build"]["docker_log"]
                    )
                    with open(docker_log, "r") as log:
                        text = log.read()
                    text = self.find_confident_errors(project, name, text)
                    text = self.match_error_with_regex(project, name, text)
                    text = self.match_error_fuzzy(project, name, text)
                    text = self.find_new_errors(project, name, text)
                    if not project["build"]["errortypes"]:
                        self.errortypes["unrecognized"]["amount"] += 1
                        if name not in self.errortypes["unrecognized"]["projects"]:
                            self.errortypes["unrecognized"]["projects"].append(name)
                        project["build"]["errortypes"] = ["unrecognized"]
            self.add_incorrect_project()
            self.build_systems[build_system]["fail"] += 1
            for i in ci_systems:
                self.ci_systems[i]["fail"] += 1
            self.add_rebuild_data(project, name)
        end = time()
        project["statistics"]["error_analysis"] = end - start
        self.stat_time += end - start
        if (
            "build" in project
            and project["status"] != "success"
            and project["status"] != "crash"
        ):
            start = time()
            self.find_deps(project, name)
            end = time()
            project["statistics"]["dep_finder"] = end - start
            self.stat_time += end - start

    def add_unrecognized_project(self, name):
        self.unrecognized_projects.append(name)

    def add_correct_project(self):
        self.correct_projects += 1

    def add_incorrect_project(self):
        self.incorrect_projects += 1

    def add_errors(self, project, name, errors):
        new_errors = []
        for e in errors:
            if [i for i in project["build"]["errortypes"] if e in i] == []:
                new_errors.append(e)
        # new_errors = [e for e in errors if e not in project["build"]["errortypes"]]
        for err in new_errors:
            if err in self.errortypes:
                self.errortypes[err]["amount"] += 1
                if name not in self.errortypes[err]["projects"]:
                    self.errortypes[err]["projects"].append(name)
            else:
                self.errortypes[err] = copy.deepcopy(self.errors_stdout[err])
                self.errortypes[err]["amount"] = 1
                self.errortypes[err]["projects"] = [name]

            if name not in self.errors_stdout[err]["projects"]:
                self.errors_stdout[err]["projects"].append(name)
            if "amount" in self.errors_stdout[err]:
                self.errors_stdout[err]["amount"] += 1
            else:
                self.errors_stdout[err]["amount"] = 1
        project["build"]["errortypes"].extend(new_errors)

    def match_error_with_regex(self, project, name, log):
        log_lines = log.splitlines()
        errors_matches = [
            (err, re.search(self.errors_stdout[err]["regex"], log))
            for err in self.errors_stdout
            if self.errors_stdout[err]["regex"] is not None
            and re.search(self.errors_stdout[err]["regex"], log) is not None
        ]
        errors = []
        for err, match in errors_matches:
            errlines = [i for i in log_lines if match[0] in i]
            for e in errlines:
                log = log.replace(e, "")
            errors.append(err)
        # we found the following errors
        self.add_errors(project, name, errors)
        return log

    def match_error_fuzzy(self, project, name, log):
        orig_lines = [l for l in log.splitlines() if len(l) < 1000]
        lines = [re.sub(self.path_regex, "PATH/FILE.TXT", l) for l in orig_lines]
        errors = []
        for i, l in enumerate(lines):
            # check if string has any processable character, otherwise continue
            processed = fuzzywuzzy.utils.full_process(l)  # type: ignore
            if not processed:
                continue
            matches = process.extract(
                processed, self.errors_stdout.keys(), limit=5, scorer=fuzz.ratio
            )
            # what threshold??
            new_errs = [m[0] for m in matches if m[1] >= 90]
            if new_errs:
                log.replace(orig_lines[i], "")
                pass
                # print("matched \n{}\nto\n{} using fuzzy".format(l, new_errs), sep='\n')
            errors.extend([m[0] for m in matches if m[1] >= 90])
        # remove dups
        self.add_errors(project, name, list(set(errors)))
        return log

    # we search for these errors anyway, since they are pretty safely "good"
    def find_confident_errors(self, project, name, log):
        # try to find the normal clang error line (match to filename.xx:line:col: error: )
        errlines = re.findall(
            r"^.*\..*\:\d+\:\d+\:.*error\:.*$", log, flags=re.MULTILINE
        )
        # if we have nicely formatted errs from clang, we just add to known errs
        if errlines:
            for err in errlines:
                # remove filename and lines etc.
                log = log.replace(err, "")
                err = re.sub(self.path_regex, "PATH/FILE.EXT", err)
                err = re.search(r"error\:.*$", err).group(0)
                if err not in self.errors_stdout:
                    self.errors_stdout[err] = {
                        "name": err.replace("error: ", ""),
                        "projects": [name],
                        "origin": "clang",
                        "regex": re.escape(err).replace(
                            re.escape("PATH/FILE.EXT"), self.path_regex
                        ),
                    }
                    self.new_errs += 1
                self.add_errors(project, name, [err])
                # remove error from log, so it does not get matched again
        # now we look for cmake errors
        errlines = [l for l in log.splitlines() if len(l) < 1000]
        match_next = False
        multiline_err = ""
        first_line_err = ""  # used for the regex
        for err in errlines:
            # remove paths
            # err = re.sub(self.path_regex, "PATH/FILE.EXT", err)
            # remove file in beginning of line e.g. makefile 96:420:
            # err = re.sub(r"^\S*\.\S*(?:\:|\ )?\d+(?:\:\d+)?\:\ ", "", err)
            if match_next:
                if err[0:2] == "  " and err.strip() != "":
                    # this error is part of the CMake multiline error
                    if multiline_err == "":
                        first_line_err = err.strip()
                    multiline_err += err.strip() + " "
                    log = log.replace(err, "")
                    continue
                elif err.strip() == "":
                    # this is just a newline, sometimes this is here
                    continue
                else:
                    # this is no longer part of same err
                    if multiline_err.strip() != "":
                        if multiline_err not in self.errors_stdout:
                            self.errors_stdout[multiline_err] = {
                                "name": multiline_err,
                                "projects": [name],
                                "origin": "CMake",
                                "regex": re.escape(first_line_err).replace(
                                    re.escape("PATH/FILE.EXT"), self.path_regex
                                ),
                            }
                            self.new_errs += 1
                        self.add_errors(project, name, [multiline_err])
                    match_next = False
                    multiline_err = ""

            # cmake has a line where it prints CMake ERROR at blabla.txt:
            # and then the error in next line
            elif "CMake Error at" in err:
                match_next = True
                log = log.replace(err, "")
                continue
        return log

    def find_new_errors(self, project, name, log):

        errlines = [l for l in log.splitlines() if len(l) < 1000]
        # figure out what to do with other error strings
        # this dict contains the error match and then thi origin, at the
        # end is the most generic one.
        err_patterns = [
            (
                r".*\.o\:" + re.escape(" 'linker' input unused") + r".*$",
                "clang_other",
                re.escape(".o: 'linker' input unused"),
            ),
            (
                re.escape("[Error] Package ") + r".*" + re.escape(" is not installed"),
                "cmake - dependency",
                False,
            ),
            (re.escape("clang: error: ") + r".*$", "clang_other", False),
            (
                re.escape("ERROR - ") + r".*" + re.escape("not found"),
                "dependency",
                False,
            ),
            (
                r".*\s(.+?)" + re.escape(": No such file or directory"),
                "dependency",
                False,
            ),
            (re.escape("configure: error :") + r".*$", "configure", False),
            (re.escape("Errors while running CTest"), "testing", False),
            (
                re.escape("E: Unable to find a source package") + r".*$",
                "debian",
                re.escape("E: Unable to find a source package"),
            ),
            (r"\.\/configure.*syntax\ error.*$", "configure", False),
            (re.escape("ERROR - ") + r".*syntax\ error.*", "syntax error", False),
            (
                re.escape("ERROR - ")
                + r".*"
                + re.escape("Compatibility levels before "),
                "compatibility error",
                False,
            ),
            (re.escape("fatal error: ") + r".*$", "fatal_error", False),
            (r".*" + re.escape("command not found"), "bash_command", False),
            # debian/rules in there to avoid matching to the generic
            # dpkg: error: debian/rules build subprocess returned exit status 2
            (re.escape("error: ") + r"(?!debian/rules).*$", "general_error", False),
            (re.escape("Error: ") + r".*$", "general_error", False),
            (re.escape("ERROR: ") + r".*$", "general_error", False),
        ]

        for err in errlines:
            # for the removal of the error from log
            original_line = err
            # remove paths
            err = re.sub(self.path_regex, "PATH/FILE.EXT", err)
            # remove file in beginning of line e.g. makefile 96:420:
            err = re.sub(r"^\S*\.\S*(?:\:|\ )?\d+(?:\:\d+)?\:\ ", "", err)

            for match, origin, title in err_patterns:
                regex_result = re.search(match, err)
                if regex_result:
                    # regex to extract paths and filenames
                    err = (
                        re.search(title, err).group() if title else regex_result.group()
                    )
                    # print("matched err {}".format(err))
                    if err not in self.errors_stdout:
                        self.errors_stdout[err] = {
                            "name": err,
                            "projects": [name],
                            "origin": origin,
                            "regex": re.escape(err).replace(
                                re.escape("PATH/FILE.EXT"), self.path_regex
                            ),
                        }
                        self.new_errs += 1
                    # elif name not in self.errors_stdout[err]["projects"]:
                    #     self.errors_stdout[err]["projects"].append(name)
                    self.add_errors(project, name, [err])
                    log = log.replace(original_line, "")
                    break
        return log

    def find_deps(self, project, name):
        confident_deps, dependencies = self.dep_finder.analyze_logs(project, name)
        dependencies = confident_deps + dependencies
        self.add_depencenies(dependencies, name)
        project["build"]["missing_dependencies"] = dependencies
        if not project.get("is_first_build", False):
            try:
                self.rebuild_projects[project["type"]][name][
                    "missing_deps"
                ] = dependencies
            except KeyError:
                pass

    def add_depencenies(self, deps, name):
        for dep, src in deps:
            if dep in self.dependencies:
                if name not in self.dependencies[dep]["projects"]:
                    self.dependencies[dep]["count"] += 1
                    self.dependencies[dep]["projects"].append(name)
            else:
                self.dependencies[dep] = {}
                self.dependencies[dep]["count"] = 1
                self.dependencies[dep]["projects"] = [name]

    def map_dependencies(self, missing: list, installed: list, name: str) -> None:
        if installed == []:
            # nothing valuable to add here
            return
        for m, src in missing:
            if m not in self.dep_mapping:
                self.dep_mapping[m] = {}
            if m not in self.persistent_dep_mapping:
                self.persistent_dep_mapping[m] = {}
                self.persistent_dep_mapping[m]["deps"] = {}
                self.persistent_dep_mapping[m]["source"] = src
                self.persistent_dep_mapping[m]["projects"] = []
            for i in installed:
                self.dep_mapping[m][i] = self.dep_mapping[m].get(i, 0) + 1
                self.persistent_dep_mapping[m]["deps"][i] = (
                    self.persistent_dep_mapping[m]["deps"].get(i, 0) + 1
                )
                if name not in self.persistent_dep_mapping[m]["projects"]:
                    self.persistent_dep_mapping[m]["projects"].append(name)

    def add_rebuild_data(self, project, name):
        # we don't want the projects first build if we build twice
        if project.get("is_first_build"):
            return
        # generate info for rebuild
        rebuild_data = {
            "type": project["type"],
            "suite": project.get("suite"),
            "version": project.get("version"),
            "status": project["status"],
            "codebase_data": project.get("codebase_data"),
            "build_system": project.get("build_system", "unrecognized"),
            "previous_errors": project["build"]["errortypes"]
            if "build" in project and "errortypes" in project["build"]
            else None,
        }
        if project["type"] not in self.rebuild_projects:
            self.rebuild_projects[project["type"]] = {}
        self.rebuild_projects[project["type"]][name] = rebuild_data

    def save_errorstat_json(self, path, timestamp):
        path = join(
            path, "errorstats_{}_{}.json".format(timestamp, self.project_count),
        )
        self.errortypes = OrderedDict(
            sorted(
                self.errortypes.items(),
                key=lambda i: i[1].get("amount", 0),
                reverse=True,
            )
        )
        with open(path, "w") as o:
            o.write(json.dumps(self.errortypes, indent=2))

    def save_rebuild_json(self, path, timestamp):
        rebuild_with_missing = {}
        for source, projects in self.rebuild_projects.items():
            for name, p in projects.items():
                if p.get("missing_deps"):
                    if source not in rebuild_with_missing:
                        rebuild_with_missing[source] = {}
                    rebuild_with_missing[source][name] = p

        name = join(path, "rebuild_{}_{}.json".format(timestamp, self.project_count),)
        name_with_missing = join(
            path, "useful_rebuild_{}_{}.json".format(timestamp, self.project_count),
        )
        with open(name, "w") as o:
            o.write(json.dumps(self.rebuild_projects, indent=2))
        with open(name_with_missing, "w") as o:
            o.write(json.dumps(rebuild_with_missing, indent=2))

    def save_errors_json(self, path=None):
        if path is None:
            path = join("code_builder", "errortypes.json")
        self.errors_stdout = OrderedDict(
            sorted(
                self.errors_stdout.items(),
                key=lambda i: i[1].get("amount", 0),
                reverse=True,
            )
        )
        with open(path, "w") as o:
            o.write(json.dumps(self.errors_stdout, indent=2))

    def save_dependencies_json(self, path, timestamp):
        name = join(
            path, "dependencies_{}_{}.json".format(timestamp, self.project_count),
        )
        map_name = join(
            path, "dep_maping_{}_{}.json".format(timestamp, self.project_count),
        )
        self.dependencies = OrderedDict(
            sorted(
                self.dependencies.items(),
                key=lambda i: i[1].get("count", 0),
                reverse=True,
            )
        )
        with open(name, "w") as o:
            o.write(json.dumps(self.dependencies, indent=2))
        with open(map_name, "w") as o:
            o.write(json.dumps(self.dep_mapping, indent=2))
        with open("code_builder/dep_mapping.json", "w") as o:
            o.write(json.dumps(self.persistent_dep_mapping, indent=2))
