def operation_list(uploader):
    
    files = uploader.file_list()
    for f in files:
        log.info("{file:30s} {size}".format(file=f[0], size=f[1]))
