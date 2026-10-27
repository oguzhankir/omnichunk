def open_bucket(bucket_name,
                aws_access_key_id=None, aws_secret_access_key=None,
                aws_profile=None):
    
    session = boto3.session.Session(
        profile_name=aws_profile,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key)
    s3 = session.resource('s3')
    bucket = s3.Bucket(bucket_name)
    return bucket
