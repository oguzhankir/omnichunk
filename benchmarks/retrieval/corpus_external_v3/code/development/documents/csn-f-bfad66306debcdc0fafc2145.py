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
