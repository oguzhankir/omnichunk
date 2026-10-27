def _send(self, message, read_reply=False):
        
        sock = None
        for tries in range(0, 3):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.connect((self._host, self.PORT))
                break
            except (ConnectionError, BrokenPipeError):
                if tries == 3:
                    print("socket connect failed.")
                    return
                sleep(0.1)
        sock.send(codecs.decode(message, 'hex_codec'))
        if read_reply:
            sleep(0.1)
            reply = ''
            tries = 0
            max_tries = 20
            while len(reply) < len(message) and tries < max_tries:
                try:
                    reply += codecs.encode(sock.recv(self.BUFFERSIZE), 'hex')\
                        .decode("utf-8")
                except (ConnectionError, BrokenPipeError):
                    pass
                tries += 1
            sock.close()
            if tries >= max_tries:
                return
            return reply
        sock.close()
