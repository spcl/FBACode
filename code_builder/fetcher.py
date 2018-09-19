from requests import get
from time import time

def fetch_json(address, params, language):

    params['q'] = 'language:%s' % language
    r = get(address, params)
    if r.status_code != 200:
        error_log.error('Failed to fetch from GitHub, url %s, text %s\n', r.url, r.text)
        return None
    else:
        return r.json()

class GithubFetcher:

    def __init__(self, cfg, out_log, error_log):
        self.cfg = cfg
        self.out_log = out_log
        self.error_log = error_log

    def fetch(self):

        request_params = self.cfg['github.org']
        address = request_params['address']
        del request_params['address']
        repos_per_page = int(self.cfg['fetch']['pagination'])
        request_params['per_page'] = str(repos_per_page)
        page = 1
        max_repos = int(self.cfg['fetch']['max_repos'])
        repos_processed = 0
        results = []
        start = time()
        while repos_processed < max_repos:
            request_params['page'] = str(page)
            results_c = fetch_json(address, request_params, 'C')
            results_cpp = fetch_json(address, request_params, 'Cpp')
            if results_c['incomplete_results'] or results_cpp['incomplete_results']:
                repos_per_page /= 2
                request_params['per_page'] = str(repos_per_page)
                continue
            repos_processed += repos_per_page
            results += results_c['items']
            results += results_cpp['items']
            page += 1
        end = time()
        self.out_log.info('Processed %d repositories in %f seconds\n' % (repos_processed, end-start))
        sorted_results = sorted(results, key = lambda x : x['stargazers_count'])

    def update(self, existing_repo):
        pass


