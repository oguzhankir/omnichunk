def cli_command_quit(self, msg):
        
        if self.state == State.RUNNING and self.sprocess and self.sprocess.proc:
            self.sprocess.proc.kill()
        else:
            sys.exit(0)
