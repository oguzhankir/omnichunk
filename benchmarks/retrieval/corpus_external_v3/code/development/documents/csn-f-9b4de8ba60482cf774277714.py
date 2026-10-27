def render(self, obj):
        
        self.obj = obj
        attrs = ' '.join([
            '%s="%s"' % (attr_name, attr.resolve(obj))
            if isinstance(attr, Accessor)
            else '%s="%s"' % (attr_name, attr)
            for attr_name, attr in self.attrs.items()
        ])
        return mark_safe(u'<a %s>%s</a>' % (attrs, self.text))
