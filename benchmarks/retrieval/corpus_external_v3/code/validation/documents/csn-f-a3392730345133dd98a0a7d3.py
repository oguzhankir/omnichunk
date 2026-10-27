def pseudo_handler(self, signum, frame):
        
        self.log.warn("Received sigal {0} but system is already busy processing a previous signal, current frame: {1}".format(signum, str(frame)))
