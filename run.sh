#!/bin/bash

./kill.sh
bin/twistd --logfile=twistd.log -y bot.tac
