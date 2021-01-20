from os.path import isdir, join
import os
import yaml
from yaml.composer import ComposerError
# from yaml.loader import FullLoader
from .ci_helper import append_script, run, set_env_vars
import stat
from subprocess import PIPE


class Context:
    def __init__(self, cfg):
        self.cfg = cfg

    def set_loggers(self, out, err):
        self.out_log = out
        self.err_log = err


class CiSystem:
    def __init__(self, repo_dir, build_dir, idx, ctx, name, project):
        self.repository_path = repo_dir
        self.build_dir = build_dir
        self.idx = idx
        self.ctx = ctx
        self.output_log = ctx.out_log
        self.error_log = ctx.err_log
        self.gh_dir = repo_dir
        self.project = project

    def install(self):
        yml_files = [
            f for f in os.listdir(join(self.gh_dir, ".github/workflows")) if ".yml" in f
        ]
        ymls = []
        for file in yml_files:
            try:
                with open(join(self.gh_dir, ".github/workflows/") + file, "r") as f:
                    yml = yaml.safe_load(f)
                    ymls.append(yml)
            except ComposerError as e:
                self.error_log.print_error(
                    self.idx, "Error parsing {}:\n  {}".format(file, e)
                )
                return False
            except FileNotFoundError:
                self.error_log.print_error(
                    self.idx, "Could not find {}/{}".format(self.gh_dir, file)
                )
                return False
        self.output_log.print_info(
            self.idx, "loaded {} github actions files!".format(len(ymls))
        )
        # let's just run anything, see what sticks...
        for i, yml in enumerate(ymls):
            if not isinstance(yml.get("jobs", False), dict):
                self.error_log.print_info(
                    self.idx, "no job found for {} or is not dict".format(yml_files[i])
                )
                continue
            print("GH_ACTIONS file {}".format(yml_files[i]))
            # before_yml_env = os.environ.copy()
            self.handle_env(yml.get("env"))
            for jobname, job in yml.get("jobs", {}).items():

                jobscript = []
                print("running job {}".format(jobname))
                if not isinstance(job.get("steps", False), list):
                    self.error_log.print_info(
                        self.idx,
                        "no steps found for job {} of {} or is not list".format(
                            jobname, yml_files[i]
                        ),
                    )
                    continue
                # TODO: filter which jobs are worth doing, we dont want to do them all
                if "macos" in job.get("runs-on", "") or "windows" in job.get(
                    "runs-on", ""
                ):
                    # not linux
                    continue
                # list of jobnames we want to skip
                # blacklist is probably better than whitelist,
                # since jobnames can be anything
                blacklist = {"unit", "test", "lint"}
                if any(x in jobname for x in blacklist):
                    print(
                        "skipped job {} of {} because of blacklist".format(
                            jobname, yml_files[i]
                        )
                    )
                    continue
                # we need to go deeper
                stepnum = 0
                before_job_env = os.environ.copy()
                self.handle_env(job.get("env"))
                for stepnum, step in enumerate(job.get("steps", [])):
                    if not isinstance(step, dict) or "run" not in step:
                        self.error_log.print_info(
                            self.idx,
                            "no run in step {} or job {} of {}".format(
                                stepnum, jobname, yml_files[i]
                            ),
                        )
                        continue
                    self.handle_env(step.get("env"))
                    self.handle_env(step.get("with"))
                    append_script(jobscript, step["run"])

                if jobscript == []:
                    print("no runnable jobs for {}".format(jobname))
                    continue
                print("made a big script with {} steps for {}".format(stepnum, jobname))
                # let's run it
                script_file = join(
                    self.gh_dir,
                    "job_{}_{}.sh".format(jobname, yml_files[i].replace(".yml", "")),
                )
                with open(script_file, "w") as f:
                    f.write("#!/bin/bash\n")
                    for s in jobscript:
                        f.write(s)
                        f.write("\n")
                # make it executable
                st = os.stat(script_file)
                os.chmod(script_file, st.st_mode | stat.S_IEXEC)

                # run the script:
                out = run([script_file], cwd=self.gh_dir, stdout=PIPE, stderr=PIPE)
                if out.returncode != 0:
                    self.error_log.print_error(
                        self.idx,
                        "GH_ACTIONS {} failed (error {}):\n{}".format(
                            script_file, out.returncode, out.stderr
                        ),
                    )
                    self.output_log.print_error(
                        self.idx,
                        "GH_ACTIONS {} failed (error {}):\n{}".format(
                            script_file, out.returncode, out.stdout
                        ),
                    )
                    # also print to container log, easier for debugging purposes
                    print(
                        "GH_ACTIONS {} failed:\n{}\nstderr:\n{}".format(
                            script_file, out.stdout, out.stderr,
                        )
                    )
                else:
                    print(
                        "GH_ACTIONS {} success:\n{}\nstderr:\n{}".format(
                            script_file, out.stdout, out.stderr,
                        )
                    )
                os.environ.clear()
                os.environ.update(before_job_env)
            # we keep env vars defined outside of jobs
            # os.environ.clear()
            # os.environ.update(before_yml_env)
        return True

    def handle_env(self, env):
        if not env:
            return
        envlist = ["{}={}".format(key, value) for key, value in env.items()]
        set_env_vars(" ".join(envlist))

    @staticmethod
    def recognize(repo_dir):
        return isdir(join(repo_dir, ".github/workflows"))

    @staticmethod
    def get_docker_image(repo_dir, clang_version=9):
        return False
