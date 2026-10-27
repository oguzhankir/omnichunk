def records(self, name):
        
        if self.get(name):
            return DomainRecords(self.api, name)
