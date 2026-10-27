def format(self, number, **kwargs):
        
        # Resursively format lists
        if check_type(number, 'list'):
            return map(lambda val: self.format(val, **kwargs))
        # Clean up number
        number = self.parse(number)

        # Build options object from second param (if object) or all params,
        # extending defaults
        if check_type(kwargs, 'dict'):
            options = (self.settings['number'].update(kwargs))

        # Clean up precision
        precision = self._change_precision(options['precision'])
        negative = (lambda num: "-" if num < 0 else "")(number)
        base = str(int(self.to_fixed(abs(number) or 0, precision)), 10)
        mod = (lambda num: len(num) % 3 if len(num) > 3 else 0)(base)

        # Format the number:
        num = negative + (lambda num: base[0:num] if num else '')(mod)

        num += re.sub('/(\d{3})(?=\d)/g', '$1' +
                      options['thousand'], base[mod:])
        num += (lambda val: options[
            'decimal'] + self.to_fixed(abs(number), precision)
            .split('.')[1] if val else '')(precision)

        return num
