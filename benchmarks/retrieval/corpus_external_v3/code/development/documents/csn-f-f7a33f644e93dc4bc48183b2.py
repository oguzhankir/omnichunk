def set_timeout(self, timeout):
        
        timeout = int(timeout) # will raise on Error
        self._timeout = timeout == 0 and 999999 or timeout
