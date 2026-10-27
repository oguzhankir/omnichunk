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
