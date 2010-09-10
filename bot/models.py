# -*- coding: utf-8 -*-
import datetime

from collections import defaultdict
from bot import db
from storm.locals import Int, Unicode, DateTime, Bool, Date
from storm.twisted.store import DeferredStore as Store
from storm.twisted.wrapper import DeferredReference, DeferredReferenceSet
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import log

MAX_DYN_ID = 99


from storm import properties, info

marker = object()


class Base( object ):
    """ Украдено отсюда: https://lists.ubuntu.com/archives/storm/2009-August/001161.html
    """
    def __getstate__( self ):
        d = {}
        for p,v in info.get_obj_info(self).variables.items():
            d[p.name] = v.get()
        return d


    def __setstate__( self, o ):
        for p,v in info.get_obj_info( self ).variables.items():
            value = o.get( p.name, marker )
            if value is marker: continue
            v.set( value, from_db=True )


    def detach( self ):
        obj_info = info.get_obj_info( self )
        store = obj_info.get('store')
        assert not obj_info in store._dirty, "Can't Detach Dirty Object"
        store._remove_from_alive( obj_info )
        store._disable_change_notification( obj_info )
        store._disable_lazy_resolving( obj_info )
        return self


    def attach( self, store ):
        if hasattr(store, 'store'):
            store = store.store

        obj_info = info.get_obj_info( self )
        obj_info['store'] = store
        store._enable_change_notification( obj_info )
        store._add_to_alive( obj_info )
        store._enable_lazy_resolving( obj_info )
        return self



class User(Base):
    __storm_table__ = 'users'
    id = Int(primary = True)
    jid = Unicode()
    subscribed = Bool(default = True)
    auth_token = Unicode(default = None)
    refresh_token = Unicode(default = None)
    created_at = DateTime(default = None)
    updated_at = DateTime(default = None)
    lastseen_at = DateTime(default = None)
    next_poll_at = DateTime(default = None)
    last_post_at = DateTime(default = None)
    last_comment_at = DateTime(default = None)

    _last_dyn_ids_cache = dict()
    _ids_cache = defaultdict(dict)

    def __init__(self, jid = None):
        self.jid = jid
        now = datetime.datetime.utcnow()
        self.created_at = now
        self.updated_at = now
        self.lastseen_at = now
        self.next_poll_at = now


    def __storm_pre_flush__(self):
        self.updated_at = datetime.datetime.utcnow()


    @inlineCallbacks
    def register_url(self, url):
        last_id = User._last_dyn_ids_cache.get(self.id)

        if last_id is None:
            result = yield self.dynamic_ids.find()
            result.order_by(DynamicID.updated_at, DynamicID.id)
            result.config(limit = 1)
            result = yield result.one()

            if result is None:
                last_id = -1
            else:
                last_id = result.id

        next_id = last_id + 1
        if next_id > MAX_DYN_ID:
            next_id = 0

        result = yield self.dynamic_ids.find(id = next_id)
        id_obj = yield result.one()

        if id_obj is None:
            id_obj = DynamicID(next_id, url)
            self.dynamic_ids.add(id_obj)
        else:
            id_obj.url = url

        User._last_dyn_ids_cache[self.id] = next_id
        User._ids_cache[self.id][next_id] = url

        returnValue(id_obj)


    @inlineCallbacks
    def unregister_id(self, dyn_id):
        if dyn_id is not None:
            if isinstance(dyn_id, DynamicID):
                dyn_id = dyn_id.id

            User._last_dyn_ids_cache[self.id] -= 1
            del User._ids_cache[self.id][dyn_id]

            results = yield self.dynamic_ids.find(id = dyn_id)
            yield results.remove()


    def get_post_url_by_id(self, id):
        return User._ids_cache[self.id].get(id)



class DynamicID(Base):
    __storm_table__ = 'ids'
    __storm_primary__ = 'user_id', 'id'
    user_id = Int(default = 0)
    id = Int()
    url = Unicode()
    updated_at = DateTime()

    user = DeferredReference(user_id, User.id)

    def __init__(self, id, url):
        self.id = id
        self.url = url

    def __storm_pre_flush__(self):
        self.updated_at = datetime.datetime.utcnow()

User.dynamic_ids = DeferredReferenceSet(User.id, DynamicID.user_id)



class Stats(Base):
    __storm_table__ = 'stats'
    date = Date(primary = True)
    new_users = Int(default = 0)
    unsubscribed = Int(default = 0)
    posts_processed = Int(default = 0)
    posts_failed = Int(default = 0)
    sent_posts = Int(default = 0)
    sent_links = Int(default = 0)

    def __init__(self):
        self.date = datetime.date.today()

