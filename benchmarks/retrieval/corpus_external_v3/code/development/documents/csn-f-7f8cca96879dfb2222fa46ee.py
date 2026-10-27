def get_codec(bytes_):
    
    prefix = extract_prefix(bytes_)
    try:
        return CODE_TABLE[prefix]
    except KeyError:
        raise ValueError('Prefix {} not present in the lookup table'.format(prefix))
