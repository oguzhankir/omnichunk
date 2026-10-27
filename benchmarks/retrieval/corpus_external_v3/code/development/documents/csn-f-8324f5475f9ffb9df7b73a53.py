def set_fields(self):
        

        # Get dictionary map of current model
        if self.is_initialized:
            self.model_map_dict = self.create_document_dictionary(self.model_instance)
        else:
            self.model_map_dict = self.create_document_dictionary(self.model)

        form_field_dict = self.get_form_field_dict(self.model_map_dict)
        self.set_form_fields(form_field_dict)
