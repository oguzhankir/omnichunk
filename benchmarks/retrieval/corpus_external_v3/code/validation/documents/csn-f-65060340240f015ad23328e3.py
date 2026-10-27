def exec_command(self, domain, function, operator, value=None):
        
        if operator in CMDS[domain][function]['supported_operators']:
            if operator is '=' and value is None:
                raise ValueError('No value provided')

            if value is None:
                cmd = ''.join([CMDS[domain][function]['cmd'], operator])
            else:
                cmd = ''.join(
                    [CMDS[domain][function]['cmd'], operator, str(value)])
        else:
            raise ValueError('Invalid operator provided %s' % operator)

        if self._open_connection():
            # For telnet the first \r / \n is recommended only
            self.telnet.write((''.join(['\r', cmd, '\n']).encode()))
            # Could raise eg. socket.error, UnicodeError, let the client handle it

            # Test 3 x buffer is completely empty
            # With the default timeout that means a delay at
            # about 3+ seconds
            loop = 3
            while loop:
                msg = self.telnet.read_until('\n'.encode(), self.timeout)
                # Could raise eg. EOFError, UnicodeError, let the client handle it

                if msg == "":
                    # Nothing in buffer
                    loop -= 1
                    continue

                msg = msg.decode().strip('\r\n')
                # Could raise eg. UnicodeError, let the client handle it

                #print("NAD reponded with '%s'" % msg)
                # Wait for the response that equals the requested domain.function
                if msg.strip().split('=')[0].lower() == '.'.join([domain, function]).lower():
                    # b'Main.Volume=-12\r will return -12
                    return msg.strip().split('=')[1]

            raise RuntimeError('Failed to read response')

        raise RuntimeError('Failed to open connection')
