def get_prefix(multicodec):
    
    try:
        prefix = varint.encode(NAME_TABLE[multicodec])
    except KeyError:
        raise ValueError('{} multicodec is not supported.'.format(multicodec))
    return prefix
