
from json import dumps, loads
from threading import Lock, Thread
from time import sleep

from websocket import create_connection

from cbexchange.client import APIClient


class WSClient(APIClient):
  
  WS_URI = 'wss://ws-feed.exchange.coinbase.com'
  WS_TYPE = 'subscribe'
  WS_PRODUCT_ID = 'BTC-USD'

  def __init__(self, ws_uri=None, ws_type=None, ws_product_id=None):
    self.WS_URI = ws_uri or self.WS_URI
    self.WS_TYPE = ws_type or self.WS_TYPE
    self.WS_PRODUCT_ID = ws_product_id or self.WS_PRODUCT_ID
    self._ws = None
    self._thread = None
    self._lock = Lock()

  def __iter__(self):
    return self

  def __enter__(self):
    self.connect()
    return self

  def __exit__(self, type, value, traceback):
    self.disconnect()

  def __next__(self):
    
    next = self.receive()
    if next:
      return next
    raise StopIteration

  # Iterator function for Python 2.
  next = __next__

  def _format_message(self, message):
    
    return loads(message)

  def _keep_alive_thread(self):
    
    while True:
      with self._lock:
        if self.connected():
          self._ws.ping()
        else:
          self.disconnect()
          self._thread = None
          return
      sleep(30)

  def connect(self):
    
    if not self.connected():
      self._ws = create_connection(self.WS_URI)
      message = {
        'type':self.WS_TYPE,
        'product_id':self.WS_PRODUCT_ID
      }
      self._ws.send(dumps(message))

      # There will be only one keep alive thread per client instance
      with self._lock:
        if not self._thread:
          thread = Thread(target=self._keep_alive_thread, args=[])
          thread.start()

  def disconnect(self):
    
    if self.connected():
      self._ws.close()
      self._ws = None

  def receive(self):
    
    if self.connected():
      return self._format_message(self._ws.recv())
    return None

  def connected(self):
    
    if self._ws:
      return self._ws.connected
    return False
