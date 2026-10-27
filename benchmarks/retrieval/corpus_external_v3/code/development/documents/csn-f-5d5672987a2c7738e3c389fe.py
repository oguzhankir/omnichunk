async def load(self, filename):
        
        cmd = "load %s" % filename
        return await asyncio.wait_for(
            self._protocol.send_command(cmd), timeout=self._timeout
        )
