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
