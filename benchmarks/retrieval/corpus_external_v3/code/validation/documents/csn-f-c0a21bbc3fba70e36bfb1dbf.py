def authorize_redirect(self, oauth_scope, callback_uri=None,
                           ax_attrs=["name","email","language","username"]):
        
        callback_uri = callback_uri or self.request.uri
        args = self._openid_args(callback_uri, ax_attrs=ax_attrs,
                                 oauth_scope=oauth_scope)
        self.redirect(self._OPENID_ENDPOINT + "?" + urllib.urlencode(args))
