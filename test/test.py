#!../bin/python
import logging

from pdb import set_trace
from storm import tracer
from storm.locals import *
from storm.twisted.store import StorePool
from storm.twisted.wrapper import DeferredReference, DeferredReferenceSet
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

    @inlineCallbacks
    def add_link(self, url):
        link = UserLink(url)
        yield self.links.add(link)
        returnValue(link)


class UserLink(object):
    """
    create table test2(test_id integer not null, url varchar(100) not null);
    """
    __storm_table__ = 'test2'
    test_id = Int()
    url = Unicode(primary = True)
    user = DeferredReference(test_id, User.id)

    def __init__(self, url= None):
        self.url = url

User.links = DeferredReferenceSet(User.id, UserLink.test_id)



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

        @inlineCallbacks
        def add_link(store):
            results = yield store.find(User, name = u'Alexander')
            user = yield results.one()
            link = yield user.add_link(u'http://ya.ru')
            logger.debug('link: %r' % (link,))

        pool.transact(add_link)

    pool.start().addCallback(pool_started)

reactor.callLater(1, main)
reactor.callLater(5, reactor.stop)
reactor.run()
