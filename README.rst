historical_collection
=====================

.. image:: https://img.shields.io/pypi/v/historical_collection.svg
    :target: https://pypi.python.org/pypi/historical_collection
    :alt: Latest PyPI version

.. image:: https://travis-ci.org/srcrr/historical_collection.png
   :target: https://travis-ci.org/srcrr/historical_collection
   :alt: Latest Travis CI build status

Easily keep track of changes to Mongo document changes with a collection.

Concepts
========

HistoricalCollection
--------------------

An ``HistoricalCollection`` behaves just like a regular MongoDB
``Collection``, but adds additional fields and methods to apply
patching.

Patching
--------

This is most likely something you will not need to worry about since the
logic is taken care of. However…

A ``Patch`` is a set of changes. A patch is associated with a
``Document`` of an ``HistoricalCollection``.

Revision
--------

A ``Revision`` is a state of a document with a patch applied. Only the
base ``Revision`` is stored in the document table. Note (for
``historical_collection`` developers): ``Revision`` is more of a concept
than an actual object.

You won’t find yourself actively creating ``Revision``\ s (remember,
you’re creating ``Patch``\ es). They’re only retrieved.

Change
------

Just like a patch, this is most likely something you don’t need to worry
about. Changes are calculated for you.

A change consists of a dict of actions. The actions are one of:

-  ``INITIAL`` (character key ``I``)
-  ``ADD`` (character key ``A``)
-  ``REMOVE`` (character key ``R``)
-  ``UPDATE`` (character key ``U``)

``INITIAL`` actions do not not have any attributes. The ``Document``
stored in the associated ``Collection`` is the all the information
needed. The ``INITIAL`` is stored as a revision for any metadata
associated with the patch.

``ADD`` and ``UPDATE`` actions take a Python ``dict`` of keys mapped to
values. Obviously any of the ``PK_FIELD``\ s will not be included in
this.

``REMOVE`` takes a list of document keys to be removed. Just like
``ADD`` and ``UPDATE``, no ``PK_FIELD``\ s are in this list.

Requirements
============

Basic Requirements
------------------

-  Python 3.6 or higher
-  MongoDB
-  pymongo

Optionally, you may want ``pip`` and to run this in a virtual
environment.

Requirements For Development or Testing
---------------------------------------

-  Faker

Installation
============

To install from PIP

::

   user@host~# pip3 install -U historical_collection

Or clone the repostitory and execute:

::

   user@host~# python3 setup.py install

Usage
=====

Extend the Collection
---------------------

In order to keep track of changes to a document, extend
HistoricalCollection.

.. code:: ipython3

    from historical_collection.historical import HistoricalCollection
    from pymongo import MongoClient
    class Users(HistoricalCollection):
        PK_FIELDS = ['username', ]  # <<= This is the only requirement

The only requirement is the ``PK_FIELDS`` attribute that specifies the
primary keys of the document. If omitted, Python will complain. This is
so that any incoming document can be seen as “the same.”

It’s recommended to *not* use the ``_id`` field unless you have a valid
reason, and if you have a mechanism in place to keep track of the
``_id``. Otherwise, the changes will most likely be ignored.

Perhaps an example of how to patch will make it more clear.

Connect to a Mongo Database Instance
------------------------------------

.. code:: ipython3

    CLIENT_URL = "mongodb://localhost:27017/"
    DATABASE = "historical_collection_example"
    mongo = MongoClient(CLIENT_URL)
    db = mongo[DATABASE]

    mongo.drop_database(db)

    users = Users(database=db)

There’s a lot going on under the hood with the line
``users = Users(database=db)``. We’re also creating a ``deltas``
collection with the format ``__deltas_User``. Usually you will not need
to access the deltas collection, but if you do, then you can always
access it with ``<collection_instance>._deltas_collection``:

.. code:: ipython3

    users._deltas_collection




.. parsed-literal::

    Collection(Database(MongoClient(host=['localhost:27017'], document_class=dict, tz_aware=False, connect=True), 'historical_collection_example'), '__deltas_Users')



Patching Documents
------------------

Let’s add an initial user to your document. You’re probably already
familiar with ``Collection.insert_one()`` and
``Collection.insert_many()``. Well, ``HistoricalCollection`` has 2
additional methods for inserting:

-  ``HistoricalCollection.patch_one()``
-  ``HistoricalCollection.patch_many()``

They behave similarly to ``insert_one`` and ``insert_many`` with one
major difference: Only the first ``Document`` is inserted. Additional
documents have deltas generated and stored in the ``_deltas_collection``
collection.

Let’s patch our first document.

.. code:: ipython3

    users.patch_one({"email": "darth_later@example2.com"})


::


    ---------------------------------------------------------------------------

    KeyError                                  Traceback (most recent call last)

    ~/projects/historical_collection/historical_collection/historical.py in _document_filter(self, document)
        134         try:
    --> 135             return dict([(k, document[k]) for k in self.PK_FIELDS])
        136         except KeyError as e:


    ~/projects/historical_collection/historical_collection/historical.py in <listcomp>(.0)
        134         try:
    --> 135             return dict([(k, document[k]) for k in self.PK_FIELDS])
        136         except KeyError as e:


    KeyError: 'username'


    During handling of the above exception, another exception occurred:


    KeyError                                  Traceback (most recent call last)

    <ipython-input-4-03f5bb018ec2> in <module>
    ----> 1 users.patch_one({"email": "darth_later@example2.com"})


    ~/projects/historical_collection/historical_collection/historical.py in patch_one(self, *args, **kwargs)
        258         doc = args[0]
        259         metadata = kwargs.pop("metadata", None)
    --> 260         fltr = self._document_filter(doc)
        261         latest = self.latest(fltr)
        262         insert_result = None


    ~/projects/historical_collection/historical_collection/historical.py in _document_filter(self, document)
        138                 raise KeyError(
        139                     "Perhaps you forgot to include {} in projection?".format(
    --> 140                         self.PK_FIELDS
        141                     )
        142                 )


    KeyError: "Perhaps you forgot to include ['username'] in projection?"


Whoopsie! That’s right! We need to include the ``username`` field!

.. code:: ipython3

    users.patch_one({"username": "darth_later", "email": "darthlater@example.com"})
    users.find_one({"username": "darth_later"})




.. parsed-literal::

    {'_id': ObjectId('5d98c3385d8edadaf0bb845b'),
     'username': 'darth_later',
     'email': 'darthlater@example.com'}



Okay, now let’s patch it! For starters let’s simply add a field.

.. code:: ipython3

    users.patch_one({"username": "darth_later", "email": "darthlater@example.com", "laser_sword_color": "red"})




.. parsed-literal::

    []



**One Important Thing to Note:** We need to keep everything from the
*previous* example, in that, we must include the ``username`` field
(otherwise, the ``Users`` collection will not find ``darth_vader``) and
the ``email`` (otherwise, this will be seen as a ``REMOVE``-al).

.. code:: ipython3

    users.find_one({"username": "darth_later"})




.. parsed-literal::

    {'_id': ObjectId('5d98c3385d8edadaf0bb845b'),
     'username': 'darth_later',
     'email': 'darthlater@example.com'}



What? What happened? We patched ``darth_vader``, didn’t we?

Yes, we did. So the first (and only) ``Document`` stored in the
``Users`` ``Document`` is the first one. But we do have several
revisions. These can be retrieved with the ``revisions()`` function.
This behaves just like ``find_all()`` for a standard ``Collection``.

.. code:: ipython3

    list(users.revisions({"username": "darth_later"}))




.. parsed-literal::

    [{'_id': ObjectId('5d98c3385d8edadaf0bb845b'),
      'username': 'darth_later',
      'email': 'darthlater@example.com',
      '_revision_metadata': None},
     {'_id': ObjectId('5d98c3385d8edadaf0bb845b'),
      'username': 'darth_later',
      'email': 'darthlater@example.com',
      '_revision_metadata': None,
      'laser_sword_color': 'red'}]



There we go! There’s the revision we were looking for! This may be
annoying, though to get all revisions when you most likely just want the
latest one. That’s why there’s a ``latest()`` method to make it easy.

.. code:: ipython3

    users.latest({"username": "darth_later"})




.. parsed-literal::

    {'_id': ObjectId('5d98c3385d8edadaf0bb845b'),
     'username': 'darth_later',
     'email': 'darthlater@example.com',
     '_revision_metadata': None,
     'laser_sword_color': 'red'}



Note that this assumes one document. If you want the latest revision of
*several* documents, use ``find_latest()``

.. code:: ipython3

    list(users.find_latest({"username": "darth_later"}))




.. parsed-literal::

    [{'_id': ObjectId('5d98c3385d8edadaf0bb845b'),
      'username': 'darth_later',
      'email': 'darthlater@example.com',
      '_revision_metadata': None,
      'laser_sword_color': 'red'}]



Those curious may have noticed a ``_revision_metadata`` element in the
document. That’s added by ``HistoricalCollection`` in the
``_deltas_collection`` for any additional data that you want to
associate with the document. Timestamps are an excellent usage case.

Let’s start over with no users to show an example.

.. code:: ipython3

    mongo.drop_database(DATABASE)

.. code:: ipython3

    from datetime import datetime
    from time import sleep
    import random

    SWORD_COLORS='red blue orange green transparent'.split(' ')

    for i in range(0, 5):
        timestamp = datetime.now()
        laser_sword_color = random.choice(SWORD_COLORS)
        document = {"username": "darth_later", "laser_sword_color": laser_sword_color}
        metadata = {"timestamp": timestamp}
        users.patch_one(document, metadata=metadata)
        sleep(1)

    list(users.revisions({"username": "darth_later"}))




.. parsed-literal::

    [{'_id': ObjectId('5d98c3435d8edadaf0bb845e'),
      'username': 'darth_later',
      'laser_sword_color': 'green',
      '_revision_metadata': {'timestamp': datetime.datetime(2019, 10, 5, 9, 22, 27, 994000)}},
     {'_id': ObjectId('5d98c3435d8edadaf0bb845e'),
      'username': 'darth_later',
      'laser_sword_color': 'orange',
      '_revision_metadata': {'timestamp': datetime.datetime(2019, 10, 5, 9, 22, 29, 26000)}},
     {'_id': ObjectId('5d98c3435d8edadaf0bb845e'),
      'username': 'darth_later',
      'laser_sword_color': 'blue',
      '_revision_metadata': {'timestamp': datetime.datetime(2019, 10, 5, 9, 22, 30, 29000)}},
     {'_id': ObjectId('5d98c3435d8edadaf0bb845e'),
      'username': 'darth_later',
      'laser_sword_color': 'blue',
      '_revision_metadata': {'timestamp': datetime.datetime(2019, 10, 5, 9, 22, 31, 31000)}},
     {'_id': ObjectId('5d98c3435d8edadaf0bb845e'),
      'username': 'darth_later',
      'laser_sword_color': 'green',
      '_revision_metadata': {'timestamp': datetime.datetime(2019, 10, 5, 9, 22, 32, 33000)}}]
