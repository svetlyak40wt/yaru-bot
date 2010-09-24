#!bin/python
# -*- coding: utf-8 -*-

import sys, os, xmpp, time, select

class Bot:
    """ Пингующий бот, основан на примере отсюда: http: //xmpppy.sourceforge.net/examples/xtalk.py """
    def __init__(self, jabber, remotejid):
        self.online = True
        self.jabber = jabber
        self.remotejid = remotejid

    def register_handlers(self):
        self.jabber.RegisterHandler('message', self.xmpp_message)

    def xmpp_message(self, con, event):
        import pdb;pdb.set_trace()
        type = event.getType()
        fromjid = event.getFrom().getStripped()
        if type in ['message', 'chat', None] and self.remotejid.startswith(fromjid):
            sys.stdout.write(event.getBody() + '\n')

    def stdio_message(self, message):
        m = xmpp.protocol.Message(to = self.remotejid, body = message, typ = 'chat')
        self.jabber.send(m)
        time.sleep(1)

    def xmpp_connect(self):
        con = self.jabber.connect(server = ('93.158.134.48', 5223))
        if not con:
            sys.stderr.write('could not connect!\n')
            return False

        sys.stderr.write('connected with %s\n'%con)
        auth = self.jabber.auth(jid.getNode(), jidparams['password'], resource = jid.getResource())
        if not auth:
            sys.stderr.write('could not authenticate!\n')
            return False

        sys.stderr.write('authenticated using %s\n'%auth)
        self.register_handlers()
        self.stdio_message('status')
        return con

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print "Syntax: xtalk JID"
        sys.exit(0)

    tojid = sys.argv[1]

#    jidparams = dict(
#        jid = 'yaru-bot@ya.ru/pinger',
#        password = 'Ykg7K1Mfaz',
#    )
    jidparams = dict(
        jid = 'yaru-bot-dev@ya.ru/pinger',
        password = 'lyN01xcShE',
    )

    jid = xmpp.protocol.JID(jidparams['jid'])
    cl = xmpp.Client(jid.getDomain(), debug = [])

    bot = Bot(cl, tojid)

    if not bot.xmpp_connect():
        sys.stderr.write("Could not connect to server, or password mismatch!\n")
        sys.exit(1)

    #cl.SendInitPresence(requestRoster = 0)   # you may need to uncomment this for old server

    socketlist = [cl.Connection._sock]

    while bot.online:
        (i , o, e) = select.select(socketlist, [], [], 1)
        cl.Process(1)
    cl.disconnect()

