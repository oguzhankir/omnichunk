# -*- coding: utf-8 -*-

import os
import sys
import pkg_resources
import csv
import json
from collections import namedtuple
from zipfile import ZipFile
from tiingo.restclient import RestClient
import requests
import re

try:
    import pandas as pd
    pandas_is_installed = True
except ImportError:
    pandas_is_installed = False

VERSION = pkg_resources.get_distribution("tiingo").version


# These methods enable python 2 + 3 compatibility.
def get_zipfile_from_response(response):
    if sys.version_info < (3, 0):  # python 2
        from StringIO import StringIO as Buffer
    else:  # python 3
        from io import BytesIO as Buffer
    buffered = Buffer(response.content)
    return ZipFile(buffered)


def get_buffer_from_zipfile(zipfile, filename):
    if sys.version_info < (3, 0):  # python 2
        from StringIO import StringIO
        return StringIO(zipfile.read(filename))
    else:  # python 3
        # Source:
        # https://stackoverflow.com/questions/5627954/py3k-how-do-you-read-a-file-inside-a-zip-file-as-text-not-bytes
        from io import (TextIOWrapper, BytesIO)
        return TextIOWrapper(BytesIO(zipfile.read(filename)))


def dict_to_object(item, object_name):
    
    fields = item.keys()
    values = item.values()
    return json.loads(json.dumps(item),
                      object_hook=lambda d:
                      namedtuple(object_name, fields)(*values))

class InstallPandasException(Exception):
    pass


class APIColumnNameError(Exception):
    pass


class InvalidFrequencyError(Exception):
    pass


class TiingoClient(RestClient):
    

    def __init__(self, *args, **kwargs):
        super(TiingoClient, self).__init__(*args, **kwargs)
        self._base_url = "https://api.tiingo.com"

        try:
            api_key = self._config['api_key']
        except KeyError:
            api_key = os.environ.get('TIINGO_API_KEY')
        self._api_key = api_key

        if not(api_key):
            raise RuntimeError("Tiingo API Key not provided. Please provide"
                               " via environment variable or config argument.")

        self._headers = {
            'Authorization': "Token {}".format(api_key),
            'Content-Type': 'application/json',
            'User-Agent': 'tiingo-python-client {}'.format(VERSION)
        }

        self._frequency_pattern = re.compile('^[0-9]+(min|hour)$', re.IGNORECASE)

    def __repr__(self):
        return '<TiingoClient(url="{}")>'.format(self._base_url)

    def _is_eod_frequency(self,frequency):
        return frequency.lower() in ['daily', 'weekly', 'monthly', 'annually']

    # TICKER PRICE ENDPOINTS
    # https://api.tiingo.com/docs/tiingo/daily
    def list_tickers(self, assetType):
        
        listing_file_url = "https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip"
        response = requests.get(listing_file_url)
        zipdata = get_zipfile_from_response(response)
        raw_csv = get_buffer_from_zipfile(zipdata, 'supported_tickers.csv')
        reader = csv.DictReader(raw_csv)

        return [row for row in reader
                if row.get('assetType') == assetType]

    def list_stock_tickers(self):
        return self.list_tickers('Stock')

    def list_etf_tickers(self):
        return self.list_tickers('ETF')

    def list_fund_tickers(self):
        return self.list_tickers('Mutual Fund')

    def get_ticker_metadata(self, ticker, fmt='json'):
        
        url = "tiingo/daily/{}".format(ticker)
        response = self._request('GET', url)
        data = response.json()
        if fmt == 'json':
            return data
        elif fmt == 'object':
            return dict_to_object(data, "Ticker")

    def _invalid_frequency(self, frequency):
        
        is_valid = self._is_eod_frequency(frequency) or re.match(self._frequency_pattern, frequency)
        return not is_valid

    def _get_url(self, ticker, frequency):
        
        if self._invalid_frequency(frequency):
            etext = ("Error: {} is an invalid frequency.  Check Tiingo API documentation "
                     "for valid EOD or intraday frequency format.")
            raise InvalidFrequencyError(etext.format(frequency))
        else:
            if self._is_eod_frequency(frequency):
                return "tiingo/daily/{}/prices".format(ticker)
            else:
                return "iex/{}/prices".format(ticker)

    def get_ticker_price(self, ticker,
                         startDate=None, endDate=None,
                         fmt='json', frequency='daily'):
        
        url = self._get_url(ticker, frequency)
        params = {
            'format': fmt if fmt != "object" else 'json',  # conversion local
            'resampleFreq': frequency
        }

        if startDate:
            params['startDate'] = startDate
        if endDate:
            params['endDate'] = endDate

        # TODO: evaluate whether to stream CSV to cache on disk, or
        # load as array in memory, or just pass plain text
        response = self._request('GET', url, params=params)
        if fmt == "json":
            return response.json()
        elif fmt == "object":
            data = response.json()
            return [dict_to_object(item, "TickerPrice") for item in data]
        else:
            return response.content.decode("utf-8")

    def get_dataframe(self, tickers,
                      startDate=None, endDate=None, metric_name=None, frequency='daily'):

        

        valid_columns = ['open', 'high', 'low', 'close', 'volume', 'adjOpen', 'adjHigh', 'adjLow',
                         'adjClose', 'adjVolume', 'divCash', 'splitFactor']

        if metric_name is not None and metric_name not in valid_columns:
            raise APIColumnNameError('Valid data items are: ' + str(valid_columns))

        params = {
            'format': 'json',
            'resampleFreq': frequency
        }
        if startDate:
            params['startDate'] = startDate
        if endDate:
            params['endDate'] = endDate

        if pandas_is_installed:
            if type(tickers) is str:
                stock = tickers
                url = self._get_url(stock, frequency)
                response = self._request('GET', url, params=params)
                df = pd.DataFrame(response.json())
                if metric_name is not None:
                    prices = df[metric_name]
                    prices.index = df['date']
                else:
                    prices = df
                    prices.index = df['date']
                    del (prices['date'])
            else:
                prices = pd.DataFrame()
                for stock in tickers:
                    url = self._get_url(stock, frequency)
                    response = self._request('GET', url, params=params)
                    df = pd.DataFrame(response.json())
                    df.index = df['date']
                    df.rename(index=str, columns={metric_name: stock}, inplace=True)
                    prices = pd.concat([prices, df[stock]], axis=1)
            prices.index = pd.to_datetime(prices.index)
            return prices
        else:
            error_message = ("Pandas is not installed, but .get_ticker_price() was "
                             "called with fmt=pandas.  In order to install tiingo with "
                             "pandas, reinstall with pandas as an optional dependency. \n"
                             "Install tiingo with pandas dependency: \'pip install tiingo[pandas]\'\n"
                             "Alternatively, just install pandas: pip install pandas.")
            raise InstallPandasException(error_message)

    # NEWS FEEDS
    # tiingo/news
    def get_news(self, tickers=[], tags=[], sources=[], startDate=None,
                 endDate=None, limit=100, offset=0, sortBy="publishedDate",
                 fmt='json'):
        
        url = "tiingo/news"
        params = {
            'limit': limit,
            'offset': offset,
            'sortBy': sortBy,
            'tickers': tickers,
            'sources': sources,
            'tags': tags,
            'startDate': startDate,
            'endDate': endDate
        }
        response = self._request('GET', url, params=params)
        data = response.json()
        if fmt == 'json':
            return data
        elif fmt == 'object':
            return [dict_to_object(item, "NewsArticle") for item in data]

    def get_bulk_news(self, file_id=None, fmt='json'):
        
        if file_id:
            url = "tiingo/news/bulk_download/{}".format(file_id)
        else:
            url = "tiingo/news/bulk_download"

        response = self._request('GET', url)
        data = response.json()
        if fmt == 'json':
            return data
        elif fmt == 'object':
            return dict_to_object(data, "BulkNews")
