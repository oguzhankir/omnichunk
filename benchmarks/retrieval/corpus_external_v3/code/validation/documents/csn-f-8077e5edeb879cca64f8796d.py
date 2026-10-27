def create_dir_redirect_object(bucket_dir_path, bucket, metadata=None,
                               acl=None, cache_control=None):
    
    # Just the name of the 'directory' itself
    bucket_dir_path = bucket_dir_path.rstrip('/')

    # create a copy of metadata
    if metadata is not None:
        metadata = dict(metadata)
    else:
        metadata = {}

    # header used by LTD's Fastly Varnish config to create a 301 redirect
    metadata['dir-redirect'] = 'true'

    upload_object(bucket_dir_path,
                  content='',
                  bucket=bucket,
                  metadata=metadata,
                  acl=acl,
                  cache_control=cache_control)
