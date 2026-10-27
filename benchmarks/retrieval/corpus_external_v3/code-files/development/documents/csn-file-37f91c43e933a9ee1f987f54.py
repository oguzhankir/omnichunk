# -*- coding: UTF-8 -*-



from __future__ import division, unicode_literals, absolute_import

import os
import re
import itertools
import functools
import calendar
import contextlib
import logging
import datetime
import glob
import tempfile
import platform
import ctypes
import importlib

import six
from six.moves import map

log = logging.getLogger(__name__)


def get_unique_pathname(path, root=''):
	
	path = os.path.join(root, path)
	# consider the path supplied, then the paths with numbers appended
	potentialPaths = itertools.chain((path,), __get_numbered_paths(path))
	potentialPaths = six.moves.filterfalse(os.path.exists, potentialPaths)
	return next(potentialPaths)


def __get_numbered_paths(filepath):
	
	format = '%s (%%d)%s' % splitext_files_only(filepath)
	return map(lambda n: format % n, itertools.count(1))


def splitext_files_only(filepath):
	
	return (
		(filepath, '') if os.path.isdir(filepath) else os.path.splitext(filepath)
	)


def set_time(filename, mod_time):
	
	log.debug('Setting modified time to %s', mod_time)
	mtime = calendar.timegm(mod_time.utctimetuple())
	# utctimetuple discards microseconds, so restore it (for consistency)
	mtime += mod_time.microsecond / 1000000
	atime = os.stat(filename).st_atime
	os.utime(filename, (atime, mtime))


def get_time(filename):
	
	ts = os.stat(filename).st_mtime
	return datetime.datetime.utcfromtimestamp(ts)


def insert_before_extension(filename, content):
	
	parts = list(os.path.splitext(filename))
	parts[1:1] = [content]
	return ''.join(parts)


class DirectoryStack(list):
	
	def pushd(self, new_dir):
		self.append(os.getcwd())
		os.chdir(new_dir)

	def popd(self):
		res = os.getcwd()
		os.chdir(self.pop())
		return res

	@contextlib.contextmanager
	def context(self, new_dir):
		self.pushd(new_dir)
		try:
			yield
		finally:
			self.popd()


def recursive_glob(root, spec):
	
	specs = (
		os.path.join(dirpath, dirname, spec)
		for dirpath, dirnames, filenames in os.walk(root)
		for dirname in dirnames
	)

	return itertools.chain.from_iterable(
		glob.iglob(spec)
		for spec in specs
	)


def encode(name, system='NTFS'):
	
	assert system == 'NTFS', 'unsupported filesystem'
	special_characters = r'<>:"/\|?*' + ''.join(map(chr, range(32)))
	pattern = '|'.join(map(re.escape, special_characters))
	pattern = re.compile(pattern)
	return pattern.sub('_', name)


class save_to_file():
	
	def __init__(self, content):
		self.content = content

	def __enter__(self):
		tf = tempfile.NamedTemporaryFile(delete=False)
		tf.write(self.content)
		tf.close()
		self.filename = tf.name
		return tf.name

	def __exit__(self, type, value, traceback):
		os.remove(self.filename)


@contextlib.contextmanager
def tempfile_context(*args, **kwargs):
	
	fd, filename = tempfile.mkstemp(*args, **kwargs)
	os.close(fd)
	try:
		yield filename
	finally:
		os.remove(filename)


def replace_extension(new_ext, filename):
	
	return os.path.splitext(filename)[0] + new_ext


def ExtensionReplacer(new_ext):
	
	return functools.partial(replace_extension, new_ext)


def ensure_dir_exists(func):
	
	@functools.wraps(func)
	def make_if_not_present():
		dir = func()
		if not os.path.isdir(dir):
			os.makedirs(dir)
		return dir
	return make_if_not_present


def read_chunks(file, chunk_size=2048, update_func=lambda x: None):
	
	while(True):
		res = file.read(chunk_size)
		if not res:
			break
		update_func(len(res))
		yield res


def is_hidden(path):
	
	full_path = os.path.abspath(path)
	name = os.path.basename(full_path)

	def no(path):
		return False
	platform_hidden = globals().get('is_hidden_' + platform.system(), no)
	return name.startswith('.') or platform_hidden(full_path)


def is_hidden_Windows(path):
	res = ctypes.windll.kernel32.GetFileAttributesW(path)
	assert res != -1
	return bool(res & 2)


def is_hidden_Darwin(path):
	Foundation = importlib.import_module('Foundation')
	url = Foundation.NSURL.fileURLWithPath_(path)
	res = url.getResourceValue_forKey_error_(
		None, Foundation.NSURLIsHiddenKey, None
	)
	return res[1]
