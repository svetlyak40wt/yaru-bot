# -*- coding: utf-8 -*-
from twisted.python import log

from storm import tracer
from copy import copy
from functools import wraps, partial
from storm.locals import create_database
from storm.twisted.store import StorePool

pool = None
database = None

def init(cfg):
    global pool, database

    if 'debug' in cfg:
        debug = cfg.pop('debug')
    else:
        debug = False

    tracer.debug(debug)

    values = dict(driver = 'mysql', host = 'localhost', db = 'yaru_bot', user = 'yaru_bot', passwd = 'yaru_bot')
    values.update(cfg)
    uri = '%(driver)s://%(user)s:%(passwd)s@%(host)s/%(db)s' % values

    database = create_database(uri)
    pool = StorePool(database)
    return pool.start()

