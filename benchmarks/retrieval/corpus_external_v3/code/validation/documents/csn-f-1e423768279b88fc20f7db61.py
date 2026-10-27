def save_form_data(self, instance, data):
        
        to_assign = data
        if data and isinstance(data, tuple):
            # This value is coming from a MultiValueField
            if data[0] is None:
                # This means the file hasn't changed but we need to
                # update the ppoi
                current_field = getattr(instance, self.name)
                if data[1]:
                    current_field.ppoi = data[1]
                to_assign = current_field
            elif data[0] is False:
                # This means the 'Clear' checkbox was checked so we
                # need to empty the field
                to_assign = ''
            else:
                # This means there is a new upload so we need to unpack
                # the tuple and assign the first position to the field
                # attribute
                to_assign = data[0]
        super(VersatileImageField, self).save_form_data(instance, to_assign)
