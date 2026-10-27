async def stream_frames(self, frames="allframes", components=None, on_packet=None):
        

        if components is None:
            components = ["all"]
        else:
            _validate_components(components)

        self._protocol.set_on_packet(on_packet)

        cmd = "streamframes %s %s" % (frames, " ".join(components))
        return await asyncio.wait_for(
            self._protocol.send_command(cmd), timeout=self._timeout
        )
