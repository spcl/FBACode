from os.path import join
import re


class DepFinder:
    def __init__(self):
        # todo: differentiate between definitive and maybe dependencies
        self.patterns = [
            (r".*\s(.+?): [C|c]ommand not found", "bash"),
            (re.escape("[Error] Package ") + r"(.*) is not installed", None,),
            (r"error: no (.*) found", None),
            # error: Libtool library used but 'LIBTOOL' is undefined
            (r"error: (.*) library used but .* is undefined", "autotools"),
            # match everyting until a (space) or .(space)
            (re.escape("Error: missing ") + r"(.+?(?=\s|\.\s))", None),
            (re.escape("Cannot find ") + r"(.*)\.", None),
            # Can't exec "autoreconf-dickey":
            (re.escape("Can't exec ") + r"\"(.*?)\"", None),
            # /bin/sh: 1: rake: not found
            (r": .*: (.*?): not found", "bash"),
            (r"configure: error: The (.*?) script could not be found", "debian"),
            # debian/rules:8: /usr/share/cdbs/1/rules/utils.mk: No such file or directory
            (r"^.*:\d+: /usr/share/.*/(.*?)\.mk: No such file or directory", "debian"),
        ]
        self.confident_patterns = [
            (re.escape("] ") + r"(.*)" + re.escape(" not found or too old"), None),
            (re.escape("ImportError: No module named '") + r"(.*)\'", "python"),
            (re.escape("Please install ") + r"(.*)\.", None),
            (r"dh: unable to load addon (.*?):", "debian"),
            # (r"you may need to install the (.*?) module", "debian"),
            # clang header not found
            # ./styles.h:26:10: fatal error: 'clxclient.h' file not found
            (r"^.*\..*\:\d+\:\d+\:.*error\: '(.*?)'.*$", "clang"),
            # find a better way to handle the following, but for now, see if is worth it
            # Project ERROR: Unknown module(s) in QT: core gui printsupport svg
            (r"Project ERROR: Unknown module\(s\) in (.*)", "debian"),
            # debian/rules:8: /usr/share/cdbs/1/rules/utils.mk: No such file or directory
            (r"^.*:\d+: /usr/share/(.*?)/.*: No such file or directory", "debian"),
        ]

    def analyze_logs(self, project, name):
        deps = []
        safe_deps = []
        # keep track of lines matched, makes it easier to debug
        project["build"]["dep_lines"] = []
        if "build" not in project:
            print("no logfiles found for {}\n{}".format(name, project))
            return ([], [])
        # if project["build_system"] == "cmake":
        # cmake has multiline errors, so we check for that
        # also we can be pretty confident in cmake errors
        cmake_dep_strings = [
            re.escape('package configuration file provided by "') + r"(.+?(?=\"))",
            re.escape("Could NOT find ") + r"(.+?(?=\s|\.\s))",
            re.escape("Unable to find the ") + r"(.*)" + re.escape("header files."),
        ]
        for err in project["build"].get("errortypes", []):
            for s in cmake_dep_strings:
                name = re.search(s, err)
                if name:
                    project["build"]["dep_lines"].append(err)
                    version = re.search(
                        re.escape('Required is at least version "') + r"(.+?(?=\"))",
                        err,
                    )
                    if version:
                        safe_deps.append((name[1] + "_" + version[1], "cmake"))
                    else:
                        safe_deps.append((name[1], "cmake"))
        # print("\nstarting dependency analysis for {}".format(name))
        # lognames = ["stderr", "docker_log", "stdout"]
        # docker_log can be huge, skip it for now
        # errors get redirected to sterr anyway
        lognames = ["stderr"]
        for logfiles in lognames:
            try:
                err_log = join(project["build"]["dir"], project["build"][logfiles])
                with open(err_log, "r") as log:
                    text = log.read()
                    # find lines about missing deps
            except (KeyError, FileNotFoundError):
                print("dep_finder: error opening log files for {}".format(name))
                return [], []
            # found = False
            for line in text.splitlines():
                for pattern, source in self.confident_patterns:
                    regex_result = re.search(pattern, line)
                    if regex_result:
                        safe_deps.append((regex_result[1].strip(), source))
                        project["build"]["dep_lines"].append(line)
                        found = True
                # if found:
                #     continue
                for pattern, source in self.patterns:
                    regex_result = re.search(pattern, line)
                    if regex_result:
                        deps.append((regex_result[1].strip(), source))
                        project["build"]["dep_lines"].append(line)

        # remove duplicates
        return list(set(safe_deps)), list(set(deps))
