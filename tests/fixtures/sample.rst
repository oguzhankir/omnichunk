Project Overview
================

Welcome to the project. This is a top-level introduction paragraph.

Installation
------------

Install the package via pip:

.. code-block:: bash

    pip install omnichunk

Then verify your install:

.. code-block:: python

    from omnichunk import Chunker
    print(Chunker().chunk("hello.py", "x = 1\n"))

Usage
-----

Basic example::

    from omnichunk import Chunker
    chunker = Chunker()

.. note::

    Make sure your input is UTF-8.

.. warning::

    Large files may take a while to process.

API Reference
-------------

Chunker.chunk
~~~~~~~~~~~~~

Returns a list of ``Chunk`` objects.

.. toctree::
    :maxdepth: 2

    intro
    api
    examples
