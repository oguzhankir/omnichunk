
from base64 import b64decode, b64encode
from hashlib import sha256
from hmac import new
from time import time

from requests import delete, get, post
from requests.auth import AuthBase

from cbexchange.client import RESTClient, PaginationClient

# List Orders Status
STATUS_ALL     = 'all'
STATUS_OPEN    = 'open'
STATUS_PENDING = 'pending'


class CoinbaseExchangeAuth(AuthBase):
  
  def __init__(self, api_key, secret_key, passphrase):
    self.api_key = api_key
    self.secret_key = secret_key
    self.passphrase = passphrase

  def __call__(self, request):
    timestamp = str(time())
    msg = timestamp + request.method + request.path_url + (request.body or '')

    signature = new(b64decode(self.secret_key),
                    msg=msg.encode(),
                    digestmod=sha256).digest()

    signature_b64 = b64encode(signature)

    request.headers.update({
      'CB-ACCESS-SIGN':signature_b64,
      'CB-ACCESS-TIMESTAMP':timestamp,
      'CB-ACCESS-KEY':self.api_key,
      'CB-ACCESS-PASSPHRASE':self.passphrase,
      'Content-Type':'application/json'
    })

    return request

class PrivateClient(RESTClient):
  
  def __init__(self, auth, api_uri=None):
    super(PrivateClient, self).__init__(api_uri)
    self.auth = auth

  def _request(self, method, *relative_path_parts, **kwargs):
    
    uri = self._create_api_uri(*relative_path_parts)
    if method == 'get':
      response = get(uri, auth=self.auth, params=kwargs.get('params', None))
    elif method == 'post':
      response = post(uri, auth=self.auth, json=kwargs.get('data', None))
    else:
      response = delete(uri, auth=self.auth, json=kwargs.get('data', None))
    return self._handle_response(response).json()

  def list_accounts(self):
    
    return self._get('accounts')

  def get_account(self, account_id):
    
    return self._get('accounts', account_id)

  def get_account_history(self, account_id):
    
    return self._get('accounts', account_id, 'ledger')

  def get_holds(self, account_id):
    
    return self._get('accounts', account_id, 'holds')

  def _place_order(self,
                   side,
                   product_id='BTC-USD',
                   client_oid=None,
                   type=None,
                   stp=None,
                   price=None,
                   size=None,
                   funds=None,
                   time_in_force=None,
                   cancel_after=None,
                   post_only=None):
    
    data = {
      'side':side,
      'product_id':product_id,
      'client_oid':client_oid,
      'type':type,
      'stp':stp,
      'price':price,
      'size':size,
      'funds':funds,
      'time_in_force':time_in_force,
      'cancel_after':cancel_after,
      'post_only':post_only
    }
    return self._post('orders', data=data)

  def place_limit_order(self,
                        side,
                        price,
                        size,
                        product_id='BTC-USD',
                        client_oid=None,
                        stp=None,
                        time_in_force=None,
                        cancel_after=None,
                        post_only=None):
    
    return self._place_order(side,
                             product_id=product_id,
                             client_oid=client_oid,
                             type='limit',
                             stp=stp,
                             price=price,
                             size=size,
                             time_in_force=time_in_force,
                             cancel_after=cancel_after,
                             post_only=post_only)

  def place_market_order(self,
                         side,
                         product_id='BTC-USD',
                         size=None,
                         funds=None,
                         client_oid=None,
                         stp=None):
    
    return self._place_order(type='market',
                             side=size,
                             product_id=product_id,
                             size=size,
                             funds=funds,
                             client_oid=client_oid,
                             stp=stp)

  def cancel_order(self, order_id):
    
    return self._delete('orders', order_id)

  def cancel_all(self, product_id=None):
    
    return self._delete('orders', data={'product_id':product_id})

  def list_orders(self, status=None):
    
    return self._get('orders', params={'status':status})

  def get_order(self, order_id):
    
    return self._get('orders', order_id)

  def list_fills(self):
    
    return self._get('fills')

  def _deposit_withdraw(self, type, amount, coinbase_account_id):
    
    data = {
      'type':type,
      'amount':amount,
      'coinbase_account_id':coinbase_account_id
    }
    return self._post('transfers', data=data)

  def deposit(self, amount, coinbase_account_id):
    
    return self._deposit_withdraw('deposit', amount, coinbase_account_id)

  def withdraw(self, amount, coinbase_account_id):
    
    return self._deposit_withdraw('withdraw', amount, coinbase_account_id)

  def _new_report(self,
                  type,
                  start_date,
                  end_date,
                  product_id='BTC-USD',
                  account_id=None,
                  format=None,
                  email=None):
    
    data = {
      'type':type,
      'start_date':self._format_iso_time(start_date),
      'end_date':self._format_iso_time(end_date),
      'product_id':product_id,
      'account_id':account_id,
      'format':format,
      'email':email
    }
    return self._post('reports', data=data)

  def new_fills_report(self,
                       start_date,
                       end_date,
                       account_id=None,
                       product_id='BTC-USD',
                       format=None,
                       email=None):
    
    return self._new_report(start_date,
                            'fills',
                            end_date,
                            account_id,
                            product_id,
                            format,
                            email)

  def new_accounts_report(self,
                          start_date,
                          end_date,
                          account_id,
                          product_id='BTC-USD',
                          format=None,
                          email=None):
    
    return self._new_report(start_date,
                            'account',
                            end_date,
                            product_id,
                            account_id,
                            format,
                            email)

  def get_report_status(self, report_id):
    
    return self._get('reports', report_id)

class PrivatePaginationClient(PaginationClient):
  def __init__(self, auth, api_uri=None, before=True, limit=None, cursor=None):
    super(PrivatePaginationClient, self).__init__(api_uri,
                                                  before,
                                                  limit,
                                                  cursor)
    self.auth = auth

  def _request(self, method, *relative_path_parts, **kwargs):
    
    uri = self._create_api_uri(*relative_path_parts)
    if method == 'get':
      response = get(uri, auth=self.auth, params=kwargs.get('params', None))
    elif method == 'post':
      response = post(uri, auth=self.auth, json=kwargs.get('data', None))
    else:
      response = delete(uri, auth=self.auth, json=kwargs.get('data', None))
    self.is_initial = False
    self.before_cursor = response.headers.get('cb-before', None)
    self.after_cursor = response.headers.get('cb-after', None)
    return self._handle_response(response).json()

class ListAccountsPagination(PrivatePaginationClient):
  
  def endpoint(self):
    if self._check_next():
      return self._get('accounts')
    else:
      return None

class AccountPagination(PrivatePaginationClient):
  def __init__(self,
               account_id,
               auth,
               api_uri=None,
               before=True,
               limit=None,
               cursor=None):
    super(AccountPagination, self).__init__(auth,
                                            api_uri,
                                            before,
                                            limit,
                                            cursor)
    self.account_id = account_id

class GetAccountHistoryPagination(AccountPagination):
  
  def endpoint(self):
    if self._check_next():
      return self._get('accounts', self.account_id, 'ledger')
    else:
      return None

class GetHoldsPagination(AccountPagination):
  
  def endpoint(self):
    if self._check_next():
      return self._get('accounts', self.account_id, 'holds')
    else:
      return None

class ListFillsPagination(PrivatePaginationClient):
  
  def endpoint(self):
    if self._check_next():
      return self._get('fills')
    else:
      return None

class CancelAllPagination(PrivatePaginationClient):
  
  def __init__(self,
               product_id,
               auth,
               api_uri=None,
               before=True,
               limit=None,
               cursor=None):
    super(AccountPagination, self).__init__(auth,
                                            api_uri,
                                            before,
                                            limit,
                                            cursor)
    self.product_id = product_id

  def endpoint(self):
    if self._check_next():
      return self._delete('orders', data={'product_id':self.product_id})
    else:
      return None

class ListOrdersPagination(PrivatePaginationClient):
  
  def __init__(self,
               auth,
               status=None,
               api_uri=None,
               before=True,
               limit=None,
               cursor=None):
    super(ListOrdersPagination, self).__init__(auth,
                                               api_uri,
                                               before,
                                               limit,
                                               cursor)
    self.status = status

  def endpoint(self):
    if self._check_next():
      return self._get('orders', params={'status':self.status})
    else:
      return None
