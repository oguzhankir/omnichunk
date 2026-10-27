def get_argument(self, name, default=_ARG_DEFAULT, strip=True):
        
        args = self.get_arguments(name, strip=strip)
        if not args:
            if default is self._ARG_DEFAULT:
                raise HTTPError(400, "Missing argument %s" % name)
            return default
        return args[-1]
