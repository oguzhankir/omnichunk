def as_money(self, number, **options):
        
        # Resursively format arrays
        if isinstance(number, list):
            return map(lambda val: self.as_money(val, **options))

        # Clean up number
        decimal = options.get('decimal')
        number = self.parse(number, decimal)

        # Build options object from second param (if object) or all params,
        # extending defaults
        if check_type(options, 'dict'):
            options = (self.settings['currency'].update(options))

        # Check format (returns object with pos, neg and zero)
        formats = self._check_currency_format(options['format'])

        # Choose which format to use for this value
        use_format = (lambda num: formats['pos'] if num > 0 else formats[
                      'neg'] if num < 0 else formats['zero'])(number)
        precision = self._change_precision(number, options['precision'])
        thousands = options['thousand']
        decimal = options['decimal']
        formater = self.format(abs(number), precision, thousands, decimal)

        # Return with currency symbol added
        amount = use_format.replace(
            '%s', options['symbol']).replace('%v', formater)

        return amount
