# -*- encoding: utf-8 -*-
import datetime

from . import db
from . models import Stats
from twisted.internet.defer import inlineCallbacks
from twisted.python import log
from pdb import set_trace

_default_stats = dict(
    date = datetime.date.today(),
    new_users = 0,
    unsubscribed = 0,
    posts_processed = 0,
    posts_failed = 0,
    sent_posts = 0,
    sent_links = 0,
)

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

