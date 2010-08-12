#!/bin/bash

if [ -e twistd.pid ]; then
    kill `cat twistd.pid`
fi

bin/twistd --logfile=twistd.log -y bot.tac
