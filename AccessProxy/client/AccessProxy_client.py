#!/usr/bin/env python3
# vim:ft=python:ts=4:sts=4:sw=4:et:fileencoding=utf8

import socket
import logging
import sys
import os
import json
import signal
from datetime import datetime
from time import sleep

CONFIG = ()
USERID = "";
DEVICEID = "";

def communicate(verb):
    message = verb+";"+USERID+";"+DEVICEID+";"+CONFIG['secret']

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect((CONFIG['ip_address'], CONFIG['port']))

    client.sendall(bytes(message, "UTF-8"))
    response = client.recv(1024)
    client.close()

    response = response.decode().strip()
    logging.info(response)

    if response[:3] == "200":
        return(True)

    return(False)

def login():
    logging.info("Starting session for user " + USERID + " from device " + DEVICEID)
    if communicate('login'):
        logging.info("Session started successfully")
        return(True)
    else:
        logging.error("Error starting session")
        return(False)

def logout():
    logging.info("Terminating session of user " + USERID + " from device " + DEVICEID)
    if communicate('logout'):
        logging.info("Session terminated successfully")
        return(True)
    else:
        logging.error("Error terminating session")
        return(False)

def reauth():
    logging.info("Reauthenticating session for user " + USERID + " from device " + DEVICEID)
    if communicate('reauth'):
        logging.info("Session reauthenticated successfully")
        return(True)
    else:
        logging.error("Error reauthenticating session")
        return(False)

def exithandler(_signo, _stackframe):
    logging.debug("exithandler")
    logout()
    sys.exit(0)

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

    if 'USER' in os.environ:
        USERID = os.environ['USER']
    else:
        logging.error("USER not found in environment")
        sys.exit(1)

    if 'ZT_DEVICE_ID' in os.environ:
        DEVICEID = os.environ['ZT_DEVICE_ID']
    else:
        logging.error("ZT_DEVICE_ID not found in environment")
        sys.exit(1)

    if login():
        signal.signal(signal.SIGINT, exithandler)
        signal.signal(signal.SIGTERM, exithandler)
        signal.signal(signal.SIGHUP, exithandler)

        anchor = datetime.today().timestamp()
        while True:
            # Reauthentication
            if datetime.today().timestamp() > (anchor + CONFIG['reauth']):
                print()
                if reauth():
                    anchor = datetime.today().timestamp()
                else:
                    sys.exit(1)
            print('.', end='',flush=True)
            sleep(1)
    else:
        sys.exit(1)
