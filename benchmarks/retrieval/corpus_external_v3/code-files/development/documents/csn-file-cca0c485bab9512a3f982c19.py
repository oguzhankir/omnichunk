

import os
import requests
try:
    import simplejson as json
    JSON_ERROR = json.JSONDecodeError
except ImportError:
    JSON_ERROR = Exception

API_VERSION = 'v2'
API_URL = 'https://api.digitalocean.com'


"""
TODO: refactor for multipage results
TODO: unit tests for Images, ImageActions, and DomainRecords
"""

class APIError(Exception):
    

    def __init__(self, message, status_code, **kwargs):
        super(APIError, self).__init__(message)
        self.status_code = status_code
        for k, v in kwargs.iteritems():
            setattr(self, k, v)



class RestAPI(object):
    

    def send_request(self, kind, resource, url_components, **kwargs):
        
        url = self.format_request_url(resource, *url_components)
        meth = getattr(requests, kind)
        headers = self.get_request_headers()
        req_data = self.format_parameters(**kwargs)
        response = meth(url, headers=headers, data=req_data)
        data = self.get_response(response)
        if response.status_code >= 300:
            msg = data.pop('message', 'API request returned error')
            raise APIError(msg, response.status_code, **data)
        return data

    def get_response(self, resp):
        
        try:
            return resp.json()
        except JSON_ERROR:
            return {}

    def get_request_headers(self):
        raise NotImplementedError()

    def format_request_url(self, resource, *args):
        raise NotImplementedError()

    def format_parameters(self, **kwargs):
        
        req_data = {}
        for k, v in kwargs.items():
            if isinstance(v, (list, tuple)):
                k = k + '[]'
            req_data[k] = v
        return req_data



class DigitalOceanAPI(RestAPI):
    

    def __init__(self, api_key=None, api_url=API_URL, api_version=API_VERSION):
        
        if api_key is None:
            api_key = os.environ.get('DIGITALOCEAN_API_KEY', None)
        if api_key is None:
            raise ValueError("API key was not found nor supplied")
        self.api_key = api_key
        self.api_url = api_url
        self.api_version = api_version

    def get_request_headers(self):
        
        header = {}
        header['Authorization'] = 'Bearer %s' % self.api_key
        return header

    def format_request_url(self, resource, *args):
        
        return '/'.join((self.api_url, self.api_version, resource) +
                        tuple(str(x) for x in args))



class Resource(object):
    

    resource_path = None

    def __init__(self, api):
        
        self.api = api

    def send_request(self, kind, url_components, **kwargs):
        
        return self.api.send_request(kind, self.resource_path, url_components,
                                     **kwargs)

    def get(self, url_components=(), **kwargs):
        
        return self.send_request('get', url_components, **kwargs)

    def delete(self, url_components=(), **kwargs):
        
        return self.send_request('delete', url_components, **kwargs)

    def put(self, url_components=(), **kwargs):
        
        return self.send_request('put', url_components, **kwargs)

    def post(self, url_components=(), **kwargs):
        
        return self.send_request('post', url_components, **kwargs)

    def head(self, url_components=(), **kwargs):
        
        return self.send_request('head', url_components, **kwargs)



class ResourceCollection(Resource):
    

    def list(self, url_components=()):
        
        resp = self.get(url_components)
        return resp.get(self.result_key, [])

    @property
    def result_key(self):
        
        return self.resource_path

    @property
    def singular(self):
        
        return self.result_key[:-1]



class MutableCollection(ResourceCollection):
    

    def delete(self, id):
        return super(MutableCollection, self).delete((id,))

    def update(self, id, **kwargs):
        return self.put((id,), **kwargs)

    def list(self, url_components=()):
        resp = super(MutableCollection, self).get(url_components)
        return resp.get(self.result_key, [])

    def get(self, id, **kwargs):
        
        return (super(MutableCollection, self).get((id,), **kwargs)
                .get(self.singular, None))



class ImageActions(Resource):
    

    def __init__(self, api, id, **kwargs):
        super(ImageActions, self).__init__(api)
        self.id = id
        for k, v in kwargs.iteritems():
            setattr(self, k, v)

    def transfer(self, region):
        
        action = self.post(type='transfer', region=region)['action']
        return self.parent.get(action['resource_id'])

    @property
    def resource_path(self):
        return 'images/%s/actions' % self.id



# ----------------------------------------------------------------------
# Mutable collections
# ----------------------------------------------------------------------

class Images(MutableCollection):
    
    resource_path = 'images'

    def get(self, id):
        
        info = super(Images, self).get(id)
        return ImageActions(self.api, parent=self, **info)



class Keys(MutableCollection):
    

    resource_path = 'account/keys'

    @property
    def result_key(self):
        return 'ssh_keys'

    def update(self, id, name):
        
        return super(Keys, self).update(id, name=name)

    def create(self, name, public_key):
        return (self.post(name=name, public_key=public_key)
                .get(self.singular, None))



class Domains(MutableCollection):
    

    resource_path = 'domains'

    def create(self, name, ip_address):
        
        return (self.post(name=name, ip_address=ip_address)
                .get(self.singular, None))

    def records(self, name):
        
        if self.get(name):
            return DomainRecords(self.api, name)

    def update(self, id, **kwargs):
        
        raise NotImplementedError()



class DomainRecords(MutableCollection):
    

    def __init__(self, api, domain):
        self.api = api
        self.domain = domain

    @property
    def resource_path(self):
        return 'domains/%s/records' % self.domain

    @property
    def singular(self):
        return 'domain_record'

    def rename(self, id, name):
        
        return super(DomainRecords, self).update(id, name=name)[self.singular]

    def create(self, type, name=None, data=None, priority=None,
               port=None, weight=None):
        
        if type == 'A' and name is None:
            name = self.domain
        return self.post(type=type, name=name, data=data, priority=priority,
                         port=port, weight=weight)[self.singular]

    def get(self, id, **kwargs):
        
        return super(DomainRecords, self).get(id, **kwargs)



# ----------------------------------------------------------------------
# Immutable collections
# ----------------------------------------------------------------------

class Regions(ResourceCollection):
    
    resource_path = 'regions'



class Sizes(ResourceCollection):
    
    resource_path = 'sizes'



class Actions(ResourceCollection):
    
    resource_path = 'actions'

    def list(self, url_components=()):
        resp = super(Actions, self).get(url_components)
        return resp.get(self.result_key)

    def get(self, id, **kwargs):
        return (super(Actions, self).get((id,), **kwargs)
                .get(self.singular, None))
