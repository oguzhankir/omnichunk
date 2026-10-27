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
