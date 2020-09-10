import json
import re
from os.path import join
from datetime import datetime


class Statistics:
    # define a few errors: "search term": "error name"
    # errors_stdout = {
    #     "error: ordered comparison between pointer and zero": "ordered comparison between pointer and zero",
    #     "configure: error: something wrong with LDFLAGS": "something wrong with LDFLAGS",
    #     "Project ERROR: failed to parse default search paths from compiler output": "failed to parse default search paths from compiler output",
    #     "clang: error: linker command failed": "linker command failed",
    #     "error: embedding a directive within macro arguments has undefined behavior": "embedding a directive within macro arguments has undefined behavior",
    #     "configure: error: could not find gnutls": "configure: error: could not find gnutls",
    #     "configure: error:": "configure_error",
    #     "error: use of undeclared identifier": "undeclared identifier",  #racket
    #     "error: empty search path given via `-L`": "empty search path given via `-L`",  #rust-findshlibs
    #     "error: invalid suffix on literal": "error: invalid suffix on literal", #vdr-plugin-mp3
    #     "error: 'iostream' file not found": "'iostream' not found",  #rapmap

    # }

    def __init__(self):
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
        self.save_errors_json()
        self.errorypes = {self.errors_stdout[x]["name"]: 0 for x in self.errors_stdout}
        self.errorypes["unrecognized"] = 0
        # save the failed projects, so we can retry them later
        self.rebuild_projects = {}

    def print_stats(self, out):
        print("Repository clone time: %f seconds" % self.clone_time, file=out)
        print("Repository build time: %f seconds" % self.build_time, file=out)
        print("Succesfull builds: %d" % self.correct_projects, file=out)
        print("Failed builds: %d" % self.incorrect_projects, file=out)
        print("Unrecognized builds: %d" % self.unrecognized_projects, file=out)
        print("Types of build errors:", file=out)
        for err, count in self.errorypes.items():
            if count > 0:
                print("{}: {}".format(err, count), file=out)

    def update(self, project, name):
        self.clone_time += project["source"]["time"]
        if "build" in project:
            self.build_time += project["build"]["time"]
        if project["status"] == "unrecognized":
            self.add_unrecognized_project()
            self.add_rebuild_data(project, name)
        elif project["status"] == "success":
            self.add_correct_project()
        else:
            if "build" in project:
                print("\nstarting error analysis for {}".format(name))
                err_log = join(project["build"]["dir"], project["build"]["stderr"])
                with open(err_log, "r") as log:
                    text = log.read()
                    # try to find the normal clang error line
                    errlines = re.findall(r"error:.*$", text, flags=re.MULTILINE)
                    clang_errs = True
                    print(name)
                    if errlines == []:
                        print("could not find <error:> pattern..")
                        errlines = re.findall(r"^.*error.*$", text, flags=re.IGNORECASE | re.MULTILINE)
                        clang_errs = False
                    print(errlines)
                    # if we have nicely formatted errs from clang, we just add to known errs
                    if clang_errs:
                        for err in errlines:
                            if err not in self.errors_stdout:
                                self.errors_stdout[err] = {
                                    "name": err.replace("error: ", ''),
                                    "projects": [name],
                                    "origin": "clang",
                                    "regex": re.escape(err)
                                }
                                self.errorypes[err.replace("error: ", '')] = 0
                            elif name not in self.errors_stdout[err]["projects"]:
                                self.errors_stdout[err]["projects"].append(name)
                    else:
                        # figure out what to do with other error strings
                        print("not clang errs")
                    errors = [x["name"] for err, x in self.errors_stdout.items() if re.search(x["regex"], text) is not None]
                    for err in errors:
                        self.errorypes[err] += 1
                    project["build"]["errortypes"] = errors
                    if not errors:
                        self.errorypes["unrecognized"] += 1
            # probs do error statistics
            self.add_incorrect_project()
            self.add_rebuild_data(project, name)
      
    def add_unrecognized_project(self):
        self.unrecognized_projects += 1

    def add_correct_project(self):
        self.correct_projects += 1

    def add_incorrect_project(self):
        self.incorrect_projects += 1

    def add_rebuild_data(self, project, name):
        # generate info for rebuild
        rebuild_data = {
            "type": project["type"],
            "suite": project["suite"] if "suite" in project else None,
            "version": project["version"],
            "status": project["status"],
            "codebase_data": project["codebase_data"] if "codebase_data" in project else None
            }
        if project["type"] not in self.rebuild_projects:
            self.rebuild_projects[project["type"]] = {}
        self.rebuild_projects[project["type"]][name] = rebuild_data

    def save_rebuild_json(self, path=None):
        if path is None:
            timestamp = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
            path = join("buildlogs", "rebuild_{}.json".format(timestamp))
        with open(path, 'w') as o:
            o.write(json.dumps(self.rebuild_projects, indent=2))

    def save_errors_json(self, path=None):
        if path is None:
            path = join("code_builder", "errortypes.json")
        with open(path, 'w') as o:
            o.write(json.dumps(self.errors_stdout, indent=2))
