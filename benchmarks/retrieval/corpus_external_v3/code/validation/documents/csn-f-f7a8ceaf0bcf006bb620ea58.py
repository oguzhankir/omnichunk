def cli_command_pause(self, msg):
        
        info = ''
        if self.state == State.RUNNING and self.sprocess and self.sprocess.proc:
            self.sprocess.set_exit_callback(self.proc_exit_cb_noop)
            self.sprocess.proc.kill()
            info = 'killed'
            # TODO: check if process is really dead etc.
        self.state = State.PAUSED
        return info
