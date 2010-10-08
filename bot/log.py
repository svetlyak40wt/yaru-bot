from __future__ import absolute_import

from twisted.python import log
from . utils import force_str

def err(_stuff = None, _why = None, **kw):
    return log.err(_stuff = _stuff, _why = force_str(_why), **kw)

msg = log.msg
