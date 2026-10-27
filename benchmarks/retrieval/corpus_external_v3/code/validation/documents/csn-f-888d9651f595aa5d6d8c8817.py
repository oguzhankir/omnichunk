def set_volume(self, volume):
        
        if 0 <= volume <= 200:
            volume = format(volume, "02x")  # Convert to hex
            self._send(self.CMD_VOLUME + volume)
