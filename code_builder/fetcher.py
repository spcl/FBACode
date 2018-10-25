from requests import get
from time import time

def fetch_projects(cfg, out_log, error_log, max_repos = None):

    github = GithubFetcher(cfg, out_log, error_log)
    github.fetch(max_repos)
    data = github.process_results()
    return data

def fetch_json(address, params, language):

    params['q'] = 'language:%s' % language
    r = get(address, params)
    if r.status_code != 200:
        error_log.error('Failed to fetch from GitHub, url %s, text %s', r.url, r.text)
        return None
    else:
        return r.json()

class GithubFetcher:

    def __init__(self, cfg, out_log, error_log):
        self.cfg = cfg
        self.out_log = out_log
        self.error_log = error_log

    def fetch(self, max_repos):

        request_params = self.cfg['github.org']
        address = request_params['address']
        del request_params['address']
        repos_per_page = int(self.cfg['fetch']['pagination'])
        page = 1
        if max_repos is None:
            max_repos = int(self.cfg['fetch']['max_repos'])
        repos_per_page = min(max_repos, repos_per_page)
        request_params['per_page'] = str(repos_per_page)

        repos_processed = 0
        results = []
        start = time()
        self.out_log.set_counter(max_repos)
        self.error_log.set_counter(max_repos)
        
        while repos_processed < max_repos:
            request_params['page'] = str(page)
            results_c = fetch_json(address, request_params, 'C')
            results_cpp = fetch_json(address, request_params, 'Cpp')
            if results_c['incomplete_results'] or results_cpp['incomplete_results']:
                repos_per_page /= 2
                request_params['per_page'] = str(repos_per_page)
                self.error_log.error('Incomplete results at GitHub API for %d repositories, start again with %d'
                        % (repos_per_page*2, repos_per_page))
                continue
            repos_processed += repos_per_page
            results += results_c['items']
            results += results_cpp['items']
            self.out_log.step(repos_per_page)
            self.error_log.step(repos_per_page)
            self.out_log.info('Fetched %d repositories for C and C++ with GitHub API' % repos_per_page)
            page += 1

        end = time()
        self.out_log.info('Processed %d repositories in %f seconds' % (repos_processed, end-start))
        # Mix C and C++ projects and sort them together
        reversed_order = request_params['order'] == 'desc'
        sort_key = request_params['sort']
        self.results = sorted(results, key = lambda x : x[sort_key], reverse = reversed_order)

    def process_results(self):
       
        processed_results = {}
        for repo in self.results:
            # dict https://stackoverflow.com/questions/3420122/filter-dict-to-contain-only-certain-keys
            data = { key : repo[key] for key in ('git_url', 'updated_at', 'name', 'default_branch') }
            processed_results[ repo['full_name'] ] = {'type' : 'git_repository', 'codebase_data' : data}

        return processed_results

    def update(self, existing_repo):
        pass


