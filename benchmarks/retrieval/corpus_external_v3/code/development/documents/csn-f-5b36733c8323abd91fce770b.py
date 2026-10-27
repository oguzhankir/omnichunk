def delete(self, wait=True):
        
        resp = self.parent.delete(self.id)
        if wait:
            self.wait()
        return resp
