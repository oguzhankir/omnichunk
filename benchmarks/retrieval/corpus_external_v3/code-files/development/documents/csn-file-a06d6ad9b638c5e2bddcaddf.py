# -----------------------------------------------------------------------------
# Adapted from Microsoft OSS
# see https://github.com/Microsoft/service-fabric-cli
# -----------------------------------------------------------------------------



import adal
from msrest.authentication import Authentication

# pylint: disable=too-few-public-methods
class ClientCertAuthentication(Authentication):
    

    def __init__(self, cert=None, ca_cert=None, no_verify=False):
        self.cert = cert
        self.ca_cert = ca_cert
        self.no_verify = no_verify

    def signed_session(self, session=None):
        

        if session:
            session = super(ClientCertAuthentication, self).signed_session(session)
        else:
            session = super(ClientCertAuthentication, self).signed_session()

        if self.cert is not None:
            session.cert = self.cert
        if self.ca_cert is not None:
            session.verify = self.ca_cert
        if self.no_verify:
            session.verify = False

        return session

class AdalAuthentication(Authentication):
    

    def __init__(self, no_verify=False):
        self.no_verify = no_verify

    def signed_session(self, session=None):
        

        from sfctl.config import (aad_metadata, aad_cache)

        if session:
            session = super(AdalAuthentication, self).signed_session(session)
        else:
            session = super(AdalAuthentication, self).signed_session()

        if self.no_verify:
            session.verify = False

        authority_uri, cluster_id, client_id = aad_metadata()
        existing_token, existing_cache = aad_cache()
        context = adal.AuthenticationContext(authority_uri,
                                             cache=existing_cache)
        new_token = context.acquire_token(cluster_id,
                                          existing_token['userId'], client_id)
        header = "{} {}".format("Bearer", new_token['accessToken'])
        session.headers['Authorization'] = header
        return session
