async def byte_order(self):
        
        return await asyncio.wait_for(
            self._protocol.send_command("byteorder"), timeout=self._timeout
        )
