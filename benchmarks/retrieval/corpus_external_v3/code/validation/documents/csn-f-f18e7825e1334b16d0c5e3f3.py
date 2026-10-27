def load_systemjs_manifest(self):
        
        # backup the original name
        _manifest_name = self.manifest_name

        # load the custom bundle manifest
        self.manifest_name = self.systemjs_manifest_name
        bundle_files = self.load_manifest()
        # reset the manifest name
        self.manifest_name = _manifest_name

        # check that the files actually exist, if not, remove them from the manifest
        for file, hashed_file in bundle_files.copy().items():
            if not self.exists(file) or not self.exists(hashed_file):
                del bundle_files[file]
        return bundle_files
