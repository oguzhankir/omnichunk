
from builtins import map
from datetime import datetime

from requests.compat import urljoin, quote

from cbexchange.error import get_api_error


class APIClient(object):
  pass

class RESTClient(APIClient):
  
  API_URI = 'https://api.exchange.coinbase.com'

  def __init__(self, api_uri=None):
    self.API_URI = api_uri or self.API_URI

  def _create_api_uri(self, *parts):
    
    return urljoin(self.API_URI, '/'.join(map(quote, parts)))
  
  def _format_iso_time(self, time):
    
    if isinstance(time, str):
      return time
    elif isinstance(time, datetime):
      return time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    else:
      return None

  def _handle_response(self, response):
    
    if not str(response.status_code).startswith('2'):
      raise get_api_error(response)
    return response

  def _request(self, method, *relative_path_parts, **kwargs):
    
    raise NotImplementedError

  def _get(self, *args, **kwargs):
    
    return self._request('get', *args, **kwargs)

  def _post(self, *args, **kwargs):
    
    return self._request('post', *args, **kwargs)

  def _delete(self, *args, **kwargs):
    
    return self._request('post', *args, **kwargs)

class PaginationClient(RESTClient):
  
  def __init__(self, api_uri=None, before=True, limit=None, cursor=None):
    super(PaginationClient, self).__init__(api_uri)
    self.before = before
    self.limit = limit
    self.before_cursor = None
    self.after_cursor = None
    if cursor:
      self.is_initial = False
      if before:
        self.before_cursor = cursor
      else:
        self.after_cursor = cursor
    else:
      self.is_initial = True

  def __iter__(self):
    return self

  def __next__(self):
    
    next = self.endpoint()
    if next is not None:
      return next
    raise StopIteration

  # Iterator function for Python 2.
  next = __next__

  def _get_params(self, **kwargs):
    params = kwargs.get('params', {})
    params['limit'] = self.limit
    if not self.is_initial:
      if self.before:
        params['before'] = self.before_cursor
      else:
        params['after'] = self.after_cursor
    return params

  def _check_next(self):
    
    if self.is_initial:
      return True
    if self.before:
      if self.before_cursor:
        return True
      else:
        return False
    else:
      if self.after_cursor:
        return True
      else:
        return False

  def is_before(self):
    
    return self.before

  def is_after(self):
    
    return not self.before

  def set_before(self):
    
    self.before = True

  def set_after(self):
    
    self.before = False

  def endpoint(self):
    
    raise NotImplementedError

  def get_before_cursor(self):
    
    return self.before_cursor

  def get_after_cursor(self):
    
    return self.after_cursor
