from requests import get
from time import time, sleep
from string import ascii_lowercase
from random import shuffle
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from subprocess import PIPE
import concurrent.futures
import json
import requests
from .utils.driver import run


def maximum_repos(cfg):
    return int(cfg["max_repos"])


def pagination(cfg):
    return int(cfg["pagination"])


class GithubFetcher:
    def __init__(self, cfg, out_log, error_log):
        self.cfg = cfg
        self.out_log = out_log
        self.error_log = error_log
        self.name = "github.org"

    def fetch(self, max_repos):

        # request_params = self.cfg[self.name]
        backoff = 0.5
        address = self.cfg[self.name]["address"]
        request_params = {}
        request_params["sort"] = self.cfg[self.name]["sort"]
        request_params["order"] = self.cfg[self.name]["order"]
        repos_per_page = pagination(self.cfg[self.name])
        page = 1
        if max_repos is None:
            max_repos = maximum_repos(self.cfg[self.name])
        repos_per_page = min(max_repos, repos_per_page)
        request_params["per_page"] = str(repos_per_page)

        # Authorize for higher rate limits
        if "access_token" in self.cfg[self.name]:
            request_params["access_token"] = self.cfg[self.name]["access_token"]

        repos_processed = 0
        results = []
        start = time()
        self.out_log.set_counter(max_repos)
        self.error_log.set_counter(max_repos)
        self.results = None

        unique_names = set()
        while repos_processed < max_repos:
            request_params["page"] = str(page)
            results_page = self.fetch_json(address, request_params, ["C", "Cpp"])
            items = len(results_page["items"])
            if results_page is None:
                self.error_log.error("Incorrect results, end work!")
                return
            # some times GH returns the desired number of results but still, it prints incomplete results
            # restart with more fine-grained paging
            elif results_page["incomplete_results"] and not items == repos_per_page:
                repos_per_page = int(repos_per_page / 2)
                if repos_per_page < 1:
                    self.error_log.error("Couldnt fetch a single repository, end work!")
                    return
                request_params["per_page"] = str(repos_per_page)
                self.error_log.error(
                    "Incomplete results at GitHub API for %d repositories, start again with %d"
                    % (repos_per_page * 2, repos_per_page)
                )
                page = 0
                sleep(backoff)
                backoff *= 2
                continue
            # paging restart can let to duplicating some results
            for result in results_page["items"]:
                if result["full_name"] not in unique_names:
                    results.append(result)
                    repos_processed += 1
            self.out_log.next(repos_per_page)
            self.error_log.next(repos_per_page)
            self.out_log.info(
                "Fetched %d repositories for C and C++ with GitHub API" % repos_per_page
            )
            page += 1

        end = time()
        self.out_log.info(
            "Processed %d repositories in %f seconds" % (repos_processed, end - start)
        )
        # Mix C and C++ projects and sort them together
        reversed_order = request_params["order"] == "desc"
        sort_key = request_params["sort"]
        self.results = sorted(
            results, key=lambda x: x[sort_key], reverse=reversed_order
        )

    def process_results(self, data):
        if self.results is None:
            return None
        processed_results = {}
        for repo in self.results:
            # dict https://stackoverflow.com/questions/3420122/filter-dict-to-contain-only-certain-keys
            data = {
                key: repo[key]
                for key in (
                    "git_url",
                    "updated_at",
                    "name",
                    "default_branch",
                    "language",
                )
            }
            processed_results[repo["full_name"]] = {
                "type": "github.org",
                "status": "new",
                "recently_updated": True,
                "codebase_data": data,
                "owner": repo["owner"]["login"],
            }

        if data is None:
            return processed_results
        else:
            return processed_results

    def update(self, existing_repo):
        pass

    def fetch_json(self, address, params, languages):

        # language:C+Cpp+...
        # https://developer.github.com/v3/search/
        params["q"] = r"+".join(map(lambda l: "language:%s" % l, languages))
        # New API - GH doesn't want to have token passed in the query
        # https://developer.github.com/changes/2020-02-10-deprecating-auth-through-query-param/
        token = params["access_token"]
        params_to_parse = dict(params)
        del params_to_parse["access_token"]
        # Avoid percent encoding of plus sign - GH does not like that
        params_str = "&".join(
            "{0}={1}".format(key, value) for key, value in params_to_parse.items()
        )
        headers = {"Authorization": token}

        r = get(address, params_str, headers=headers)
        if r.status_code != 200:
            self.error_log.error(
                "Failed to fetch from GitHub, url %s, text %s", r.url, r.text
            )
            return None
        else:
            return r.json()


class DebianFetcher:
    def __init__(self, cfg, out_log, error_log, thread_count=50):
        self.cfg = cfg
        self.out_log = out_log
        self.error_log = error_log
        self.name = "debian"
        self.suite = cfg["debian"]["suite"]
        self.thread_count = int(cfg["debian"]["threads"])
        self.shuffle = bool(cfg["debian"]["shuffle"])

    def fetch(self, max_repos=None):
        # fetch results to self.results
        if not max_repos:
            max_repos = -1
        self.max_repos = max_repos
        repo_count = 0
        self.results = []
        self.out_log.set_counter(max_repos)
        self.error_log.set_counter(max_repos)
        start = time()
        # lets get random pkgs from the whole list -> more randomness
        all_pkgs = get(
            "https://sources.debian.org/api/list/?suite={}".format(self.suite)
        )
        if all_pkgs.status_code != 200:
            self.error_log.error(
                "error fetching {}, code {}".format(all_pkgs.url, all_pkgs.status_code)
            )
            return False
        pkg_list = all_pkgs.json()["packages"]
        if self.shuffle:
            shuffle(pkg_list)
        futures = []
        index = 0
        print("Loaded all {} debian packages".format(len(pkg_list)))
        with ProcessPoolExecutor(max_workers=self.thread_count) as executor:
            # start thread_count workers
            for index in range(0, self.thread_count):
                future = executor.submit(self.package_info, pkg_list[index]["name"])
                futures.append(future)
                # sleep(0.05)
            # when one finishes, increment counter and add a new one to the queue
            while len(futures) > 0:
                done, _ = concurrent.futures.wait(
                    futures, return_when=concurrent.futures.FIRST_COMPLETED
                )
                for future in done:
                    result = future.result()
                    futures.remove(future)

                    if not result is False:
                        self.results.append(result)
                        repo_count += 1
                        print(
                            "[{}/{}] debian c/c++ packages found".format(
                                repo_count, max_repos
                            ),
                            end="\r",
                        )
                    if index < len(pkg_list):
                        new_future = executor.submit(
                            self.package_info, pkg_list[index]["name"]
                        )
                        futures.append(new_future)
                        index += 1

        print("done!")
        end = time()
        self.out_log.info(
            "got {} c/c++ packages in {} seconds!".format(repo_count, end - start)
        )
        return True

    def process_results(self, data):
        if not self.results:
            return False
        processed_results = {}
        for i, pkg in enumerate(self.results):
            if i == self.max_repos:
                break
            processed_results[pkg["name"]] = {
                "type": "debian",
                "version": pkg["version"],
                "suite": pkg["suite"],
                "recently_updated": True,
                "status": "new",
                "codebase_data": {
                    "sloc": pkg["sloc"],
                    "vcs_url": pkg["vcs_browser"],
                    "vcs_type": pkg["vcs_type"],
                },
            }
        return processed_results

    def update(self, existing_repo):
        pass

    def package_info(self, name):
        # get the version number for this package
        try:
            response = get(
                "https://sources.debian.org/api/src/{}/?suite={}".format(name, self.suite),
                timeout = 15
            )
        except Exception as e:
            self.error_log.error("Failed to get src for {} with error: {}".format(name, e))
            return False
        if response.status_code != 200:
            self.error_log.error(
                "error fetching pkg versions for {}, code {}".format(
                    name, response.status_code
                )
            )
            self.error_log.error(
                "full URL is: {}".format(
                    "https://sources.debian.org/api/src/{}/?suite={}".format(name, self.suite)
                )
            )
            return False
        # first version should be correct because we specify suite in url
        if not isinstance(response.json().get("versions"), list):
            print("weird json response:")
            print(response.json())
            return False
        if len(response.json()["versions"]) == 0:
            # print("is not in {} suite".format(self.suite))
            return False
        version = response.json()["versions"][0]["version"]
        # get more info for package and version
        try:
            response = get(
                "https://sources.debian.org/api/info/package/{}/{}".format(name, version),
                timeout = 10
            )
        except Exception as e:
            self.error_log.error(
                "Failed to get pkg info for {} with error: {}".format(name, e)
            )
            return False
        if response.status_code != 200:
            self.error_log.error(
                "error fetching pkg info for {}, code {}".format(
                    name, response.status_code
                )
            )
            self.error_log.error(
                "full URL is: {}".format(
                    "https://sources.debian.org/api/info/package/{}/{}".format(name, version)
                )
            )
            return False
        # only keep packages with mostly c or c++
        # c_names = ["ansic", "cpp"]
        c_names = ["cpp"]
        # uncomment to include packages which contain any amount of c/c++
        c_sloc = [
            {lang[0]: lang[1]}
            for lang in response.json()["pkg_infos"]["sloc"]
            if lang[0] in c_names
        ]
        # if response.json()["pkg_infos"]["sloc"][0][0] in c_names:
        if any(c_sloc) and int(response.json()["pkg_infos"]["sloc"][0][1]):
            return {
                "version": version,
                "name": name,
                "sloc": response.json()["pkg_infos"]["sloc"],
                "suite": self.suite,
                "vcs_browser": response.json()["pkg_infos"]["vcs_browser"]
                if "vcs_browser" in response.json()["pkg_infos"]
                else None,
                "vcs_type": response.json()["pkg_infos"]["vcs_type"]
                if "vcs_type" in response.json()["pkg_infos"]
                else None
            }
        return False

class ConanFetcher:
    def __init__(self, cfg, out_log, error_log):
        self.cfg = cfg
        self.out_log = out_log
        self.error_log = error_log
        self.name = "conan"
        self.shuffle = bool(cfg["conan"]["shuffle"])

        self.results = {}
        self.max_repos = None

    def fetch(self, max_repos = -1):
        # fetch results to self.results
        self.max_repos = max_repos
        repo_count = 0
        self.out_log.set_counter(max_repos)
        self.error_log.set_counter(max_repos)
        start = time()

        out = run(
            [
                "bash",
                "-c",
                "shopt -s dotglob; conan search \"*\" --remote=conancenter --format=json"
            ],
            capture_output=True,
            text = True
        )

        pkg_list = list(json.loads(out.stdout)["conancenter"].keys())
        unique_pkgs = list(set([name[:name.rfind('/')] for name in pkg_list]))

        new_pkg_list = [[pkg for pkg in pkg_list if pkg_name in pkg][-1] for pkg_name in unique_pkgs]
        pkg_list = new_pkg_list

        if self.shuffle:
            shuffle(pkg_list)
        
        index = 0
        print("Conan search returned {} packages".format(len(pkg_list)))

        for idx, pkg in enumerate(pkg_list):
            if repo_count >= max_repos:
                break
            pkg = pkg.replace("/", "@")
            result = self.package_info(pkg)
            if result is not False:
                repo_count += 1
                self.results.update(result)
                print(
                    "[{}/{}] conan c/c++ packages found".format(
                        repo_count, max_repos
                    ),
                    end="\r",
                )

        print("done!")
        end = time()
        self.out_log.info(
            "got {} c/c++ packages in {} seconds!".format(repo_count, end - start)
        )
        return True

    def process_results(self, data):
        return self.results

    def update(self, existing_repo):
        pass

    def package_info(self, name):
        package_name = name[:name.rfind('@')]
        package_version = name[name.rfind('@') + 1:]
        return {
            name: {
                "name": package_name,
                "version": package_version,
                "status": "new",
                "type": "conan"
            }
        }

code_sources = {"github.org": GithubFetcher, "debian": DebianFetcher, "conan": ConanFetcher}


def fetch_projects(cfg, out_log, error_log, max_repos=None):
    data = {}
    for name, src in code_sources.items():
        if cfg[name]["active"] == "False":
            out_log.info("Skip inactive code source: {0}".format(name))
            continue
        out_log.info("fetching {} repos for {}".format(max_repos, name))
        fetcher = src(cfg, out_log, error_log)
        fetcher.fetch(max_repos)
        data[name] = fetcher.process_results(data)
    return data


def update_projects(repo, cfg, out_log, error_log):
    pass
