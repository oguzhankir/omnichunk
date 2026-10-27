def populate_fields(api_client, instance, data):
        
        for key, value in instance.__class__._fields.items():
            default = getattr(value, "default", None)
            newval = data.get(value.field, default)

            if isinstance(value, SyntheticField):
                newval = value.formatter(api_client, data, newval)
                setattr(instance, key, newval)
                continue

            model_class = getattr(value, "model", None)
            if newval and model_class:
                if isinstance(newval, list):
                    newval = model_class.from_json_list(api_client, newval)
                else:
                    newval = model_class.from_json(api_client, newval)

            if newval and value.formatter:
                newval = value.formatter(api_client, newval)

            setattr(instance, key, newval)
