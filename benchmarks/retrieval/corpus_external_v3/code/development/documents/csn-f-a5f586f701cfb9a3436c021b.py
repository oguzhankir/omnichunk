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
