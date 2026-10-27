def get_ticker_metadata(self, ticker, fmt='json'):
        
        url = "tiingo/daily/{}".format(ticker)
        response = self._request('GET', url)
        data = response.json()
        if fmt == 'json':
            return data
        elif fmt == 'object':
            return dict_to_object(data, "Ticker")
