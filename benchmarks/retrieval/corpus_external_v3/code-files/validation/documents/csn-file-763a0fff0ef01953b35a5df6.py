# -*- coding: utf-8 -*-

import logging
import requests
from requests.exceptions import HTTPError


# TODO: Possibly print HTTP json response if available?
class RestClientError(Exception):
    
    pass


class RestClient(object):

    def __init__(self, config={}):
        
        self._config = config

        # The child class should override these properties or else the
        # restclient won't work. Reevalute whether to do this as an abstract
        # base class so it doesn't get used by itself.
        self._headers = {}
        self._base_url = ""

        if config.get('session'):
            self._session = requests.Session()
        else:
            self._session = requests

    def __repr__(self):
        return '<RestClient(url="{}")>'.format(self._base_url)

    def _request(self, method, url, **kwargs):
        
        resp = self._session.request(method,
                                     '{}/{}'.format(self._base_url, url),
                                     headers=self._headers,
                                     **kwargs)

        try:
            resp.raise_for_status()
        except HTTPError as e:
            logging.error(resp.content)
            raise RestClientError(e)

        return resp
