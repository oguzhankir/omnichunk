def connection_url(self, name=None):
        
        return 'postgresql://{user}@{host}:{port}/{dbname}'.format(**{k: v for k, v in self._connect_options(name)})
