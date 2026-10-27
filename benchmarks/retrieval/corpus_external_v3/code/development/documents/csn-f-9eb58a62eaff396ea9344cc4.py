def restore(self, name, filename):
        
        if not self.exists(name):
            self.create(name)
        else:
            log.warn('overwriting contents of database %s' % name)
        log.info('restoring %s from %s' % (name, filename))
        self._run_cmd('pg_restore', '--verbose', '--dbname=%s' % name, filename)
