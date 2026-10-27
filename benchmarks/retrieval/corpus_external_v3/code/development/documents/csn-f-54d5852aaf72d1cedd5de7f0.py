def play(self, song):
        
        self._callbacks.play(song)
        self._load_track(song)
        time.sleep(2)  # Give the backend time to load the track

        while True:
            try:
                self._callbacks.pre_poll()
                self._ensure_started()
                self._loop_hook()

                readers, _, _ = select.select(
                    self._get_select_readers(), [], [], 1)

                for handle in readers:
                    if handle.fileno() == self._control_fd:
                        self._callbacks.input(handle.readline().strip(), song)
                    else:
                        value = self._read_from_process(handle)
                        if self._player_stopped(value):
                            return
            finally:
                self._callbacks.post_poll()
