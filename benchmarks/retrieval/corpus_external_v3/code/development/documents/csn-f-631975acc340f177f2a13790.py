def ping(self):
        

        self.__validate_ping_param()

        ping_proc = subprocrunner.SubprocessRunner(self.__get_ping_command())
        ping_proc.run()

        return PingResult(ping_proc.stdout, ping_proc.stderr, ping_proc.returncode)
