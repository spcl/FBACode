from requests import get
from time import time

def max_repos(cfg):
    return int(cfg['max_repos'])

def pagination(cfg):
    return int(cfg['pagination'])

class GithubFetcher:

    def __init__(self, cfg, out_log, error_log):
        self.cfg = cfg
        self.out_log = out_log
        self.error_log = error_log

    def fetch(self, max_repos):

        #request_params = self.cfg['github.org']
        address = self.cfg['github.org']['address']
        request_params = {}
        request_params['sort'] = self.cfg['github.org']['sort']
        request_params['order'] = self.cfg['github.org']['ord']
        repos_per_page = pagination(request_params)
        page = 1
        if max_repos is None:
            max_repos = max_repos(request_params)
        repos_per_page = min(max_repos, repos_per_page)
        request_params['per_page'] = str(repos_per_page)

        repos_processed = 0
        results = []
        start = time()
        self.out_log.set_counter(max_repos)
        self.error_log.set_counter(max_repos)
        self.results = None

        while repos_processed < max_repos:
            request_params['page'] = str(page)
            results_c = self.fetch_json(address, request_params, 'C')
            results_cpp = self.fetch_json(address, request_params, 'Cpp')
            if results_c is None or results_cpp is None:
                self.error_log.error('Incorrect results, end work!')
                return
            elif results_c['incomplete_results'] or results_cpp['incomplete_results']:
                repos_per_page /= 2
                if repos_per_page < 1:
                    self.error_log.error('Couldnt fetch a single repository, end work!')
                    return
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

    def process_results(self, data):
        if self.results is None:
            return None
        processed_results = {}
        for repo in self.results:
            # dict https://stackoverflow.com/questions/3420122/filter-dict-to-contain-only-certain-keys
            data = { key : repo[key] for key in ('git_url', 'updated_at', 'name', 'default_branch') }
            processed_results[ repo['full_name'] ] = {'type' : 'git_repository', 'codebase_data' : data}

        if data is None:
            return processed_results
        else:
            return processed_results

    def update(self, existing_repo):
        pass

    def fetch_json(self, address, params, language):

        params['q'] = 'language:%s' % language
        r = get(address, params)
        if r.status_code != 200:
            self.error_log.error('Failed to fetch from GitHub, url %s, text %s', r.url, r.text)
            return None
        else:
            return r.json()

code_sources = { 'github.org' : GithubFetcher }

def fetch_projects(cfg, out_log, error_log, max_repos = None):

    data = None
    for name, src in code_sources.items():
        if not bool(cfg[name]['active']):
            out_log.info('Skip inactive code source: {0}'.format(name))
            continue
        fetcher = src(cfg, out_log, error_log)
        fetcher.fetch(max_repos)
        data = fetcher.process_results(data)
    return data


