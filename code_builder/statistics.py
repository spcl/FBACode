import json
import re
import copy
from os.path import join
from datetime import datetime
from collections import OrderedDict
from fuzzywuzzy import process, fuzz
import fuzzywuzzy
from . import dep_finder


class Statistics:

    path_regex = r"(?:\.\.|\.)?(?:[/]*/)+\S*\.\S+(?:\sline\s\d+:?)?(?=\s|$|\.)"

    def __init__(self, project_count):
        self.correct_projects = 0
        self.incorrect_projects = 0
        self.unrecognized_projects = 0
        self.clone_time = 0
        self.build_time = 0
        with open("code_builder/errortypes.json", "r") as f:
            self.errors_stdout = json.load(f)
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

    def print_stats(self, out):
        print("Repository clone time: %f seconds" % self.clone_time, file=out)
        print("Repository build time: %f seconds" % self.build_time, file=out)
        print("Succesfull builds: %d" % self.correct_projects, file=out)
        print("Failed builds: %d" % self.incorrect_projects, file=out)
        print("Unrecognized builds: %d" % self.unrecognized_projects, file=out)
        print("newly discovered errors: {}".format(self.new_errs), file=out)
        print("Types of build errors:", file=out)
        self.errortypes = OrderedDict(sorted(self.errortypes.items(),
                                             key=lambda i: i[1].get("amount", 0),
                                             reverse=True))
        for err, data in self.errortypes.items():
            print("{}: {}".format(err, data["amount"]), file=out)
        print("unrecognized errors:")
        for err in self.unrecognized_errs:
            print(err, file=out)
        print("\ndetected missing dependencies:", file=out)
        self.dependencies = OrderedDict(sorted(self.dependencies.items(),
                                               key=lambda i: i[1].get("amount", 0),
                                               reverse=True))
        print(json.dumps(self.dependencies, indent=2), file=out)

    def update(self, project, name):
        self.clone_time += project["source"]["time"]
        if "build" in project:
            self.build_time += project["build"]["time"]
        if project["status"] == "unrecognized":
            self.add_unrecognized_project()
            self.add_rebuild_data(project, name)
        elif project["status"] == "success":
            self.add_correct_project()
        elif project["status"] == "crash":
            self.add_incorrect_project()
            self.add_rebuild_data(project, name)
            err = "docker_crash"
            if err not in self.errors_stdout:
                self.errors_stdout[err] = {
                    "name": err,
                    "projects": [name],
                    "origin": "docker",
                    # match to nothing, since crashes are not visible in logs
                    "regex": r"$a",
                    "amount": 1
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
                # new plan:
                # first try to match stderr to existing errors using regex
                # then try to match to existing errors using levenshtein distance (fuzzywuzzy)
                #   - how to handle path substitutions?
                # then add new error pattern
                project["build"]["errortypes"] = []
                print("\nstarting error analysis for {}".format(name))
                err_log = join(project["build"]["dir"], project["build"]["stderr"])
                with open(err_log, "r") as log:
                    text = log.read()
                    if self.match_error_with_regex(project, name, text):
                        print("found err by regex!")
                    elif self.match_error_fuzzy(project, name, text):
                        print("found err by fuzzy search!")
                    elif self.find_new_errors(project, name, text):
                        print("matched new errors!")
                    else:
                        print("no error found yet, looking at docker log...")
                # found no errs yet, check docker log (stdout of build)
                if not project["build"]["errortypes"]:
                    docker_log = join(project["build"]["dir"], project["build"]["docker_log"])
                    with open(docker_log, "r") as log:
                        text = log.read()
                    if self.match_error_with_regex(project, name, text):
                        print("found err by regex!")
                    elif self.match_error_fuzzy(project, name, text):
                        print("found err by fuzzy search!")
                    elif self.find_new_errors(project, name, text):
                        print("matched new errors!")
                    else:
                        print("no errors found for {}... fuck".format(name))
                        self.errortypes["unrecognized"]["amount"] += 1
                        if name not in self.errortypes["unrecognized"]["projects"]:
                            self.errortypes["unrecognized"]["projects"].append(name)
                        project["build"]["errortypes"] = ["unrecognized"]
            self.add_incorrect_project()
            self.add_rebuild_data(project, name)
            self.find_deps(project, name)

    def add_unrecognized_project(self):
        self.unrecognized_projects += 1

    def add_correct_project(self):
        self.correct_projects += 1

    def add_incorrect_project(self):
        self.incorrect_projects += 1

    def add_errors(self, project, name, errors):
        new_errors = [e for e in errors if e not in project['build']['errortypes']]
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
        errors = [err for err in self.errors_stdout
                  if re.search(self.errors_stdout[err]["regex"], log) is not None]
        # we found the following errors
        self.add_errors(project, name, errors)
        return bool(errors)

    def match_error_fuzzy(self, project, name, log):
        lines = [re.sub(self.path_regex, "PATH/FILE.TXT", l) for l in log.splitlines()]
        errors = []
        for l in lines:
            # check if string has any processable character, otherwise continue
            processed = fuzzywuzzy.utils.full_process(l)
            if not processed:
                continue
            matches = process.extract(processed, self.errors_stdout.keys(),
                                      limit=5, scorer=fuzz.ratio)
            # what threshold??
            new_errs = [m[0] for m in matches if m[1] >= 90]
            if new_errs:
                print("matched \n{}\nto\n{} using fuzzy".format(l, new_errs), sep='\n')
            errors.extend([m[0] for m in matches if m[1] >= 90])
        # remove dups
        self.add_errors(project, name, list(set(errors)))
        return bool(errors)

    def find_new_errors(self, project, name, log):
        # try to find the normal clang error line (match to filename.xx:line:col: error: )
        errlines = re.findall(
            r"^.*\..*\:\d+\:\d+\:.*error\:.*$", log, flags=re.MULTILINE)
        # if we have nicely formatted errs from clang, we just add to known errs
        if errlines:
            for err in errlines:
                # remove filename and lines etc.
                err = re.sub(self.path_regex, "PATH/FILE.EXT", err)
                err = re.search(r"error\:.*$", err).group(0)
                if err not in self.errors_stdout:
                    self.errors_stdout[err] = {
                        "name": err.replace("error: ", ''),
                        "projects": [name],
                        "origin": "clang",
                        "regex": re.escape(err).replace(
                            re.escape("PATH/FILE.EXT"), self.path_regex)
                    }
                    self.new_errs += 1
                self.add_errors(project, name, [err])
            return True
        errlines = re.findall(
            r"^.*error.*$", log, flags=re.IGNORECASE | re.MULTILINE)
        # figure out what to do with other error strings
        # this dict contains the error match and then thi origin, at the
        # end is the most generic one.
        err_patterns = [
            (r".*\.o\:" + re.escape(" 'linker' input unused") + r".*$",
                "clang_other", re.escape(".o: 'linker' input unused")),
            (re.escape("[Error] Package ") + r".*" +
                re.escape(" is not installed"), "cmake - dependency", False),
            (re.escape("clang: error: ") +
                r".*$", "clang_other", False),
            (re.escape("ERROR - ") + r".*" + re.escape("not found"),
                "dependency", False),
            (re.escape("ERROR - ") + r".*" + re.escape("No such file or directory"),
                "dependency", False),
            (re.escape("configure: error :") +
                r".*$", "configure", False),
            (re.escape("Errors while running CTest"), "testing", False),
            (re.escape("E: Unable to find a source package") +
                r".*$", "debian", re.escape("E: Unable to find a source package")),
            (r"\.\/configure.*syntax\ error.*$", "configure", False),
            (re.escape("ERROR - ") + r".*syntax\ error.*",
                "syntax error", False),
            (re.escape("ERROR - ") + r".*" + re.escape("Compatibility levels before "),
                "compatibility error", False),
            (re.escape("fatal error: ") +
                r".*$", "fatal_error", False),
            (re.escape("error: ") + r".*$", "general_error", False),
            (re.escape("Error: ") + r".*$", "general_error", False),
            (re.escape("ERROR: ") + r".*$", "general_error", False)
        ]
        found_match = False
        for err in errlines:
            # remove paths
            err = re.sub(self.path_regex, "PATH/FILE.EXT", err)
            # remove file in beginning of line e.g. makefile 96:420:
            err = re.sub(r"^\S*\.\S*(?:\:|\ )?\d+(?:\:\d+)?\:\ ", "", err)
            for match, origin, title in err_patterns:
                regex_result = re.search(match, err)
                if regex_result:
                    # regex to extract paths and filenames
                    err = re.search(title, err).group(
                        ) if title else regex_result.group()
                    print("matched err {}".format(err))
                    if err not in self.errors_stdout:
                        self.errors_stdout[err] = {
                            "name": err,
                            "projects": [name],
                            "origin": origin,
                            "regex": re.escape(err).replace(
                                re.escape("PATH/FILE.EXT"), self.path_regex)
                        }
                        self.new_errs += 1
                    # elif name not in self.errors_stdout[err]["projects"]:
                    #     self.errors_stdout[err]["projects"].append(
                    #         name)
                    self.add_errors(project, name, [err])
                    found_match = True
                    break
        return found_match

    def find_deps(self, project, name):
        dependencies = self.dep_finder.analyze_logs(project, name)
        self.add_depencenies(dependencies, name)
        project["build"]["missing_dependencies"] = dependencies
        self.rebuild_projects[project["type"]][name]["missing_deps"] = dependencies

    def add_depencenies(self, deps, name):
        for dep in deps:
            if dep in self.dependencies:
                self.dependencies[dep]["count"] += 1
                self.dependencies[dep]["projects"].add(name)
            else:
                self.dependencies[dep]["count"] = 1
                self.dependencies[dep]["projects"] = set([name])

    def add_rebuild_data(self, project, name):
        # generate info for rebuild
        rebuild_data = {
            "type": project["type"],
            "suite": project.get("suite"),
            "version": project.get("version"),
            "status": project["status"],
            "codebase_data": project.get("codebase_data"),
            "previous_errors": project["build"]["errortypes"]
            if ("build" in project and "errortypes" in project["build"]) else None
        }
        if project["type"] not in self.rebuild_projects:
            self.rebuild_projects[project["type"]] = {}
        self.rebuild_projects[project["type"]][name] = rebuild_data

    def save_errorstat_json(self, path=None):
        if path is None:
            timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
            path = join(
                "buildlogs",
                "errorstats_{}_{}.json".format(self.project_count, timestamp))
        self.errortypes = OrderedDict(sorted(self.errortypes.items(),
                                             key=lambda i: i[1].get("amount", 0),
                                             reverse=True))
        with open(path, 'w') as o:
            o.write(json.dumps(self.errortypes, indent=2))

    def save_rebuild_json(self, path=None):
        if path is None:
            timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
            path = join(
                "buildlogs",
                "rebuild_{}_{}.json".format(self.project_count, timestamp))
        with open(path, 'w') as o:
            o.write(json.dumps(self.rebuild_projects, indent=2))

    def save_errors_json(self, path=None):
        if path is None:
            path = join("code_builder", "errortypes.json")
        self.errors_stdout = OrderedDict(sorted(self.errors_stdout.items(),
                                                key=lambda i: i[1].get("amount", 0),
                                                reverse=True))
        with open(path, 'w') as o:
            o.write(json.dumps(self.errors_stdout, indent=2))
    
    def save_dependencies_json(self, path=None):
        if path is None:
            timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
            path = join(
                "buildlogs",
                "dependencies_{}_{}.json".format(self.project_count, timestamp))
        self.dependencies = OrderedDict(sorted(self.dependencies.items(),
                                               key=lambda i: i[1].get("amount", 0),
                                               reverse=True))
        with open(path, 'w') as o:
            o.write(json.dumps(self.dependencies, indent=2))
