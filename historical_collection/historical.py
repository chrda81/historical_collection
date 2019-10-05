#!/usr/bin/env python3

from pymongo.collection import Collection
import logging
from copy import deepcopy

log = logging.getLogger(__name__)


class Change:

    (INITIAL, ADD, REMOVE, UPDATE) = list("IARU")


class PatchResult(list):
    def __init__(self, *patches):
        super().__init__()

    def __str__(self):
        return "<PatchResult (patches=[{}])>".format(", ".join([str(i) for i in self]))


class HistoricalCollection(Collection):
    """Record everything associated with a collection.

    You can basically think of this as like a git repository. It behaves
    exactly like a regular collection. You can update, delete, modify as normal.
    However, an HistoricalCollection has the methods ``patch_one`` and ``patch_many``
    to store changes in the database. In this case no elements are changed, only
    its history is recorded.

    In addition, the ``revisions`` and ``latest`` methods can get a list of
    revisions of document and the latest revision (respectively).

    The only requirement for subclasses is to declare a `PK_FIELDS` attribute
    so that the HistoricalCollection can be associated with its history.

    Example
    =======

    ::
        >>> class Users(Collection):
        ... PK_FIELDS = ['username', ]
        ...
        >>> db = get_mongo_db()  # I assume you know how to do this ;)
        >>> users = Users(db)
        >>> users.patch_one({'username': 'fred', 'email': 'fred@example.com'})
        >>> list(users.revisions())
        [{'username': 'fred', 'email': 'fred@example.com', 'metadata': {}}]
        >>> users.patch_one({'username': 'fred', 'email': 'another@example.com'})
        >>> users.patch_one({'username': 'fred', 'email': 'another@example.com', 'favorite_color': blue})
        >>> list(users.revisions())
        [{'username': 'fred', 'email': 'fred@example.com', 'metadata': {}},
         {'username': 'fred', 'email': 'another@example.com', 'metadata': {}},
         {'username': 'fred', 'email': 'another@example.com', 'favorite_color': blue, 'metadata': {}}]
        >>> users.patch_one({'username': 'fred', 'username': 'fred', 'email': 'fred@example.com'})
        >>> list(users.revisions())
        [{'username': 'fred', 'email': 'fred@example.com', 'metadata': {}},
         {'username': 'fred', 'email': 'another@example.com', 'metadata': {}},
         {'username': 'fred', 'email': 'another@example.com', 'favorite_color': blue, 'metadata': {}},
         {'username': 'fred', 'username': 'fred', 'email': 'fred@example.com'}]

    So far this looks like we're just inserting a bunch of documents. However,
    there's just only one document with username ``fred``::

        >>> list(users.find_all())
        [{'username': 'fred', 'email': 'fred@example.com'}]

    Where are those revisions coming from? And what's with `metadata`?

    What Makes Up a Revision
    ========================

    Overall Structure
    -----------------

    All revisions are stored in a special ``__deltas_<collection_name>``
    collection. Each delta is a document of actions associated with the original
    document instance. The actions ``INITIAL``, ``ADD``, ``UPDATE``, and
    ``DELETE`` have further data associated with them.

    ``INITIAL`` Is basically a blank delta (unless ``metadata`` is provided.)

    ``ADD`` and ``UPDATE`` have the key and key value that was changed.
    Logically they are the same operation, but for semantics they are kept as
    separate changes.

    ``DELETE`` takes a list of fields that are to be deleted.

    In addition to the actions, the original document's primary keys are stored
    in the database. Note that this is not Mongo's ``_id`` field unless
    specified.

    Metadata
    --------

    This is entirely optional. ``metadata`` is there to provide a means to
    add extra data to each revision. For example, if you wanted to add a
    timestamp to the revision::

        >>> users.patch_one({'username': 'david'}, metadata={'timestmap': datetime.now()})
        >>> users.revisions({'username': 'david'})
        [{'username': 'david', 'metadata': {'timestamp': datetime(2019, 9, 10, 12, 14, 19)}}]
    """

    def __new__(cls, *args, **kwargs):
        """Mainly checks to ensure all subclasses have a PK_FIELDS attribute."""
        if not hasattr(cls, "PK_FIELDS"):
            raise AttributeError("{} is missing PK_FIELDS".format(cls.__name__))
        return super().__new__(cls)

    @property
    def _deltas_name(self):
        return "__deltas_{}".format(self.name)

    @property
    def _deltas_collection(self):
        """Shortcut property to access the `deltas` collection."""
        return self.database[self._deltas_name]

    def __init__(self, *args, **kwargs):
        """Construct a new HistoricalCollection.

        :param db: Mongo database instance.

        :param name: (Optional) If not given, will default to the class name.
        """
        if "name" not in kwargs:
            kwargs["name"] = type(self).__name__
        super().__init__(*args, **kwargs)

    def _document_filter(self, document):
        """Create a document filter based on the class's PK_FIELDS."""
        try:
            return dict([(k, document[k]) for k in self.PK_FIELDS])
        except KeyError as e:
            if bool(set(e.args) & set(self.PK_FIELDS)):
                raise KeyError(
                    "Perhaps you forgot to include {} in projection?".format(
                        self.PK_FIELDS
                    )
                )

    def revise(self, instance, delta):
        """Apply a delta to an instance, returning a new instance."""
        inst = deepcopy(instance)
        if Change.INITIAL in delta:
            return inst
        for (k, v) in delta.get(Change.ADD, {}).items():
            inst[k] = v
        for (k, v) in delta.get(Change.UPDATE, {}).items():
            inst[k] = v
        for k in delta.get(Change.REMOVE, []):
            if k not in inst:
                log.warning(
                    "'%s' wasn't in instance %s. This was unexpected, so skipping.",
                    k,
                    instance,
                )
            else:
                del inst[k]
        return inst

    def get_deltas(self, *args, **kwargs):
        """ Get a list of deltas for fltr. """
        return self._deltas_collection.find(*args, **kwargs)

    def revisions(self, *args, **kwargs):
        fltr = None
        if len(args):
            fltr = args[0]
        instances = super().find(*args, **kwargs)
        for instance in instances:
            deltas_filter = self._document_filter(instance)
            for change in self._deltas_collection.find(deltas_filter):
                instance = self.revise(instance, change["deltas"])
                instance["_revision_metadata"] = change.get("metadata", None)
                # yield instance
                if (fltr or instance) == fltr:  # kinda like a `dict in dict`
                    yield instance

    def latest(self, *args, **kwargs):
        revisions = list(self.revisions(*args, **kwargs))
        if len(revisions) > 0:
            return revisions[-1]
        return revisions

    def find_latest(self, *args, **kwargs):
        """ Find the latest revision. """
        fltr = None
        if len(args):
            fltr = args[0]
        rev = kwargs.pop("revision", None)
        originals = super().find(*args, **kwargs)
        for original in originals:
            fltr = self._document_filter(original)
            revisions = list(self.revisions(fltr))  # TODO: Count revisions
            if rev is None:
                yield revisions[-1]
            elif rev > len(revisions):
                continue
            if rev:
                yield revisions[rev]

    def _check_key(self, *docs):
        """Verify that the same `PK_FIELDS` field is present for every doc."""
        pks = set()
        for pk in self.PK_FIELDS:
            for (i, d) in enumerate(docs):
                try:
                    pks.add(d[pk])
                except KeyError as e:
                    raise AttributeError("Keys not present: {}".format(pk))
        if len(list(pks)) > 1:
            raise AttributeError("Differing keys present: {}".format(list(pks)))

    def _get_additions(self, latest, doc):
        self._check_key(latest, doc)
        latest_keyset = set(latest.keys())
        doc_keyset = set(doc.keys())
        return dict([(k, doc[k]) for k in doc_keyset - latest_keyset])

    def _get_updates(self, latest, doc):
        return dict(
            [(k, v) for (k, v) in doc.items() if k in latest and latest[k] != doc[k]]
        )

    def _get_removals(self, latest, doc):
        self._check_key(latest, doc)
        # This will get all keys that are NOT latest, but are in doc.
        # We'll be skipping '_id', since that's an internal MongoDB key.
        return [
            x
            for x in list(set(latest.keys()) - set(doc.keys()))
            if x not in ("_id", "_revision_metadata")
        ]

    def _add_patch(self, patch):
        return self._deltas_collection.insert_one(patch)

    def _create_deltas(self, last, current):
        return {
            Change.ADD: self._get_additions(last, current),
            Change.UPDATE: self._get_updates(last, current),
            Change.REMOVE: self._get_removals(last, current),
        }

    def _create_patch(self, fltr, deltas=None, metadata=None):
        patch = deepcopy(fltr)
        patch["deltas"] = None
        if deltas:
            patch["deltas"] = deltas
        if metadata:
            patch["metadata"] = metadata
        return patch

    def patch_one(self, *args, **kwargs):
        doc = args[0]
        metadata = kwargs.pop("metadata", None)
        fltr = self._document_filter(doc)
        latest = self.latest(fltr)
        insert_result = None
        if latest is None or (not len(latest)):
            log.debug("Inserting %s", doc)
            if super().insert_one(*args, **kwargs):
                patch = self._create_patch(
                    fltr, deltas={Change.INITIAL: None}, metadata=metadata
                )
                ptch = self._add_patch(patch)
                return PatchResult(ptch)
            return None  # if we couldn't create it for some reason.
        else:
            deltas = self._create_deltas(latest, doc)
            patch = self._create_patch(fltr, deltas, metadata)
            return PatchResult(self._add_patch(patch))

    def patch_many(self, docs, *args, **kwargs):
        result = PatchResult()
        for doc in docs:
            one = self.patch_one(doc, *args, **kwargs)
            result.append(one)
        return result
