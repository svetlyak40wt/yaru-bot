#!../bin/python
import logging

from pdb import set_trace
from storm import tracer
from storm.locals import *
from storm.twisted.store import StorePool
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import reactor

logging.basicConfig(level = logging.DEBUG)
logger = logging.getLogger()



class User(object):
    """
    create table test(id integer not null auto_increment primary key, name varchar(100));
    """
    __storm_table__ = 'test'
    id = Int(primary = True)
    name = Unicode()

    def __init__(self, name = None):
        self.name = name


def main():
    logger.debug('main')
    tracer.debug(True)
    database = create_database('mysql://yaru_bot:yaru_bot@localhost/yaru_bot')
    pool = StorePool(database)

    def pool_started(result):
        logger.debug('pool_started')

        @inlineCallbacks
        def add_user(store, name):
            user = User(name)
            yield store.add(user)

        @inlineCallbacks
        def add_users(store):
            yield add_user(store, u'Alexander')
            yield add_user(store, u'Maria')

        pool.transact(add_users)

    pool.start().addCallback(pool_started)

reactor.callLater(1, main)
reactor.callLater(5, reactor.stop)
reactor.run()
