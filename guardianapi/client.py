try:
    import simplejson
except ImportError:
    from django.utils import simplejson
import urllib, urlparse, time
import fetchers

class APIKeyError(Exception):
    def __init__(self, api_key, e):
        self.api_key = api_key
        self.wrapped_exception = e
    
    def __repr__(self):
        return '<APIKeyError: %s is a bad API key>' % self.api_key

class Client(object):
    base_url = 'http://api.guardianapis.com/'
    
    def __init__(self, api_key, fetcher=None):
        self.api_key = api_key
        self.fetcher = fetcher or fetchers.best_fetcher()
    
    def _do_call(self, endpoint, **kwargs):
        url = '%s?%s' % (
            urlparse.urljoin(self.base_url, endpoint),
            urllib.urlencode(self.fix_kwargs(kwargs), doseq=True)
        )
        try:
            headers, response = self.fetcher.get(url)
        except fetchers.HTTPError, e:
            if e.code == 403:
                raise APIKeyError(self.api_key, e)
            else:
                raise
        return simplejson.loads(response)
    
    def fix_kwargs(self, kwargs):
        kwargs2 = dict([ # underscores become hyphens
            (key.replace('_', '-'), value)
            for key, value in kwargs.items()
        ])
        kwargs2['format'] = 'json'
        kwargs2['api_key'] = self.api_key
        return kwargs2
    
    def search(self, **kwargs):
        json = self._do_call('/content/search', **kwargs)
        return SearchResults(self, kwargs, json)
    
    def tags(self, **kwargs):
        json = self._do_call('/content/all-subjects', **kwargs)
        return TagResults(self, kwargs, json)
    
    def content(self, content_id):
        json = self._do_call('/content/content/%s' % content_id)
        return json
    
class Results(object):
    client_method = None
    default_per_page = 10 # Client library currently needs to know this
    
    def __init__(self, client, kwargs, json):
        self.client = client
        self.kwargs = kwargs
        self.json = json
    
    def all(self, sleep=1):
        "Iterate over all results, handling pagination transparently"
        return AllResults(self, sleep)
    
    def count(self):
        return 0
    
    def start_index(self):
        return 0
    
    def __getitem__(self, key):
        return self.json[key]
    
    def results(self):
        return []
    
    def has_next(self):
        max_index = self.count() - 1
        max_in_current = self.start_index() + len(self.results())
        return max_in_current < max_index
    
    def next(self):
        "Return next Results object in pagination sequence, or None if at end"
        if not self.has_next():
            return None
        method = getattr(self.client, self.client_method)
        kwargs = dict(self.kwargs)
        start_index = kwargs.get('start_index', 0)
        count = kwargs.get('count', self.default_per_page)
        # Adjust the pagination arguments
        kwargs['count'] = count
        kwargs['start_index'] = start_index + count
        return method(**kwargs)
    
    def __iter__(self):
        for result in self.results():
            yield result

class SearchResults(Results):
    client_method = 'search'
    default_per_page = 10
    
    def count(self):
        return self.json['search']['count']
    
    def start_index(self):
        return self.json['search']['startIndex']
    
    def results(self):
        return self.json['search']['results']
    
    def filters(self):
        return self.json['search']['filters']

class TagResults(Results):
    client_method = 'tags'
    default_per_page = 10
    
    def count(self):
        return self.json['com.gu.gdn.api.model.TagList']['count']
    
    def start_index(self):
        return self.json['com.gu.gdn.api.model.TagList']['startIndex']
    
    def results(self):
        return self.json['com.gu.gdn.api.model.TagList']['tags']

class AllResults(object):
    "Results wrapper that knows how to auto-paginate a result set"
    def __init__(self, results, sleep=1):
        self.results = results
        self.sleep = sleep
    
    def __iter__(self):
        results = self.results
        while results:
            for result in results.results():
                yield result
            time.sleep(self.sleep)
            results = results.next()
