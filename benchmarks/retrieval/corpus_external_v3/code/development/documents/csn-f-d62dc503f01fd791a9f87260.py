def write_lines(self, data):
        
        lines = data.replace('\r', '').split('\n')
        for line in lines:
            self.__exchange(line)
