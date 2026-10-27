import os
import time
import fcntl
import select
import socket
import logging
from shutil import which

from .utils import iterate_forever, SilentPopen


log = logging.getLogger("pydora.audio_backend")


class PlayerException(Exception):
    
    pass


class UnsupportedEncoding(PlayerException):
    
    pass


class PlayerUnusable(PlayerException):
    
    pass


class BasePlayer:
    

    def __init__(self, callbacks, control_channel):
        
        self._control_channel = control_channel
        self._control_fd = control_channel.fileno()
        self._callbacks = callbacks
        self._process = None
        self._cmd = [self._find_path()]

    def _find_path(self):
        
        raise NotImplementedError

    def _load_track(self, song):
        
        raise NotImplementedError

    def _player_stopped(self, value):
        
        raise NotImplementedError

    def raise_volume(self):
        
        raise NotImplementedError

    def lower_volume(self):
        
        raise NotImplementedError

    def _post_start(self):
        
        return

    def _loop_hook(self):
        
        return

    def _read_from_process(self, handle):
        
        return handle.readline().strip()

    def _send_cmd(self, cmd):
        
        self._process.stdin.write("{}\n".format(cmd).encode("utf-8"))
        self._process.stdin.flush()

    def stop(self):
        
        self._send_cmd("stop")

    def pause(self):
        
        self._send_cmd("pause")

    def __del__(self):
        if self._process:
            self._process.kill()

    def start(self):
        
        self._ensure_started()

    def _ensure_started(self):
        
        if self._process and self._process.poll() is None:
            return

        if not getattr(self, "_cmd"):
            raise RuntimeError("Player command is not configured")

        log.debug("Starting playback command: %r", self._cmd)
        self._process = SilentPopen(self._cmd)
        self._post_start()

    def _get_select_readers(self):
        
        return [self._control_channel, self._process.stdout]

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

    def end_station(self):
        
        raise StopIteration

    def play_station(self, station):
        
        for song in iterate_forever(station.get_playlist):
            try:
                self.play(song)
            except StopIteration:
                self.stop()
                return


class MPG123Player(BasePlayer):
    

    def __init__(self, callbacks, control_channel):
        super().__init__(callbacks, control_channel)
        self._cmd.extend(["-q", "-R", "--ignore-mime", "."])

    def _find_path(self):
        loc = which("mpg123")
        if not loc:
            raise PlayerUnusable("Unable to find mpg123")

        log.info("Using mpg123 at path %s", loc)
        return loc

    def _load_track(self, song):
        if song.encoding != "mp3":
            raise UnsupportedEncoding("mpg123 only supports mp3 files")

        self._send_cmd("load {}".format(song.audio_url))

    def _post_start(self):
        # Only output play status in the player stdout
        self._send_cmd("silence")

    def _player_stopped(self, value):
        return value.startswith(b"@P") and value.decode("utf-8")[3] == "0"

    def raise_volume(self):
        return

    def lower_volume(self):
        return


class VLCPlayer(BasePlayer):

    POLL_INTERVAL = 3
    CHUNK_SIZE = 1024
    VOL_STEPS = 5

    def __init__(self, callbacks, control_channel):
        super().__init__(callbacks, control_channel)
        self._cmd.extend(["-I", "rc", "--advanced", "--rc-fake-tty", "-q"])
        self._last_poll = 0

    def _find_path(self):
        loc = which("vlc")
        if not loc:  # Mac OS X
            loc = which("VLC", path="/Applications/VLC.app/Contents/MacOS")

        if not loc:
            raise PlayerUnusable("Unable to find VLC")

        log.info("Using vlc at location %s", loc)
        return loc

    def raise_volume(self):
        self._send_cmd("volup {}".format(self.VOL_STEPS))

    def lower_volume(self):
        self._send_cmd("voldown {}".format(self.VOL_STEPS))

    def _post_start(self):
        
        flags = fcntl.fcntl(self._process.stdout, fcntl.F_GETFL)
        fcntl.fcntl(self._process.stdout, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def _read_from_process(self, handle):
        return handle.read(self.CHUNK_SIZE).strip()

    def _load_track(self, song):
        self._send_cmd("add {}".format(song.audio_url))

    def _player_stopped(self, value):
        return "state stopped" in value.decode("utf-8")

    def _loop_hook(self):
        if (time.time() - self._last_poll) >= self.POLL_INTERVAL:
            self._send_cmd("status")
            self._last_poll = time.time()


class RemoteVLC(VLCPlayer):

    def __init__(self, host, port, callbacks, control_channel):
        self._connect_to = (host, int(port))
        self._control_sock = None
        super().__init__(callbacks, control_channel)

    def _get_select_readers(self):
        return [self._control_channel, self._control_sock]

    def _send_cmd(self, cmd):
        self._control_sock.sendall("{}\n".format(cmd).encode("utf-8"))

    def _read_from_process(self, handle):
        return handle.recv(self.CHUNK_SIZE).strip()

    def _ensure_started(self):
        if not self._control_sock:
            log.debug("Connecting to remote VLC at %r", self._connect_to)
            self._control_sock = socket.create_connection(self._connect_to)
            self._control_sock.setblocking(False)

    def _find_path(self):
        try:
            self._ensure_started()
        except socket.error:
            raise PlayerUnusable("Unable to connect to VLC")

    def _post_start(self):
        # This is a NOOP for network VLC
        pass
