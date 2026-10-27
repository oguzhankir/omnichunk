def register(cls, vendor_id, product_id, mapping):
        
        cls._registry[(vendor_id, product_id)] = mapping
