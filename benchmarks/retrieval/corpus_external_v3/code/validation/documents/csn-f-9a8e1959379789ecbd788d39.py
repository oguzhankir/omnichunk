def validate_versatileimagefield_sizekey_list(sizes):
    
    try:
        for key, size_key in sizes:
            size_key_split = size_key.split('__')
            if size_key_split[-1] != 'url' and (
                'x' not in size_key_split[-1]
            ):
                raise InvalidSizeKey(
                    "{0} is an invalid size. All sizes must be either "
                    "'url' or made up of at least two segments separated "
                    "by double underscores. Examples: 'crop__400x400', "
                    "filters__invert__url".format(size_key)
                )
    except ValueError:
        raise InvalidSizeKeySet(
            '{} is an invalid size key set. Size key sets must be an '
            'iterable of 2-tuples'.format(str(sizes))
        )
    return list(set(sizes))
