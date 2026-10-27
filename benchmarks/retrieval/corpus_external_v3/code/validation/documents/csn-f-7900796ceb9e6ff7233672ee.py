def dumps(obj):
    
    if not isinstance(obj, dict):
        raise TypeError('can only dump a dictionary as an Appinfo but got ' + type(obj).__name__)

    return b''.join(AppinfoEncoder(obj).iter_encode())
