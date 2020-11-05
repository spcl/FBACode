from os.path import join
import re


class DepFinder:
    def __init__(self):
        self.patterns = [
            re.escape("bash:") + r"(.*)" + re.escape(": command not found"),
            re.escape("ERROR - ") + r"(.*)" + re.escape("not found"),
            re.escape("ERROR - ") + r"(.*)" + re.escape("No such file or directory"),
            re.escape("[Error] Package ") + r"(.*)" + re.escape(" is not installed"),
            
        ]

    def analyze_logs(self, project, name):
        deps = []
        if "build" not in project:
            print("no logfiles found for {}".format(name))
            return []
        print("\nstarting dependency analysis for {}".format(name))
        lognames = ["stderr", "docker_log", "stdout"]
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
                        break
        # remove duplicates
        return list(set(deps))
