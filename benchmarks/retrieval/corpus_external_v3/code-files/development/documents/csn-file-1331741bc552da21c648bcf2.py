
from requests import get

from cbexchange.client import RESTClient, PaginationClient

# Levels for Get Product Order Book
LEVEL_BEST = 1
LEVEL_TOP  = 2
LEVEL_FULL = 3


class MarketClient(RESTClient):
  def _request(self, method, *relative_path_parts, **kwargs):
    
    uri = self._create_api_uri(*relative_path_parts)
    response = get(uri, params=kwargs.get('params', None))
    return self._handle_response(response).json()

  def get_products(self):
    
    return self._get('products')

  def get_product_order_book(self, level=None, product_id='BTC-USD'):
    
    return self._get('products', product_id, 'book', params={'level':level})

  def get_product_ticker(self, product_id='BTC-USD'):
    
    return self._get('products', product_id, 'ticker')

  def get_trades(self, product_id='BTC-USD'):
    
    return self._get('products', product_id, 'trades')

  def get_historic_trades(self, start, end, granularity, product_id='BTC-USD'):
    
    params = {
      'start':self._format_iso_time(start),
      'end':self._format_iso_time(end),
      'granularity':granularity
    }
    return self._get('products', product_id, 'candles', params=params)

  def get_stats(self, product_id='BTC-USD'):
    
    return self._get('products', product_id, 'stats')

  def get_currencies(self):
    
    return self._get('currencies')

  def get_time(self):
    
    return self._get('time')

class MarketPaginationClient(PaginationClient):
  def _request(self, method, *relative_path_parts, **kwargs):
    
    uri = self._create_api_uri(*relative_path_parts)
    response = get(uri, params=self._get_params(**kwargs))
    self.is_initial = False
    self.before_cursor = response.headers.get('cb-before', None)
    self.after_cursor = response.headers.get('cb-after', None)
    return self._handle_response(response).json()

class GetTradesPagination(MarketPaginationClient):
  
  def __init__(self,
               product_id='BTC-USD',
               api_uri=None,
               before=True,
               limit=None,
               cursor=None):
    super(GetTradesPagination, self).__init__(api_uri, before, limit, cursor)
    self.product_id = product_id

  def endpoint(self):
    if self._check_next():
      return self._get('products', self.product_id, 'trades')
    else:
      return None
