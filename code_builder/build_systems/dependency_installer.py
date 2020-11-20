from subprocess import run, PIPE
import urllib.request
import json
import yaml
from os.path import join
import os


def parse_travis(project, path):
    os.environ["TRAVIS_BUILD_DIR"] = path
    os.environ["TRAVIS_OS"] = "linux"
    with open(join(path, ".travis.yml"), "r") as f:
        yml = yaml.load(f, Loader=yaml.loader.FullLoader)
    if yml.get("addons") is not None:
        if not travis_addons(project, yml["addons"]):
            return False
    os.environ["TRAVIS_BUILD_DIR"] = path
    # not sure if it is a good idea to also run scripts...
    if yml.get("before_install") is not None:
        print("TRAVIS: running before_install")
        if not run_travis_scripts(project, yml["before_install"], path):
            return False
    # run the install
    if yml.get("install") is not None:
        print("TRAVIS: running install")
        if not run_travis_scripts(project, yml["install"], path):
            return False
    # run the before_script part
    if yml.get("before_script") is not None:
        print("TRAVIS: running before_script")
        if not run_travis_scripts(project, yml["before_script"], path):
            return False
    return True


def run_travis_scripts(project, script_list, travis_path):
    if isinstance(script_list, str):
        script_list = [script_list]
    elif not isinstance(script_list, list):
        project.error_log.print_error(
            project.idx, "travis script not string or list: {}".format(script_list)
        )
        return True
    for cmd in script_list:
        print("TRAVIS: {}".format(cmd))
        out = run(["bash", "-c", cmd], cwd=travis_path, stderr=PIPE)
        if out.returncode != 0:
            project.error_log.print_error(
                project.idx, "running command \n{}\nfailed".format(cmd)
            )
            project.error_log.print_error(
                project.idx, "{}:\n{}".format(out.args, out.stderr.decode("utf-8"))
            )
            return False
    return True


def travis_addons(project, addons):
    apt = addons.get("apt")
    # in case it's just a string or list of strings
    if apt and (isinstance(apt, str) or
                isinstance(apt, list) and all(isinstance(i, str) for i in apt)):
        cmd = ["apt-get", "install", "-y", "--force-yes",
                "--no-install-recommends", apt]
        out = run(cmd, stderr=PIPE)
        if out.returncode != 0:
            project.error_log.print_error(project.idx, "apt_packages install from .travis.yml failed")
            project.error_log.print_error(project.idx, "{}:\n{}".format(out.args, out.stderr.decode("utf-8")))
            return False
    # in case it is more complicated
    elif apt:
        do_update = False
        if apt.get("sources", None) is not None:
            # add apt sources accoring to the yaml
            do_update = True
            # download apt source safelist file
            safelist = None
            url = "https://raw.githubusercontent.com/travis-ci/apt-source-safelist/master/ubuntu.json"
            with urllib.request.urlopen(url) as resp:
                safelist = json.loads(resp.read().decode())
            for source in apt.get("sources", []):
                key_url = None
                source_url = None
                if isinstance(source, str):
                    # this should be in safelist
                    safelist_entry = [i for i in safelist if i["alias"] == source]
                    if not safelist_entry:
                        # found nothing in safelist, try to use this string as url
                        source_url = source
                    else:
                        key_url = safelist_entry[0].get("canonical_key_url", None)
                        source_url = safelist_entry[0].get("sourceline")
                else:
                    key_url = source.get("key_url", None)
                    source_url = source.get("sourceline")
                if key_url:
                    cmd = ["sh", "-c", "wget -q0 - {} | apt-key add -".format(key_url)]
                    out = run(cmd, cwd=project.build_dir, stderr=PIPE)
                    if out.returncode != 0:
                        project.error_log.print_error(project.idx, "adding key to repo failed")
                        project.error_log.print_error(project.idx, "{}:\n{}".format(out.args, out.stderr.decode("utf-8")))
                        return False
                if source_url is None:
                    project.error_log.print_error(project.idx, "wrong format of sourceline in travis")
                    return False
                cmd = ["add-apt-repository", source_url]
                out = run(cmd, cwd=project.build_dir, stderr=PIPE)
                if out.returncode != 0:
                    project.error_log.print_error(project.idx, "adding repo failed")
                    project.error_log.print_error(project.idx, "{}:\n{}".format(out.args, out.stderr.decode("utf-8")))
                    return False
        if apt.get("update") or do_update:
            cmd = ["apt-get", "update"]
            out = run(cmd, stderr=PIPE)
            if out.returncode != 0:
                project.error_log.print_error(project.idx, "apt update from .travis.yml failed")
                project.error_log.print_error(project.idx, "{}:\n{}".format(out.args, out.stderr.decode("utf-8")))
                return False
        if apt.get("packages") is not None:
            if isinstance(apt["packages"], str):
                print("am string")
                cmd = ["apt-get", "install", "-y", "--force-yes",
                       "--no-install-recommends", apt["packages"]]
            else:
                # we have a list of packages
                print("am not string, am {}".format(type(apt["packages"])))
                cmd = ["apt-get", "install", "-yq", "--force-yes",
                       "--no-install-recommends"]
                cmd.extend(apt["packages"])
            print(cmd)
            out = run(cmd, stderr=PIPE)
            if out.returncode != 0:
                project.error_log.print_error(project.idx, "apt install from .travis.yml failed")
                project.error_log.print_error(project.idx, "{}:\n{}".format(out.args, out.stderr.decode("utf-8")))
                return False

    apt_packages = addons.get("apt_packages")
    if apt_packages:
        cmd = ["apt-get", "install", "-y", "--force-yes",
                "--no-install-recommends", apt]
        out = run(cmd, stderr=PIPE)
        if out.returncode != 0:
            project.error_log.print_error(project.idx, "apt_packages install from .travis.yml failed")
            project.error_log.print_error(project.idx, "{}:\n{}".format(out.args, out.stderr.decode("utf-8")))
            return False
    # run the snap module
    snaps = addons.get("snaps")
    if snaps is not None:

        if isinstance(snaps, str):
            cmd = ["snap", "install", snaps]
            out = run(cmd, stderr=PIPE)
            if out.returncode != 0:
                project.error_log.print_error(project.idx, "snap install from .travis.yml failed")
                project.error_log.print_error(project.idx, "{}:\n{}".format(out.args, out.stderr.decode("utf-8")))
                return False
        else:
            for snap in snaps:
                if isinstance(snap, str):
                    cmd = ["snap", "install", snap]
                else:
                    if "name" not in snap:
                        project.error_log.print_error(project.idx, "invalid yaml file, snap name missing")
                        return False
                    cmd = ["snap", "install", snap["name"]]
                    if snap.get("confinement") is not None:
                        cmd.append("--{}".format(snap["confinement"]))
                    if snap.get("channel") is not None:
                        cmd.append("--channel={}".format(snap["channel"]))
                out = run(cmd, cwd=project.build_dir, stderr=PIPE)
                if out.returncode != 0:
                    project.error_log.print_error(project.idx, "snap install from .travis.yml failed")
                    project.error_log.print_error(project.idx, "{}:\n{}".format(out.args, out.stderr.decode("utf-8")))
                    return False
    return True
