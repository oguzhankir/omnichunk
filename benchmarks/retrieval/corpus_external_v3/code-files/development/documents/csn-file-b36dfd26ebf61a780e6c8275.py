from datetime import datetime
from collections import namedtuple


class Field(namedtuple("Field", ["field", "default", "formatter", "model"])):
    

    def __new__(cls, field, default=None, formatter=None, model=None):
        return super().__new__(cls, field, default, formatter, model)


class SyntheticField(namedtuple("SyntheticField", ["field"])):
    

    def formatter(self, api_client, data, newval):
        
        raise NotImplementedError


class DateField(SyntheticField):
    

    def formatter(self, api_client, data, newval):
        if not newval:
            return None

        return datetime.utcfromtimestamp(newval["time"] / 1000)


class ModelMetaClass(type):

    def __new__(cls, name, parents, dct):
        dct["_fields"] = fields = {}
        new_dct = dct.copy()

        for key, val in dct.items():
            if key.startswith("__"):
                continue

            if isinstance(val, Field) or isinstance(val, SyntheticField):
                fields[key] = val
                del new_dct[key]

        return super().__new__(cls, name, parents, new_dct)


class PandoraModel(metaclass=ModelMetaClass):
    

    @classmethod
    def from_json_list(cls, api_client, data):
        
        return [cls.from_json(api_client, item) for item in data]

    def __init__(self, api_client):
        self._api_client = api_client

        safe_types = (type(None), str, bytes, int, bool)

        for key, value in self._fields.items():
            default = getattr(value, "default", None)

            if not isinstance(default, safe_types):
                default = type(default)()

            setattr(self, key, default)

    @staticmethod
    def populate_fields(api_client, instance, data):
        
        for key, value in instance.__class__._fields.items():
            default = getattr(value, "default", None)
            newval = data.get(value.field, default)

            if isinstance(value, SyntheticField):
                newval = value.formatter(api_client, data, newval)
                setattr(instance, key, newval)
                continue

            model_class = getattr(value, "model", None)
            if newval and model_class:
                if isinstance(newval, list):
                    newval = model_class.from_json_list(api_client, newval)
                else:
                    newval = model_class.from_json(api_client, newval)

            if newval and value.formatter:
                newval = value.formatter(api_client, newval)

            setattr(instance, key, newval)

    @classmethod
    def from_json(cls, api_client, data):
        
        self = cls(api_client)
        PandoraModel.populate_fields(api_client, self, data)
        return self

    def _base_repr(self, and_also=None):
        
        items = [
            "=".join((key, repr(getattr(self, key))))
            for key in sorted(self._fields.keys())]

        if items:
            output = ", ".join(items)
        else:
            output = None

        if and_also:
            return "{}({}, {})".format(self.__class__.__name__,
                                       output, and_also)
        else:
            return "{}({})".format(self.__class__.__name__, output)

    def __repr__(self):
        return self._base_repr()


class PandoraListModel(PandoraModel, list):
    

    __list_key__ = None
    __list_model__ = None
    __index_key__ = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._index = {}

    @classmethod
    def from_json(cls, api_client, data):
        self = cls(api_client)
        PandoraModel.populate_fields(api_client, self, data)

        for item in data[cls.__list_key__]:
            model = cls.__list_model__.from_json(api_client, item)

            if self.__index_key__:
                value = getattr(model, self.__index_key__)
                self._index[value] = model

            self.append(model)

        return self

    def __getitem__(self, key):
        item = self._index.get(key, None)
        if item:
            return item
        else:
            return list.__getitem__(self, key)

    def __contains__(self, key):
        if key in self._index:
            return True
        else:
            return list.__contains__(self, key)

    def keys(self):
        return self._index.keys()

    def items(self):
        return self._index.items()

    def __repr__(self):
        return self._base_repr(and_also=list.__repr__(self))


class PandoraDictListModel(PandoraModel, dict):
    

    __dict_list_key__ = None
    __dict_key__ = None
    __list_key__ = None
    __list_model__ = None

    @classmethod
    def from_json(cls, api_client, data):
        self = cls(api_client)
        PandoraModel.populate_fields(api_client, self, data)

        for item in data[self.__dict_list_key__]:
            key = item[self.__dict_key__]
            self[key] = []

            for part in item[self.__list_key__]:
                self[key].append(
                    cls.__list_model__.from_json(api_client, part))

        return self

    def __repr__(self):
        return self._base_repr(and_also=dict.__repr__(self))
