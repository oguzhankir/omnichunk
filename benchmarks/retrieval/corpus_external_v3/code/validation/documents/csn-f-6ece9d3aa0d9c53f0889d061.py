def status(self, signum):
        
        self.log.debug('Signal handler got status signal')
        new_status_callbacks = []
        for status_call in self.status_callbacks:
            # If callback is non persistent we remove it
            try:
                self.log.debug("Calling {0}({1},{2})".format(status_call['function'].__name__, status_call['args'], status_call['kwargs']))
            except AttributeError:
                self.log.debug("Calling unbound function/method {0}".format(str(status_call)))

            apply(status_call['function'], status_call['args'], status_call['kwargs'])
            if status_call['persistent']:
                new_status_callbacks.append(status_call)
        self.status_callbacks = new_status_callbacks
        self._resume(signum)
