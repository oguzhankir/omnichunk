def resolve(self, context, quiet=True):
        
        try:
            obj = context
            for level in self.levels:
                if isinstance(obj, dict):
                    obj = obj[level]
                elif isinstance(obj, list) or isinstance(obj, tuple):
                    obj = obj[int(level)]
                else:
                    if callable(getattr(obj, level)):
                        try:
                            obj = getattr(obj, level)()
                        except KeyError:
                            obj = getattr(obj, level)
                    else:
                        # for model field that has choice set
                        # use get_xxx_display to access
                        display = 'get_%s_display' % level
                        obj = getattr(obj, display)() if hasattr(obj, display) else getattr(obj, level)
                if not obj:
                    break
            return obj
        except Exception as e:
            if quiet:
                return ''
            else:
                raise e
