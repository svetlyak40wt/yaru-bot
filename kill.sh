#!/bin/bash

if [ -e twistd.pid ]; then
    kill -9 `cat twistd.pid`
fi

