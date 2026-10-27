

__all__ = ('purge_key', 'FastlyError')

import logging
import requests

from .exceptions import ConveyorError


def purge_key(surrogate_key, service_id, api_key):
    
    logger = logging.getLogger(__name__)

    api_root = 'https://api.fastly.com'
    path = '/service/{service}/purge/{surrogate_key}'.format(
        service=service_id,
        surrogate_key=surrogate_key)
    logger.info('Fastly purge {0}'.format(path))
    r = requests.post(api_root + path,
                      headers={'Fastly-Key': api_key,
                               'Accept': 'application/json'})
    if r.status_code != 200:
        raise FastlyError(r.json)


class FastlyError(ConveyorError):
    pass
