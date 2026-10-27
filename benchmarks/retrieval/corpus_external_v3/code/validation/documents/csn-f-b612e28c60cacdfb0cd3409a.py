def _change_precision(self, val, base=0):
        
        if not isinstance(val, int):
            raise TypeError('The first argument must be an integer.')
        val = round(abs(val))
        val = (lambda num: base if is_num(num) else num)(val)
        return val
