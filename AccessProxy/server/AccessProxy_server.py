#!/usr/bin/env python3
# vim:ft=python:ts=4:sts=4:sw=4:et:fileencoding=utf8

import socket
import threading
import logging
import sys
import os
import json
import re
import mysql.connector
import shlex
import subprocess

CONFIG = ()

class ZeroTrustConnection:
    def __init__(self,userid,deviceid):
        logging.debug("Constructor")
        self.userid = userid
        self.deviceid = deviceid
        self.chainname = (userid+"-"+deviceid)[:28]

        self.db = mysql.connector.connect(
            host = CONFIG['dbhost'],
            user = CONFIG['dbuser'],
            password = CONFIG['dbpass'],
            database = CONFIG['dbname']
        )

        # Initialize Trustlevel
        self.usertrust = -1
        self.devicetrust = -1

    def __del__(self):
        logging.debug("Destructor")
        self.db.close()

    def evaluate_usertrust(self):
        logging.debug("Evaluating trust for user "+self.userid)
        sql = "select currenttrustlevel from users where name = %s"
        logging.debug(sql)
        parameters = (self.userid, )
        cursor = self.db.cursor(prepared=True)
        cursor.execute(sql, parameters)
        data = cursor.fetchone()
        if data:
            self.usertrust = data[0]
        cursor.close()

        logging.debug("Trust after evaluation: "+str(self.usertrust))

    def evaluate_devicetrust(self):
        logging.debug("Evaluating trust for device "+self.deviceid)
        sql = """
select a.currenttrustlevel
from assets a inner join user_assets ua on ua.asset_id = a.id inner join users u on ua.user_id = u.id 
where u.name = %s 
and a.connection_token = %s
and date_add(a.connection_token_issued, INTERVAL """ + str(CONFIG['tokenlifetime']) + " second) > now()"

        logging.debug(sql)
        cursor = self.db.cursor(prepared=True)
        parameters = (self.userid, self.deviceid)
        logging.debug(parameters)
        cursor.execute(sql, parameters)
        data = cursor.fetchone()
        if data:
            self.devicetrust = data[0]
        else:
            self.devicetrust = -1
        logging.debug("Trust after evaluation: "+str(self.devicetrust))

    def remove_firewall_rules(self):
        logging.debug("removing firewall rules for user: "+ self.userid + ", device: "+ self.deviceid)

        command = "iptables -D "+ CONFIG['userchain_name'] +" -j "+self.chainname + " -m owner --uid-owner "+self.userid
        logging.debug(command)
        if CONFIG['doiptables']:
            subprocess.run(shlex.split(command))

        command = "iptables -F "+self.chainname
        logging.debug(command)
        if CONFIG['doiptables']:
            subprocess.run(shlex.split(command))

        command = "iptables -X "+self.chainname
        logging.debug(command)
        if CONFIG['doiptables']:
            subprocess.run(shlex.split(command))

    def create_firewall_rules(self, rules):
        logging.debug("creating firewall rules for user: " + self.userid + ", device: " + self.deviceid)

        chainname=self.userid+"-"+self.deviceid
        logging.debug("creating chain: "+self.chainname)
        command = "iptables -N "+self.chainname
        logging.debug(command)
        if CONFIG['doiptables']:
            subprocess.run(shlex.split(command))

        for rule in rules:
            command = "iptables -A "+ self.chainname + " -m " + rule['protocol'].lower() + " -p " + rule['protocol'] + " -d " + rule['destination'] + " --dport " + str(rule['port']) + " -m conntrack --ctstate NEW -j ACCEPT"
            logging.debug(command)
            if CONFIG['doiptables']:
                subprocess.run(shlex.split(command))

        command = "iptables -I "+ CONFIG['userchain_name'] +" -j "+self.chainname + " -m owner --uid-owner "+self.userid
        logging.debug(command)
        if CONFIG['doiptables']:
            subprocess.run(shlex.split(command))

    def determine_ruleset(self):
        sql = """
select ah.protocol 
     , ah.port 
     , h.ipv4address
     , u.name
     , a.name
     , a.requiredusertrust
     , a.requireddevicetrust
from application_hosts ah inner join hosts h on ah.host_id = h.id 
                          inner join applications a on ah.application_id = a.id 
                          inner join application_groups ag on ag.application_id = a.id 
                          inner join user_groups ug on ug.group_id = ag.group_id 
                          inner join users u on ug.user_id = u.id
where u.name =  %s
and a.requiredusertrust <= %s
and a.requireddevicetrust <= %s
"""
        logging.debug(sql)
        parameters = (self.userid, self.usertrust, self.devicetrust)
        cursor = self.db.cursor(prepared=True)
        cursor.execute(sql, parameters)
        data = cursor.fetchall()
        rules = []
        for row in data:
            rule = { "protocol": row[0].decode(), "port": row[1], "destination": row[2].decode() }
            logging.debug(rule)
            rules.append(rule)

        cursor.close()
        return(rules)

    def login(self):
        logging.debug("Logging in user "+self.userid+" on device "+self.deviceid)

        self.remove_firewall_rules()
        self.evaluate_usertrust()
        if self.usertrust > -1:
            self.evaluate_devicetrust()
            if self.devicetrust > -1:
                logging.debug("Determine ruleset for user (usertrust) " + self.userid + "("+ str(self.usertrust) +"), device (devicetrust) " + self.deviceid + "(" + str(self.devicetrust) +")")
                rules = self.determine_ruleset()
                if rules:
                    self.create_firewall_rules(rules)
            else:
                return(False)
        else:
            return(False)

        return(True)

    def reauthenticate(self):
        logging.debug("Reauthenticating user "+self.userid+" on device "+self.deviceid)
        sql = "update assets set connection_token_issued = now() where connection_token = %s;"
        logging.debug(sql)
        parameters = (self.deviceid, )
        cursor = self.db.cursor(prepared=True)
        cursor.execute(sql, parameters)
        self.db.commit()

        rc = self.login()
        return(rc)

    def logout(self):
        logging.debug("Logging out user "+self.userid+" on device "+self.deviceid)
        self.remove_firewall_rules()
        sql = "update assets set connection_token_issued = %s where connection_token = %s;"
        logging.debug(sql)
        parameters = ('1970-01-01 00:00:00', self.deviceid)
        cursor = self.db.cursor(prepared=True)
        cursor.execute(sql, parameters)
        self.db.commit()

        return(True)

class ClientThread(threading.Thread):

    def __init__(self,clientAddress,clientsocket):
        threading.Thread.__init__(self)

        self.csocket = clientsocket
        self.clientAddress = clientAddress

    def run(self):
        msg = ''

        while True:
            data = self.csocket.recv(2048)
            msg = data.decode().strip()

            data=msg.split(';')
            if len(data) != 4:
                logging.debug("Incorrect number of fields - retry")
                self.csocket.send(bytes("400 - Bad Request","UTF-8"))
                break

            # Check input
            # Action
            if data[0] != "login" and data[0] != "logout" and data[0] != "reauth":
                logging.debug("Incorrect data[0] - retry")
                self.csocket.send(bytes("405 - Method not allowed","UTF-8"))
                break
            # Userid
            to_test = re.compile('^[A-Za-z0-9]+$')
            if not to_test.match(data[1]):
                logging.debug("Incorrect data[1] - retry")
                self.csocket.send(bytes("400 - Bad Request","UTF-8"))
                break
            # ClientId
            if not to_test.match(data[2]):
                logging.debug("Incorrect data[2] - retry")
                self.csocket.send(bytes("400 - Bad Request","UTF-8"))
                break
            # Shared secret
            if data[3] != CONFIG['secret']:
                logging.debug("Incorrect data[3] - retry")
                self.csocket.send(bytes("511 - Network Authentication Required","UTF-8"))
                break

            ztc = ZeroTrustConnection(data[1], data[2])
            if data[0] == 'login':
                if ztc.login():
                    self.csocket.send(bytes("200 - OK","UTF-8"))
                else:
                    self.csocket.send(bytes("403.1 - Forbidden","UTF-8"))
                break

            if data[0] == 'logout':
                if ztc.logout():
                    self.csocket.send(bytes("200 - OK","UTF-8"))
                else:
                    self.csocket.send(bytes("500 - Internal Server Error","UTF-8"))
                break
				
            if data[0] == 'reauth':
                if ztc.reauthenticate():
                    self.csocket.send(bytes("200 - OK","UTF-8"))
                else:
                    self.csocket.send(bytes("403.2 - Forbidden", "UTF-8"))
                break

        print("Client at ", self.clientAddress , " disconnected...")
        self.csocket.shutdown(socket.SHUT_RDWR)
        self.csocket.close()
    
def run_server(ip, port):
    logging.debug("Creating socket")
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    logging.debug("Setting socket options")
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    logging.debug("Binding socket to "+ip+":"+str(port))
    server.bind((ip, port))

    logging.info("Server started")
    logging.info("Waiting for client request..")

    while True:
        server.listen(1)
        logging.debug("Client accept")
        clientsock, clientAddress = server.accept()
        print(clientAddress)
        logging.debug("Create thread")
        newthread = ClientThread(clientAddress, clientsock)
        logging.debug("Start thread")
        newthread.start()

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    config_file = os.path.dirname(os.path.abspath(__file__)) + "/config.json"
    logging.debug("Configfile: "+config_file)

    try:
        with open(config_file) as json_data:
            CONFIG = json.load(json_data)
    except:
        logging.error("Unable to load config from "+config_file)
        sys.exit(1)

    run_server(CONFIG['ip_address'], CONFIG['port'])

