def get_historic_trades(self, start, end, granularity, product_id='BTC-USD'):
    
    params = {
      'start':self._format_iso_time(start),
      'end':self._format_iso_time(end),
      'granularity':granularity
    }
    return self._get('products', product_id, 'candles', params=params)
