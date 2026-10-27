def parse(self, ping_message):
        

        try:
            # accept PingResult instance as an input
            if typepy.is_not_null_string(ping_message.stdout):
                ping_message = ping_message.stdout
        except AttributeError:
            pass

        logger.debug("parsing ping result: {}".format(ping_message))

        self.__parser = NullPingParser()

        if typepy.is_null_string(ping_message):
            logger.debug("ping_message is empty")
            self.__stats = PingStats()

            return self.__stats

        ping_lines = _to_unicode(ping_message).splitlines()
        parser_class_list = (
            LinuxPingParser,
            WindowsPingParser,
            MacOsPingParser,
            AlpineLinuxPingParser,
        )

        for parser_class in parser_class_list:
            self.__parser = parser_class()
            try:
                self.__stats = self.__parser.parse(ping_lines)
                return self.__stats
            except ParseError as e:
                if e.reason != ParseErrorReason.HEADER_NOT_FOUND:
                    raise e
            except pp.ParseException:
                pass

        self.__parser = NullPingParser()

        return self.__stats
