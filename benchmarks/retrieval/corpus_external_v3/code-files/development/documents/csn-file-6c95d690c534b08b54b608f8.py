# -*- coding: utf-8 -*-

import os
import json
import time
import inspect

from collections import OrderedDict, deque
from datetime import datetime
from base64 import b64encode, b64decode

try:
    import numpy as np
except ImportError:  # pragma: no cover
    pass

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pass

try:
    from .helper import get_class_name
    from .comments import strip_comments
    from .warning import logger, WARN_MSG, prt_console
    from .pkg import compresslib
    from .pkg.six import PY2, PY3, add_metaclass, string_types, binary_type, iteritems
    from .pkg.dateutil.parser import parse
    from .pkg.atomicwrites import atomic_write
except:  # pragma: no cover
    from superjson.helper import get_class_name
    from superjson.comments import strip_comments
    from superjson.warning import logger, WARN_MSG, prt_console
    from superjson.pkg import compresslib
    from superjson.pkg.six import PY2, PY3, add_metaclass, string_types, binary_type, iteritems
    from superjson.pkg.dateutil.parser import parse
    from superjson.pkg.atomicwrites import atomic_write

if PY2:  # pragma: no cover
    getfullargspec = inspect.getargspec
elif PY3:  # pragma: no cover
    getfullargspec = inspect.getfullargspec
else:  # pragma: no cover
    raise EnvironmentError


def get_class_name_from_dumper_loader_method(func):
    
    return getfullargspec(func).defaults[0]


def is_dumper_method(func):
    
    if getfullargspec(func).args == ["self", "obj", "class_name"]:
        return True
    else:
        return False


def is_loader_method(func):
    
    if getfullargspec(func).args == ["self", "dct", "class_name"]:
        return True
    else:
        return False


class Meta(type):

    def __new__(cls, name, bases, attrs):
        klass = super(Meta, cls).__new__(cls, name, bases, attrs)

        _dumpers = dict()
        _loaders = dict()

        for base in inspect.getmro(klass):
            for attr, value in base.__dict__.items():
                dumper_warning_message = WARN_MSG.format(
                    attr=attr,
                    method_type="dumper",
                    obj_or_dct="obj",
                    dump_or_load="dump",
                )

                loader_warning_message = WARN_MSG.format(
                    attr=attr,
                    method_type="loader",
                    obj_or_dct="dct",
                    dump_or_load="load",
                )

                # link dumper / loader method with the full classname
                # find dumper method,
                if attr.startswith("dump_"):
                    try:
                        if is_dumper_method(value):
                            class_name = get_class_name_from_dumper_loader_method(
                                value)
                            _dumpers[class_name] = value
                        else:
                            logger.warning(dumper_warning_message)
                    except TypeError:
                        logger.warning(dumper_warning_message)

                # find loader method
                if attr.startswith("load_"):
                    try:
                        if is_loader_method(value):
                            class_name = get_class_name_from_dumper_loader_method(
                                value)
                            _loaders[class_name] = value
                        else:
                            logger.warning(loader_warning_message)
                    except TypeError:
                        logger.warning(loader_warning_message)

        klass._dumpers = _dumpers
        klass._loaders = _loaders
        return klass


bytes_class_name = get_class_name(binary_type())
set_class_name = get_class_name(set())


def is_compressed_json_file(abspath):
    
    abspath = abspath.lower()
    fname, ext = os.path.splitext(abspath)
    if ext in [".json", ".js"]:
        is_compressed = False
    elif ext == ".gz":
        is_compressed = True
    else:
        raise ValueError(
            "'%s' is not a valid json file. "
            "extension has to be '.json' or '.js' for uncompressed, '.gz' "
            "for compressed." % abspath)
    return is_compressed


@add_metaclass(Meta)
class BaseSuperJson(object):
    
    _dumpers = dict()
    _loaders = dict()

    def _dump(self, obj):
        
        class_name = get_class_name(obj)
        if class_name in self._dumpers:
            return self._dumpers[class_name](self, obj)
        raise TypeError("%r is not JSON serializable" % obj)

    def _json_convert(self, obj):
        
        # OrderedDict
        if isinstance(obj, OrderedDict):
            try:
                return self._dump(obj)
            except TypeError:
                return {k: self._json_convert(v) for k, v in iteritems(obj)}

        # nested dict
        elif isinstance(obj, dict):
            return {k: self._json_convert(v) for k, v in iteritems(obj)}

        # list or tuple
        elif isinstance(obj, (list, tuple)):
            return list((self._json_convert(v) for v in obj))

        # float
        elif isinstance(obj, float):
            return float(json.encoder.FLOAT_REPR(obj))

        # single object
        try:
            return self._dump(obj)
        except TypeError:
            return obj

    def _object_hook1(self, dct):
        
        # {"$class_name": obj_data}
        if len(dct) == 1:
            for key, value in iteritems(dct):
                class_name = key[1:]
                if class_name in self._loaders:
                    return self._loaders[class_name](self, dct)
            return dct
        return dct

    def _object_hook2(self, dct):  # pragma: no cover
        
        for class_name, loader in self._loaders.items():
            if ("$" + class_name) in dct:
                return loader(self, dct)
        return dct

    def dumps(self, obj,
              indent=None,
              sort_keys=None,
              pretty=False,
              float_precision=None,
              ensure_ascii=True,
              compress=False,
              **kwargs):
        
        if pretty:
            indent = 4
            sort_keys = True

        if float_precision is None:
            json.encoder.FLOAT_REPR = repr
        else:
            json.encoder.FLOAT_REPR = lambda x: format(
                x, ".%sf" % float_precision)

        s = json.dumps(
            self._json_convert(obj),
            indent=indent,
            sort_keys=sort_keys,
            ensure_ascii=ensure_ascii,
            **kwargs
        )

        if compress:
            s = compresslib.compress(s, return_type="str")

        return s

    def loads(self, s,
              object_hook=None,
              decompress=False,
              ignore_comments=False,
              **kwargs):
        
        if decompress:
            s = compresslib.decompress(s, return_type="str")

        if ignore_comments:
            s = strip_comments(s)

        if object_hook is None:
            object_hook = self._object_hook1

        if "object_pairs_hook" in kwargs:
            del kwargs["object_pairs_hook"]

        obj = json.loads(
            s,
            object_hook=object_hook,
            object_pairs_hook=None,
            **kwargs
        )

        return obj

    def dump(self, obj,
             abspath,
             indent=None,
             sort_keys=None,
             pretty=False,
             float_precision=None,
             ensure_ascii=True,
             overwrite=False,
             verbose=True,
             **kwargs):
        
        prt_console("\nDump to '%s' ..." % abspath, verbose)

        is_compressed = is_compressed_json_file(abspath)

        if not overwrite:
            if os.path.exists(abspath):  # pragma: no cover
                prt_console(
                    "    Stop! File exists and overwrite is not allowed",
                    verbose,
                )
                return

        st = time.clock()

        s = self.dumps(
            obj,
            indent=indent,
            sort_keys=sort_keys,
            pretty=pretty,
            float_precision=float_precision,
            ensure_ascii=ensure_ascii,
            compress=False,  # use uncompressed string, and directly write to file
            **kwargs
        )

        with atomic_write(abspath, mode="wb", overwrite=True) as f:
            if is_compressed:
                f.write(compresslib.compress(s, return_type="bytes"))
            else:
                f.write(s.encode("utf-8"))

        prt_console(
            "    Complete! Elapse %.6f sec." % (time.clock() - st),
            verbose,
        )
        return s

    def load(self, abspath,
             object_hook=None,
             ignore_comments=False,
             verbose=True,
             **kwargs):
        
        prt_console("\nLoad from '%s' ..." % abspath, verbose)

        is_compressed = is_compressed_json_file(abspath)

        if not os.path.exists(abspath):
            raise EnvironmentError("'%s' doesn't exist." % abspath)

        st = time.clock()

        with open(abspath, "rb") as f:
            if is_compressed:
                s = compresslib.decompress(f.read(), return_type="str")
            else:
                s = f.read().decode("utf-8")

        obj = self.loads(
            s,
            object_hook=object_hook,
            decompress=False,
            ignore_comments=ignore_comments,
        )

        prt_console("    Complete! Elapse %.6f sec." % (time.clock() - st),
                    verbose)

        return obj


class SupportBuiltInDataType(object):
    def dump_bytes(self, obj, class_name=bytes_class_name):
        
        return {"$" + class_name: b64encode(obj).decode()}

    def load_bytes(self, dct, class_name=bytes_class_name):
        
        return b64decode(dct["$" + class_name].encode())

    def dump_datetime(self, obj, class_name="datetime.datetime"):
        
        return {"$" + class_name: obj.isoformat()}

    def load_datetime(self, dct, class_name="datetime.datetime"):
        
        return parse(dct["$" + class_name])

    def dump_date(self, obj, class_name="datetime.date"):
        
        return {"$" + class_name: str(obj)}

    def load_date(self, dct, class_name="datetime.date"):
        
        return datetime.strptime(dct["$" + class_name], "%Y-%m-%d").date()

    def dump_set(self, obj, class_name=set_class_name):
        
        return {"$" + class_name: [self._json_convert(item) for item in obj]}

    def load_set(self, dct, class_name=set_class_name):
        
        return set(dct["$" + class_name])

    def dump_deque(self, obj, class_name="collections.deque"):
        
        return {"$" + class_name: [self._json_convert(item) for item in obj]}

    def load_deque(self, dct, class_name="collections.deque"):
        
        return deque(dct["$" + class_name])

    def dump_OrderedDict(self, obj, class_name="collections.OrderedDict"):
        
        return {
            "$" + class_name: [
                (key, self._json_convert(value)) for key, value in iteritems(obj)
            ]
        }

    def load_OrderedDict(self, dct, class_name="collections.OrderedDict"):
        
        return OrderedDict(dct["$" + class_name])


numpy_ndarray_class_name = "numpy.ndarray"


class SupportNumpyArray(object):
    def dump_nparray(self, obj, class_name=numpy_ndarray_class_name):
        
        return {"$" + class_name: self._json_convert(obj.tolist())}

    def load_nparray(self, dct, class_name=numpy_ndarray_class_name):
        
        return np.array(dct["$" + class_name])


pathlib_path_class_name = "pathlib.Path"
try:
    from pathlib import Path

    pathlib_path_class_name = get_class_name(Path(__file__))
except ImportError:
    try:
        from pathlib2 import Path

        pathlib_path_class_name = get_class_name(Path(__file__))
    except ImportError:
        pass


pathlib_mate_path_class_name = "pathlib_mate.pathlib2.Path"
try:
    from pathlib_mate import PathCls

    pathlib_mate_path_class_name = get_class_name(PathCls(__file__))
except ImportError:
    pass


class SupportPathlib(object):
    def dump_pathlib_path(self, obj, class_name=pathlib_path_class_name):
        
        return {"$" + class_name: str(obj)}

    def load_pathlib_path(self, dct, class_name=pathlib_path_class_name):
        
        return Path(dct["$" + class_name])

    def dump_pathlib_mate_path(self, obj, class_name=pathlib_mate_path_class_name):
        
        return {"$" + class_name: str(obj)}

    def load_pathlib_mate_path(self, dct, class_name=pathlib_mate_path_class_name):
        
        return PathCls(dct["$" + class_name])


class SuperJson(BaseSuperJson,
                SupportBuiltInDataType,
                SupportNumpyArray,
                SupportPathlib): pass


superjson = SuperJson()
