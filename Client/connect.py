#!/usr/bin/env python3
# vim:ft=python:ts=4:sts=4:sw=4:et:fileencoding=utf8

import requests
import logging
import os
import sys
import json

CONFIG = ()

def gettoken():
    if not os.path.isfile(CONFIG['certificate']):
        logging.error("File '"+CONFIG['certificate']+"' not found - aborting!")
        return(False)

    if not os.path.isfile(CONFIG['privatekey']):
        logging.error("File '"+CONFIG['privatekey']+"' not found - aborting!")
        return(False)

    if not os.path.isfile(CONFIG['ca']):
        logging.error("File '"+CONFIG['ca']+"' not found - aborting!")
        return(False)

    url = CONFIG['inventory'] + "/request-connection-token.php"
    logging.debug("Connecting to '" + url + "'")

    s = requests.Session()
    s.verify = CONFIG['ca']
    s.cert = ( CONFIG['certificate'], CONFIG['privatekey'] )
    r = s.get(url)
    if r.status_code != 200:
        return(False)

    data = json.loads(r.text)
    return(data)

def connect_ssh(token):
    newenv = os.environ.copy()
    newenv["ZT_DEVICE_ID"] = token

    command = "/usr/bin/ssh -D "+str(CONFIG['port'])+" -o SendEnv=ZT_DEVICE_ID "+CONFIG['accessproxy']
    logging.debug(command)
    acommand = command.split()
    os.execve(acommand[0],acommand,newenv)

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    config_file = os.path.dirname(os.path.abspath(__file__)) + "/config.json"
    logging.debug("Configfile: "+config_file)

    try:
        with open(config_file) as json_data:
            CONFIG = json.load(json_data)
    except:
        print("Unable to load config from "+config_file)
        sys.exit(1)

    token = gettoken()
    if (token):
        connect_ssh(token)

