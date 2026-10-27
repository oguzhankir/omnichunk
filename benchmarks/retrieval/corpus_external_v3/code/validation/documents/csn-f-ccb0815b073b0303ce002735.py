def cli_command_resume(self, msg):
        
        if self.state == State.PAUSED:
            self.state = State.WAITING
