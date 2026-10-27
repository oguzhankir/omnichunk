
import re

from .utils import is_str, check_type, is_num


class Accounting(object):
    

    def __init__(self, options={}):
        
        settings = {
            'currency': {
                'symbol': "$",
                'format': "%s%v",
                'decimal': ".",
                'thousand': ",",
                'precision': 2,
                'grouping': 3
            },
            'number': {
                'precision': 0,
                'grouping': 3,
                'thousand': ",",
                'decimal': "."
            }
        }
        if options:
            settings.update(options)

        self.settings = settings

    def _check_currency_format(self, format=None):
        
        defaults = self.settings['currency']['format']
        if hasattr(format, '__call__'):
            format = format()
        if is_str(format) and re.match('%v', format):

            # Create and return positive, negative and zero formats:
            return {
                'pos': format,
                'neg': format.replace("-", "").replace("%v", "-%v"),
                'zero': format
            }
        elif not format or not format['por'] or not re.match('%v',
                                                             format['pos']):
            self.settings['currency']['format'] = {
                'pos': defaults,
                'neg': defaults.replace("%v", "-%v"),
                'zero': defaults
            }
            return self.settings

        return format

    def _change_precision(self, val, base=0):
        
        if not isinstance(val, int):
            raise TypeError('The first argument must be an integer.')
        val = round(abs(val))
        val = (lambda num: base if is_num(num) else num)(val)
        return val

    def parse(self, value, decimal=None):
        
        # Fails silently (need decent errors):
        value = value or 0

        # Recursively unformat arrays:
        if check_type(value, 'list'):
            return map(lambda val: self.parse(val, decimal))

        # Return the value as-is if it's already a number:
        if check_type(value, 'int') or check_type(value, 'float'):
            return value

        # Default decimal point comes from settings, but could be set to eg.","
        decimal = decimal or self.settings.number.decimal

        # Build regex to strip out everything except digits,
        # decimal point and minus sign
        regex = re.compile("[^0-9-" + decimal + "]")
        unformatted = str(value)
        unformatted = re.sub('/\((.*)\)/', "-$1", unformatted)
        unformatted = re.sub(regex, '', unformatted)
        unformatted = unformatted.replace('.', decimal)
        formatted = (lambda val: unformatted if val else 0)(
            is_num(unformatted))

        return formatted

    def to_fixed(self, value, precision):
        
        precision = self._change_precision(
            precision, self.settings['number']['precision'])

        power = pow(10, precision)
        # Multiply up by precision, round accurately, then divide
        power = round(self.parse(value) * power) / power
        return '{0} {1}.{2}f'.format(value, precision, precision)

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
