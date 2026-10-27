def sigterm_handler(self, signum, frame):
        
        assert(self.state in ('WAITING', 'RUNNING', 'PAUSED'))
        logger.debug("our state %s", self.state)
        if self.state == 'WAITING':
            return self.ioloop.stop()

        if self.state == 'RUNNING':
            logger.debug('already running sending signal to child - %s',
                         self.sprocess.pid)
            os.kill(self.sprocess.pid, signum)
        self.ioloop.stop()
