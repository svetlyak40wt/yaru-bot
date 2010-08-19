# -*- coding: utf-8 -*-
import datetime

from collections import defaultdict
from bot import db
from hashlib import md5
from pdb import set_trace
from storm.locals import Int, Unicode, DateTime, Bool
from storm.twisted.wrapper import DeferredReference, DeferredReferenceSet
from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.python import log

HASH_LENGTH = 4
POST_HISTORY_LENGTH = 100


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


    def attach( self, store ):
        obj_info = info.get_obj_info( self )
        obj_info['store'] = store
        store._enable_change_notification( obj_info )
        store._add_to_alive( obj_info )
        store._enable_lazy_resolving( obj_info )



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

    _posts_cache = defaultdict(dict)

    def __init__(self, jid = None):
        self.jid = jid
        now = datetime.datetime.utcnow()
        self.created_at = now
        self.updated_at = now
        self.lastseen_at = now


    @inlineCallbacks
    def register_post(self, url):
        post_link = PostLink(url)
        yield self.posts.add(post_link)
        User._posts_cache[self.id][url] = True
        returnValue(post_link)


    def is_post_registered(self, url):
        return url in User._posts_cache[self.id]



class PostLink(Base):
    __storm_table__ = 'post_links'
    url = Unicode(primary = True)
    hash = Unicode()
    user_id = Int()
    user = DeferredReference(user_id, User.id)
    created_at = DateTime()

    def __init__(self, url):
        self.url = unicode(url)
        self.hash = unicode(md5(url).hexdigest()[:HASH_LENGTH])
        self.created_at = datetime.datetime.utcnow()


User.posts = DeferredReferenceSet(User.id, PostLink.user_id)

