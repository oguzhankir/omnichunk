

__all__ = ('upload_dir', 'upload_file', 'upload_object',
           'create_dir_redirect_object', 'ObjectManager')

import os
import logging
import mimetypes

import boto3

from .exceptions import S3Error


def upload_dir(bucket_name, path_prefix, source_dir,
               upload_dir_redirect_objects=True,
               surrogate_key=None,
               surrogate_control=None, cache_control=None,
               acl=None,
               aws_access_key_id=None, aws_secret_access_key=None,
               aws_profile=None):
    
    logger = logging.getLogger(__name__)

    logger.debug('s3upload.upload({0}, {1}, {2})'.format(
        bucket_name, path_prefix, source_dir))

    session = boto3.session.Session(
        profile_name=aws_profile,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key)
    s3 = session.resource('s3')
    bucket = s3.Bucket(bucket_name)

    metadata = {}
    if surrogate_key is not None:
        metadata['surrogate-key'] = surrogate_key
    if surrogate_control is not None:
        metadata['surrogate-control'] = surrogate_control

    manager = ObjectManager(session, bucket_name, path_prefix)

    for (rootdir, dirnames, filenames) in os.walk(source_dir):
        # name of root directory on S3 bucket
        bucket_root = os.path.relpath(rootdir, start=source_dir)
        if bucket_root in ('.', '/'):
            bucket_root = ''

        # Delete bucket directories that no longer exist in source
        bucket_dirnames = manager.list_dirnames_in_directory(bucket_root)
        for bucket_dirname in bucket_dirnames:
            if bucket_dirname not in dirnames:
                logger.debug(('Deleting bucket directory {0}'.format(
                    bucket_dirname)))
                manager.delete_directory(bucket_dirname)

        # Delete files that no longer exist in source
        bucket_filenames = manager.list_filenames_in_directory(bucket_root)
        for bucket_filename in bucket_filenames:
            if bucket_filename not in filenames:
                bucket_filename = os.path.join(bucket_root, bucket_filename)
                logger.debug(
                    'Deleting bucket file {0}'.format(bucket_filename))
                manager.delete_file(bucket_filename)

        # Upload files in directory
        for filename in filenames:
            local_path = os.path.join(rootdir, filename)
            bucket_path = os.path.join(path_prefix, bucket_root, filename)
            logger.debug('Uploading to {0}'.format(bucket_path))
            upload_file(local_path, bucket_path, bucket,
                        metadata=metadata, acl=acl,
                        cache_control=cache_control)

        # Upload a directory redirect object
        if upload_dir_redirect_objects is True:
            bucket_dir_path = os.path.join(path_prefix, bucket_root)
            create_dir_redirect_object(
                bucket_dir_path,
                bucket,
                metadata=metadata,
                acl=acl,
                cache_control=cache_control)


def upload_file(local_path, bucket_path, bucket,
                metadata=None, acl=None, cache_control=None):
    
    logger = logging.getLogger(__name__)

    extra_args = {}
    if acl is not None:
        extra_args['ACL'] = acl
    if metadata is not None and len(metadata) > 0:  # avoid empty Metadata
        extra_args['Metadata'] = metadata
    if cache_control is not None:
        extra_args['CacheControl'] = cache_control

    # guess_type returns None if it cannot detect a type
    content_type, content_encoding = mimetypes.guess_type(local_path,
                                                          strict=False)
    if content_type is not None:
        extra_args['ContentType'] = content_type

    logger.debug(str(extra_args))

    obj = bucket.Object(bucket_path)
    # no return status from the upload_file api
    obj.upload_file(local_path, ExtraArgs=extra_args)


def upload_object(bucket_path, bucket, content='',
                  metadata=None, acl=None, cache_control=None,
                  content_type=None):
    
    obj = bucket.Object(bucket_path)

    # Object.put seems to be sensitive to None-type kwargs, so we filter first
    args = {}
    if metadata is not None and len(metadata) > 0:  # avoid empty Metadata
        args['Metadata'] = metadata
    if acl is not None:
        args['ACL'] = acl
    if cache_control is not None:
        args['CacheControl'] = cache_control
    if content_type is not None:
        args['ContentType'] = content_type

    obj.put(Body=content, **args)


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


class ObjectManager(object):
    
    def __init__(self, session, bucket_name, bucket_root):
        super().__init__()
        self._logger = logging.getLogger(__name__)

        s3 = session.resource('s3')
        bucket = s3.Bucket(bucket_name)
        self._session = session
        self._bucket = bucket
        self._bucket_root = bucket_root
        # Strip trailing '/' from bucket_root for comparisons
        self._bucket_root = self._bucket_root.rstrip('/')

    def list_filenames_in_directory(self, dirname):
        
        prefix = self._create_prefix(dirname)
        filenames = []
        for obj in self._bucket.objects.filter(Prefix=prefix):
            if obj.key.endswith('/'):
                # a directory redirect object, not a file
                continue
            obj_dirname = os.path.dirname(obj.key)
            if obj_dirname == prefix:
                # object is at root of directory
                filenames.append(os.path.relpath(obj.key,
                                                 start=prefix))
        return filenames

    def list_dirnames_in_directory(self, dirname):
        
        prefix = self._create_prefix(dirname)
        dirnames = []
        for obj in self._bucket.objects.filter(Prefix=prefix):
            # get directory name of every object under this path prefix
            dirname = os.path.dirname(obj.key)

            # dirname is empty if the object happens to be the directory
            # redirect object object for the prefix directory (directory
            # redirect objects are named after directories and have metadata
            # that tells Fastly to redirect the browser to the index.html
            # contained in the directory).
            if dirname == '':
                dirname = obj.key + '/'

            # Strip out the path prefix from the directory name
            rel_dirname = os.path.relpath(dirname, start=prefix)

            # If there's only one part then this directory is at the root
            # relative to the prefix. We want this.
            dir_parts = rel_dirname.split('/')
            if len(dir_parts) == 1:
                dirnames.append(dir_parts[0])

        # Above algorithm finds root directories for all *files* in sub
        # subdirectories; trim down to the unique set.
        dirnames = list(set(dirnames))

        # Remove posix-like relative directory names that can appear
        # in the bucket listing.
        for filtered_dir in ('.', '..'):
            if filtered_dir in dirnames:
                dirnames.remove(filtered_dir)

        return dirnames

    def _create_prefix(self, dirname):
        
        if dirname in ('.', '/'):
            dirname = ''
        # Strips trailing slash from dir prefix for comparisons
        # os.path.dirname() returns directory names without a trailing /
        prefix = os.path.join(self._bucket_root, dirname)
        prefix = prefix.rstrip('/')
        return prefix

    def delete_file(self, filename):
        
        key = os.path.join(self._bucket_root, filename)
        objects = list(self._bucket.objects.filter(Prefix=key))
        for obj in objects:
            obj.delete()

    def delete_directory(self, dirname):
        
        key = os.path.join(self._bucket_root, dirname)
        if not key.endswith('/'):
            key += '/'

        key_objects = [{'Key': obj.key}
                       for obj in self._bucket.objects.filter(Prefix=key)]
        if len(key_objects) == 0:
            msg = 'No objects in bucket directory {}'.format(dirname)
            raise RuntimeError(msg)
        delete_keys = {'Objects': key_objects}
        # based on http://stackoverflow.com/a/34888103
        s3 = self._session.resource('s3')
        r = s3.meta.client.delete_objects(Bucket=self._bucket.name,
                                          Delete=delete_keys)
        self._logger.debug(r)
        if 'Errors' in r:
            raise S3Error('S3 could not delete {0}'.format(key))
