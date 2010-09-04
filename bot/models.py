# -*- coding: utf-8 -*-
import datetime

from collections import defaultdict
from bot import db
from hashlib import md5
from pdb import set_trace
from storm.locals import Int, Unicode, DateTime, Bool
from storm.twisted.store import DeferredStore as Store
from storm.twisted.wrapper import DeferredReference, DeferredReferenceSet
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import log

HASH_LENGTH = 3


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

    _posts_cache = defaultdict(dict)
    _hash_cache = defaultdict(dict)

    def __init__(self, jid = None):
        self.jid = jid
        now = datetime.datetime.utcnow()
        self.created_at = now
        self.updated_at = now
        self.lastseen_at = now
        self.next_poll_at = now


    @inlineCallbacks
    def register_post(self, url):
        hash = yield self._create_hash(url)

        post_link = PostLink(url, hash)
        yield self.posts.add(post_link)
        User._posts_cache[self.id][url] = True
        User._hash_cache[self.id][post_link.hash] = url
        returnValue(post_link)


    @inlineCallbacks
    def unregister_post(self, hash):
        results = yield self.posts.find(PostLink.hash == hash)
        post_link = yield results.one()

        if post_link is not None:
            yield results.remove()
            del User._posts_cache[self.id][post_link.url]
            del User._hash_cache[self.id][post_link.hash]


    def is_post_registered(self, url):
        return url in User._posts_cache[self.id]


    def get_post_url_by_hash(self, hash):
        return User._hash_cache[self.id].get(hash)


    @inlineCallbacks
    def _create_hash(self, url):
        hash = unicode(md5(url).hexdigest()[:HASH_LENGTH])
        yield self.unregister_post(hash)
        returnValue(hash)




class PostLink(Base):
    __storm_table__ = 'post_links'
    __storm_primary__ = 'user_id', 'url'
    user_id = Int()
    url = Unicode()
    hash = Unicode()
    user = DeferredReference(user_id, User.id)
    created_at = DateTime()

    def __init__(self, url, hash):
        self.url = unicode(url)
        self.hash = hash
        self.created_at = datetime.datetime.utcnow()


User.posts = DeferredReferenceSet(User.id, PostLink.user_id)

