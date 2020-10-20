from requests import get
from time import time, sleep
from string import ascii_lowercase
from random import shuffle


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

        while repos_processed < max_repos:
            request_params["page"] = str(page)
            results_page = self.fetch_json(
                address, request_params, ["C", "Cpp"])
            if results_page is None:
                self.error_log.error("Incorrect results, end work!")
                return
            elif results_page["incomplete_results"]:
                repos_per_page /= 2
                if repos_per_page < 1:
                    self.error_log.error(
                        "Couldnt fetch a single repository, end work!")
                    return
                request_params["per_page"] = str(repos_per_page)
                self.error_log.error(
                    "Incomplete results at GitHub API for %d repositories, start again with %d"
                    % (repos_per_page * 2, repos_per_page)
                )
                sleep(backoff)
                backoff *= 2
                continue
            repos_processed += repos_per_page
            results += results_page["items"]
            self.out_log.next(repos_per_page)
            self.error_log.next(repos_per_page)
            self.out_log.info(
                "Fetched %d repositories for C and C++ with GitHub API" % repos_per_page
            )
            page += 1

        end = time()
        self.out_log.info(
            "Processed %d repositories in %f seconds" % (
                repos_processed, end - start)
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
                "type": "git",
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
        # Avoid percent encoding of plus sign - GH does not like that
        params_str = "&".join(
            "{0}={1}".format(key, value) for key, value in params.items()
        )
        r = get(address, params_str)
        if r.status_code != 200:
            self.error_log.error(
                "Failed to fetch from GitHub, url %s, text %s", r.url, r.text
            )
            return None
        else:
            return r.json()


class DebianFetcher:

    def __init__(self, cfg, out_log, error_log):
        self.cfg = cfg
        self.out_log = out_log
        self.error_log = error_log
        self.name = "debian"
        # https://sources.debian.org/doc/api/
        prefixes_nums = ['0', '2', '3', '4', '6', '7', '8', '9']
        prefixes_lib = ["lib-", "lib3"] + ["lib" + x for x in ascii_lowercase]
        self.prefixes = (prefixes_nums
                         + list(ascii_lowercase[:12])
                         + prefixes_lib
                         + list(ascii_lowercase[12:]))
        self.suite = cfg["debian"]["suite"]

    def fetch(self, max_repos=None):
        # fetch results to self.results
        if not max_repos:
            max_repos = -1
        repo_count = 0
        self.results = []
        self.out_log.set_counter(max_repos)
        self.error_log.set_counter(max_repos)
        start = time()
        # comment for predictable results
        shuffle(self.prefixes)
        for i, prefix in enumerate(self.prefixes):
            self.out_log.info("fetching pkgs with prefix {}".format(prefix))
            prefix_response = get(
                "https://sources.debian.org/copyright/api/prefix/{}/?suite={}".format(prefix, self.suite))
            if prefix_response.status_code != 200:
                # hmmm fuck
                self.error_log.error("error fetching {}, code {}".format(
                    prefix_response.url, prefix_response.status_code))
                return False
            data = prefix_response.json()
            # comment for predictable results
            shuffle(data["packages"])
            for pkg in data["packages"]:
                if self.package_info(pkg):
                    repo_count += 1
                    self.out_log.next()
                    self.error_log.next()
                if repo_count == max_repos:
                    break
            if repo_count == max_repos:
                break
        end = time()
        self.out_log.info(
            "got {} c/c++ packages in {} seconds!".format(repo_count, end - start))
        return True

    def process_results(self, data):
        if not self.results:
            return False
        processed_results = {}
        for pkg in self.results:
            processed_results[pkg["name"]] = {
                "type": "debian",
                "version": pkg["version"],
                "suite": pkg["suite"],
                "recently_updated": True,
                "status": "new",
                "codebase_data": {
                    "sloc": pkg["sloc"],
                    "vcs_url": pkg["vcs_browser"],
                    "vcs_type": pkg["vcs_type"]
                }
            }
        return processed_results

    def update(self, existing_repo):
        pass

    def package_info(self, pkg):
        # get the version number for this package
        self.out_log.info("fetching info for {}".format(pkg["name"]))
        response = get(
            "https://sources.debian.org/api/src/{}/?suite={}".format(pkg["name"], self.suite))
        if response.status_code != 200:
            self.error_log.error("error fetching pkg versions for {}, code {}".format(
                pkg["name"],
                response.status_code))
            return False
        # first version should be correct because we specify suite in url
        version = response.json()["versions"][0]["version"]
        # get more info for package and version
        response = get(
            "https://sources.debian.org/api/info/package/{}/{}".format(pkg["name"], version))
        if response.status_code != 200:
            self.error_log.error("error fetching pkg info for {}, code {}".format(
                pkg["name"],
                response.status_code))
            return False
        # only keep packages with mostly c or c++
        c_names = ["ansic", "cpp"]
        # uncomment to include packages which contain any amount of c/c++
        c_sloc = [{lang[0]: lang[1]} for lang in response.json()["pkg_infos"]["sloc"] if lang[0] in c_names]
        # if response.json()["pkg_infos"]["sloc"][0][0] in c_names:
        # XXX: ignore packages with more than 1mil LOC (just for testing)
        if any(c_sloc) and int(response.json()["pkg_infos"]["sloc"][0][1]) < 100000:
            self.out_log.info("contains c/c++!")
            self.results.append({
                # pkg["name"]: {
                "version": version,
                "name": pkg["name"],
                "sloc": response.json()["pkg_infos"]["sloc"],
                "suite": self.suite,
                "vcs_browser": response.json()["pkg_infos"]["vcs_browser"] if "vcs_browser" in response.json()["pkg_infos"] else None,
                "vcs_type": response.json()["pkg_infos"]["vcs_type"] if "vcs_type" in response.json()["pkg_infos"] else None
                # }
            })
            return True
        return False


code_sources = {"github.org": GithubFetcher, "debian": DebianFetcher}


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
