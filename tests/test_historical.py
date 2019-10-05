#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Tests for `freelancer_analysis` package."""

import unittest
import os
import sys
from copy import deepcopy
import random
from pymongo import MongoClient
from pymongo.results import InsertOneResult, InsertManyResult

from faker import Faker

import logging
import logging.config

from historical_collection.historical import HistoricalCollection, Change, PatchResult

LOGGING_FORMAT = "[%(levelname)s] %(filename)s:%(lineno)d %(message)s"
DEFAULT_MONGO_CLIENT_URL = "mongodb://localhost:27017/"

logging.basicConfig(level=logging.DEBUG, format=LOGGING_FORMAT)
log = logging.getLogger(__name__)

fake = Faker()


def random_pop(lst):
    return lst.pop(lst.index(random.choice(lst)))


class TestHistoricalCollection(unittest.TestCase):
    class MyCollection(HistoricalCollection):
        PK_FIELDS = ["id"]

    def setUp(self):
        self.mongo = MongoClient(DEFAULT_MONGO_CLIENT_URL)
        self.dbname = fake.word()
        self.db = self.mongo[self.dbname]
        log.debug("Created test database %s", self.dbname)

    def tearDown(self):
        self.mongo.drop_database(self.db)
        log.debug("Destroyed test database %s", self.dbname)

    def mess_with_dict(self, d):
        """Randomize a dict by adding/updating/deleting elements."""
        d = deepcopy(d)
        valid_keys = [
            k
            for k in d
            if k not in TestHistoricalCollection.MyCollection.PK_FIELDS + ["_id"]
        ]
        to_remove = random_pop(valid_keys)
        to_update = random_pop(valid_keys)
        to_add = fake.word()
        log.debug("removing %s", to_remove)
        del d[to_remove]
        log.debug("adding %s", to_add)
        d[to_add] = 1
        log.debug("to_update %s", to_update)
        d[to_update] = fake.pylist(1, False, int, bool, float, str)
        return d

    def test_check_key(self):
        """Private function _check_key raises Exception if PK is not in doc."""
        collection = TestHistoricalCollection.MyCollection(self.db)
        with self.assertRaises(AttributeError):
            collection._check_key({"a": "b"})
        with self.assertRaises(AttributeError):
            collection._check_key({"id": 4}, {"a": 1, "b": 2})
        with self.assertRaises(AttributeError):
            collection._check_key({"id": 4}, {"id": 3})

    def test_logic(self):
        """Basic delta logic is calculated successfully."""
        collection = TestHistoricalCollection.MyCollection(self.db)
        cid = 12
        first = {"id": cid, "a": 1, "b": 2, "c": 3}
        second = {"id": cid, "b": "something", "c": 3, "d": 4}
        expected = {"id": cid, "U": {"b": "something"}, "A": {"d": 4}, "R": ["a"]}
        additions = collection._get_additions(first, second)
        updates = collection._get_updates(first, second)
        removals = collection._get_removals(first, second)
        self.assertEqual(additions, expected["A"])
        self.assertEqual(updates, expected["U"])
        self.assertEqual(removals, expected["R"])

    def test_create_pach(self):
        """A patch can be created based on two differing documents."""
        collection = TestHistoricalCollection.MyCollection(self.db)
        cid = 12
        first = {"id": cid, "a": 1, "b": 2, "c": 3}
        second = {"id": cid, "b": "something", "c": 3, "d": 4}
        expected = {
            "id": cid,
            "deltas": {
                Change.ADD: {"d": 4},
                Change.UPDATE: {"b": "something"},
                Change.REMOVE: ["a"],
            },
        }
        deltas = collection._create_deltas(first, second)
        patch = collection._create_patch({"id": cid}, deltas)
        self.assertDictEqual(expected, patch)

    @unittest.skip("might not be failing")
    def test_gen_patch_series(self):
        collection = TestHistoricalCollection.MyCollection(self.db)
        fltr = {"id": 1}
        d1 = {"id": 1, "a": 1, "b": 2, "c": 3, "d": 4, "e": 5}
        collection.patch_one(d1)
        d2 = {"id": 1, "a": 1, "c": 3, "d": 4, "e": 5}
        deltas = collection._create_deltas(d1, d2)

    def test_patch_series(self):
        """A patch can successfuly be applied."""
        collection = TestHistoricalCollection.MyCollection(self.db)
        cid = 12
        fltr = {"id": cid}
        first = {"id": cid, "a": 1, "b": 2, "c": 3}
        changes = []
        change = first
        # This one should be an insertion
        collection.patch_one(first)
        previous = None
        for i in range(0, 5):
            change = self.mess_with_dict(change)
            if previous is not None:
                deltas = collection._create_deltas(previous, change)
                patch = collection._create_patch(fltr, deltas)
                log.debug("+ Deltas: %s", deltas)
                log.debug("+ Patch: %s", patch)
            log.debug("+ New dict: %s", change)
            collection.patch_one(change)
            previous = change
        revisions = list(collection.revisions(fltr))
        last_revision = collection.latest(fltr)
        self.assertEqual(len(list(set([str(r) for r in revisions]))), 6)
        self.assertEqual(len(revisions), 6)
        del last_revision["_revision_metadata"]
        self.assertDictEqual(last_revision, change)

    def test_find_revisions(self):
        """More than one revision can be found if patch_*() is called."""
        collection = TestHistoricalCollection.MyCollection(self.db)
        cid = 12
        fltr = {"id": cid}
        first = {"id": cid, "a": 1, "b": 2, "c": 3}
        changes = []
        change = first
        # This one should be an insertion
        collection.patch_one(first)
        previous = None
        for i in range(0, 5):
            change = self.mess_with_dict(change)
            changes.append(change)
            log.debug("+ New dict: %s", change)
            collection.patch_one(change)
        # pick a random filter
        picked = random.choice(changes)
        k = random.choice([k for k in picked.keys() if k not in ("_id", "id")])
        fltr = {k: picked[k]}
        log.debug("filtering with %s", fltr)
        collection.find(fltr)

    def test_revision_metadata(self):
        """Metadata is returned for revisions and has changed between revisions."""
        collection = TestHistoricalCollection.MyCollection(self.db)
        cid = 12
        fltr = {"id": cid}
        first = {"id": cid, "a": 1, "b": 2, "c": 3}
        changes = []
        change = first
        # This one should be an insertion
        metadata = {"i": 0}
        collection.patch_one(first, metadata=metadata)
        previous = None
        for i in range(0, 5):
            change = self.mess_with_dict(change)
            if previous is not None:
                deltas = collection._create_deltas(previous, change)
                patch = collection._create_patch(fltr, deltas)
                log.debug("+ Deltas: %s", deltas)
                log.debug("+ Patch: %s", patch)
            log.debug("+ New dict: %s", change)
            metadata["i"] += 1
            collection.patch_one(change, metadata=metadata)
            previous = change
        revisions = list(collection.revisions(fltr))
        for (i, rev) in enumerate(revisions):
            self.assertIn("_revision_metadata", rev)
            self.assertIn("i", rev["_revision_metadata"])
            log.debug("Metadata: %d", rev["_revision_metadata"]["i"])
            self.assertEqual(rev["_revision_metadata"], {"i": i})

    def test_patch_many(self):
        """Many patches can be applied to a document."""
        collection = TestHistoricalCollection.MyCollection(self.db)
        initial = [fake.pydict(10, True, int, float, bool, str) for i in range(0, 10)]
        for i in initial:
            i["id"] = fake.pyint()
        changed = []
        for item in initial:
            if fake.boolean():
                changed.append(self.mess_with_dict(item))
        assert changed != initial
        log.debug("test patch: initial=%s", initial)
        log.debug("test patch: changed=%s", changed)
        result = collection.patch_many(initial)
        self.assertIsInstance(result, PatchResult)
        self.assertTrue(
            all([isinstance(subresult, PatchResult) for subresult in result])
        )
        result = collection.patch_many(changed)
        self.assertTrue(isinstance(result, PatchResult))
        self.assertEqual(len(result), len(changed))
