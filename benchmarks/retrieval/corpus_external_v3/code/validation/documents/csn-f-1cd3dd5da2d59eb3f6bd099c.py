def status(self):
        
        nad_reply = self._send(self.POLL_VOLUME +
                               self.POLL_POWER +
                               self.POLL_MUTED +
                               self.POLL_SOURCE, read_reply=True)
        if nad_reply is None:
            return

        # split reply into parts of 10 characters
        num_chars = 10
        nad_status = [nad_reply[i:i + num_chars]
                      for i in range(0, len(nad_reply), num_chars)]

        return {'volume': int(nad_status[0][-2:], 16),
                'power': nad_status[1][-2:] == '01',
                'muted': nad_status[2][-2:] == '01',
                'source': self.SOURCES_REVERSED[nad_status[3][-2:]]}
