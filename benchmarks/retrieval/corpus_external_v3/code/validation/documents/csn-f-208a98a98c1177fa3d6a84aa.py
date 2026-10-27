def process_ttl(data, template):
    
    record = ""
    if data is not None:
        record += "$TTL %s" % data

    return template.replace("{$ttl}", record)
