from os.path import isdir, join
import os
import yaml
from yaml.loader import FullLoader
from .ci_helper import append_script, run, set_env_vars
from os import stat
from subprocess import PIPE


class Context:
    def __init__(self, cfg):
        self.cfg = cfg

    def set_loggers(self, out, err):
        self.out_log = out
        self.err_log = err


class CiSystem:
    def __init__(self, repo_dir, build_dir, idx, ctx, project):
        self.repository_path = repo_dir
        self.build_dir = build_dir
        self.idx = idx
        self.ctx = ctx
        self.output_log = ctx.out_log
        self.error_log = ctx.err_log
        self.gh_dir = repo_dir
        self.project = project

    def install(self):
        yml_files = [f for f in os.listdir(join(self.gh_dir, ".github/workflows"))
                     if ".yml" in f]
        ymls = []
        for file in yml_files:
            try:
                with open(join(self.gh_dir, ".github/workflows/") + file, "r") as f:
                    yml = yaml.load(f, Loader=FullLoader)
                    ymls.append(yml)
            except yaml.composer.ComposerError as e:
                self.error_log.print_error(
                    self.idx, "Error parsing {}:\n  {}".format(file, e))
                return False
            except FileNotFoundError:
                self.error_log.print_error(
                    self.idx, "Could not find {}/{}".format(self.gh_dir, file))
                return False
        self.output_log.print_info(
            self.idx, "loaded {} github actions files!".format(len(ymls)))
        # let's just run anything, see what sticks...
        for i, yml in enumerate(ymls):
            if not isinstance(yml.get("jobs", False), dict):
                self.error_log.print_info(
                    self.idx, "no job found for {} or is not dict".format(yml_files[i]))
                continue
            before_yml_env = os.environ.copy()
            self.handle_env(yml.get("env"))
            for jobname, job in yml.get("jobs", {}).items():
                # TODO: filter which jobs are worth doing, we probs dont want to do them all
                jobscript = []
                print("running job {}".format(jobname))
                if not isinstance(job.get("steps", False), list):
                    self.error_log.print_info(
                        self.idx,
                        "no steps found for job {} of {} or is not list".format(
                            jobname, yml_files[i]))
                    continue
                if "macos" in job.get("runs-on", "") or "windows" in job.get("runs-on", ""):
                    # not linux
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
                                stepnum, jobname, yml_files[i]))
                        continue
                    self.handle_env(step.get("env"))
                    self.handle_env(step.get("with"))
                    append_script(jobscript, step["run"])
                    
                print("made a big script with {} steps for {}".format(stepnum, jobname))
                # let's run it
                script_file = join(self.gh_dir, "job_{}.sh".format(jobname))
                with open(script_file, 'w') as f:
                    f.write("#!/bin/bash\nset +e\n")
                    for s in jobscript:
                        f.write(s)
                        f.write("\n")
                # make it executable
                st = os.stat(script_file)
                os.chmod(script_file, st.st_mode | stat.S_IEXEC)

                # run the script:
                out = run([script_file], cwd=self.travis_dir, stdout=PIPE, stderr=PIPE)
                if out.returncode != 0:
                    self.error_log.print_error(
                        self.idx, "GH_ACTIONS job_{}.sh failed (error {}):\n{}".format(
                            jobname, out.returncode, out.stderr.decode("utf-8")))
                    self.error_log.print_info(self.idx, out.stdout.decode("utf-8"))

                else:
                    print("GH_ACTIONS job_{}.sh :\n{}\nstderr:\n{}".format(
                        jobname, out.stdout.decode("utf-8"), out.stderr.decode("utf-8")))
                os.environ.clear()
                os.environ.update(before_job_env)
            os.environ.clear()
            os.environ.update(before_yml_env)
        return True
    
    def handle_env(sefl, env):
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
