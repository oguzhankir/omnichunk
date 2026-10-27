def as_tuple(self):
        

        from collections import namedtuple

        ping_result = self.as_dict()

        return namedtuple("PingStatsTuple", ping_result.keys())(**ping_result)
