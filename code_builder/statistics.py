from os.path import join


class Statistics:
    # define a few errors: "search term": "error name"
    errors_stdout = {
        "error: ordered comparison between pointer and zero": "ordered comparison between pointer and zero",
        "configure: error: something wrong with LDFLAGS": "something wrong with LDFLAGS",
        "Project ERROR: failed to parse default search paths from compiler output": "failed to parse default search paths from compiler output",
        "clang: error: linker command failed": "linker command failed",
        "error: embedding a directive within macro arguments has undefined behavior": "embedding a directive within macro arguments has undefined behavior",
        "configure: error: could not find gnutls": "configure: error: could not find gnutls",
        "configure: error:": "configure_error",
        "error: use of undeclared identifier": "undeclared identifier",  #racket
        "error: empty search path given via `-L`": "empty search path given via `-L`"  #rust-findshlibs

    }

    def __init__(self):
        self.correct_projects = 0
        self.incorrect_projects = 0
        self.unrecognized_projects = 0
        self.clone_time = 0
        self.build_time = 0
        self.errorypes = {self.errors_stdout[x]: 0 for x in self.errors_stdout}

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

    def update(self, project):
        self.clone_time += project["source"]["time"]
        if "build" in project:
            self.build_time += project["build"]["time"]
        if project["status"] == "unrecognized":
            self.add_unrecognized_project()
        elif project["status"] == "success":
            self.add_correct_project()
        else:
            if "build" in project:
                docker_log = join(project["build"]["dir"], project["build"]["docker_log"])
                with open(docker_log, "r") as log:
                    text = log.read()
                    print(text)
                    errors = [name for err, name in self.errors_stdout.items() if err in text]
                    for err in errors:
                        self.errorypes[err] += 1
                    project["build"]["errortypes"] = errors
            # probs do error statistics
            self.add_incorrect_project()

    def add_unrecognized_project(self):
        self.unrecognized_projects += 1

    def add_correct_project(self):
        self.correct_projects += 1

    def add_incorrect_project(self):
        self.incorrect_projects += 1
