# -*- encoding: utf-8 -*-
import datetime

from . import db
from . models import Stats
from storm.properties import PropertyColumn
from twisted.internet.defer import inlineCallbacks
from twisted.python import log


_default_stats = {}

for key in dir(Stats):
    value = getattr(Stats, key)
    if isinstance(value, PropertyColumn):
        _default_stats[key] = value.variable_factory()._value

_default_stats['date'] = datetime.date.today()

STATS = _default_stats.copy()
_previous_stats = _default_stats.copy()


def save_stats():
    log.msg('Saving stats')
    @inlineCallbacks
    def _do(store):
        global STATS
        today = datetime.date.today()

        if STATS != _previous_stats:
            stats = yield store.find(Stats, date = today)
            stats = yield stats.one()
            if stats is None:
                stats = Stats()

            for key, value in STATS.items():
                setattr(stats, key, value)

            yield store.add(stats)

            if STATS['date'] != today:
                STATS = _default_stats.copy()
                STATS['date'] = today
    db.pool.transact(_do)


def load_stats():
    log.msg('Loading stats')

    @inlineCallbacks
    def _do(store):
        stats = yield store.find(Stats, date = datetime.date.today())
        stats = yield stats.one()
        if stats is not None:
            for key in STATS.keys():
                STATS[key] = getattr(stats, key)
    db.pool.transact(_do)

