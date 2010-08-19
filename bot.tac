"""
Jabber bot to serve http://wow.ya.ru service.
"""

import locale
import yaml

from bot import db
from bot.protocols import MessageProtocol, PresenceProtocol
from bot.web import WebRoot
from bot.scheduler import Scheduler
from pdb import set_trace
from twisted.application import service
from twisted.application.internet import TCPServer
from twisted.internet import task
from twisted.internet.defer import DebugInfo
from twisted.python import log, failure
from twisted.web import server
from twisted.words.protocols.jabber.jid import JID
from wokkel.disco import DiscoHandler
from wokkel.generic import VersionHandler
from wokkel import client


# Configuration parameters

locale.setlocale(locale.LC_ALL, '')

config = yaml.load(open('config.yml'))

db_started = db.init(config['database'])

THIS_JID = JID(config['bot']['jid'])
HOST = config['bot'].get('host', None)
PORT = config['bot'].get('port', 5222)
SECRET = config['bot']['pass']
LOG_TRAFFIC = True


# Set up the Twisted application

application = service.Application("YaRu Bot")

bot = client.XMPPClient(THIS_JID, SECRET, host = HOST, port = PORT)
bot.logTraffic = LOG_TRAFFIC
bot.setServiceParent(application)
bot.send('<presence/>') # Hello, OpenFire!

message_protocol = MessageProtocol(config)
message_protocol.setHandlerParent(bot)

def init_scheduler(ignore):
    scheduler = Scheduler(config, message_protocol)

    def process_new_posts():
        try:
            scheduler.process_new_posts()
        except Exception:
            DebugInfo().failResult = failure.Failure()

    task.LoopingCall(process_new_posts).start(
        config['bot']['polling_interval'],
        now = False
    )

db_started.addCallback(init_scheduler)

presence_protocol = PresenceProtocol(config)
presence_protocol.setHandlerParent(bot)


DiscoHandler().setHandlerParent(bot)
VersionHandler('yaru-bot', '0.1.0').setHandlerParent(bot)

web_site = server.Site(WebRoot(message_protocol))
web_server = TCPServer(8081, web_site)
web_server.setServiceParent(application)
