from os.path import join
import re


class DepFinder:
    def __init__(self):
        # todo: differentiate between definitive and maybe dependencies
        self.patterns = [
            r".*\s(.+?)" + re.escape(": command not found"),
            # r".*\s(.+?)" + re.escape("not found"),
            # r".*\s(.+?)" + re.escape(": No such file or directory"),
            re.escape("[Error] Package ") + r"(.*)" + re.escape(" is not installed"),
            re.escape("Error: No module named '") + r"(.*)\'",
            # match everyting until a (space) or .(space)
            re.escape("Error: missing ") + r"(.+?(?=\s|\.\s))",
            re.escape("Could NOT find ") + r"(.+?(?=\s|\.\s))",
            # r".*\s(.+?)" + re.escape(": No such file or directory"),
        ]
        self.confident_patterns = [
        ]

    def analyze_logs(self, project, name):
        deps = []
        safe_deps = []
        project["dep_lines"] = []
        if "build" not in project:
            print("no logfiles found for {}".format(name))
            return []
        if project["build_system"] == "cmake":
            # cmake has multiline errors, so we check for that
            # also we can be pretty confident in cmake errors
            cmake_dep_strings = [
                re.escape('package configuration file provided by "') + r"(.+?(?=\"))",
                re.escape("Could NOT find ") + r"(.+?(?=\s|\.\s))"
            ]
            for err in project["build"].get("errortypes", []):
                for s in cmake_dep_strings:
                    name = re.search(s, err)
                    if name:
                        project["dep_lines"].append(err)
                        version = re.search(
                            re.escape('Required is at least version "') + r"(.+?(?=\"))",
                            err
                        )
                        if version:
                            safe_deps.append(name[1] + "_" + version[1])
                        else:
                            safe_deps.append(name[1])
                        break
        # print("\nstarting dependency analysis for {}".format(name))
        # lognames = ["stderr", "docker_log", "stdout"]
        # docker_log can be huge, skip it for now
        # errors get redirected to sterr anyway
        lognames = ["stderr"]
        for logfiles in lognames:
            err_log = join(project["build"]["dir"], project["build"][logfiles])
            with open(err_log, "r") as log:
                text = log.read()
                # find lines about missing deps
            for line in text.splitlines():
                for pattern in self.patterns:
                    regex_result = re.search(pattern, line)
                    if regex_result:
                        deps.append(regex_result[1].strip())
                        project["dep_lines"].append(line)
                        break
        
        # remove duplicates
        return list(set(safe_deps)), list(set(deps))
