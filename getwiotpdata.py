# *****************************************************************************
# Copyright (c) 2018 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# Contributors:
#    Ranjan Dasgupta             - Initial drop for Alpha release
#
# *****************************************************************************

#
# Connector application used for inegrating Watson IoT Platform with QRadar
#

import os
import logging
import logging.handlers
from datetime import datetime
import time
import threading
from threading import Thread
from threading import Lock
import sys
import json
import re
import ibmiotf
import ibmiotf.application
import ConfigParser
import signal
import socket

# SYSLOG setup
# Application names - 
APPNAMECONNECTION = "wiotp_qradar:1.0:Connection "
# APPNAMEDEVICEMGMT = "wiotp_qradar:1.0:DevMgmt "
sysLogger = logging.getLogger('WIOTPSYSLOG')

# Setup Application logger to console
applogger = logging.getLogger('qradar-connector')
applogger.setLevel(logging.DEBUG)
conlogger = logging.StreamHandler()
conlogger.setLevel(logging.DEBUG)
applogger.addHandler(conlogger)

# Variables to control WIoTP API invocation
# 
# Variables used to control time period in GET /connection/logs API
# Time periods ar in ISO8601 format
curTime = time.gmtime()
lastTime = curTime
curISOTime = time.strftime("%Y-%m-%dT%H:%M:%S", curTime)
lastISOTime = curISOTime

# compile regular expressions
authREObj = re.compile(r'(.*): ClientID=\S(.*?)\S, ClientIP=(.*)')
connREObj = re.compile(r'^Closed\sconnection\sfrom\s(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\.(.*)')
genrREObj = re.compile(r'(.*)ClientIP=(.*)')

# compile regex for log file line
logfREObj = re.compile(r'^(.*?) LOGMSG=(.*$)')

systemIP = '127.0.0.1'
test_mode = 0
fetchInit = 0
configData = {}
startLoop = 0
stopLoop = 0
threadStopped = 0

# Signal handler
def signalHandler(sig, frame):
    global stopLoop
    stopLoop = 1
    applogger.info("Exit program on SIGINT")
    sys.exit(0)

#
# Get local IP address
def getLocalIP():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 1))
        IP = s.getsockname()[0]
    except:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

#
# Function to process device log messages and generate syslog events
#
def processLogEvent(clientId, log):
    global test_mode
    global systemIP

    # This function parses log event and generate syslog event.
    # Log event from WIoTP is in JSON format. Example of a typical log event:
    # {"timestamp": "2018-02-28T20:02:50.585Z", "message": "Token auth succeeded: ClientID='d:li0f0v:NXPDev:testSub', ClientIP=32.97.110.54"}

    # SYSLOG Event format:
    # <timestamp> <localip> <APPNAME>: devType=<devType> devId=<devId> Message=<Raw log message>

    timestamp = log["timestamp"]
    msg = log["message"]

    if test_mode == 1:
        cT = time.gmtime()
        tstamp = time.strftime("%b %d %H:%M:%S", cT)
        syslog_header = "%s %s " % (tstamp, systemIP)
    else:
        syslog_header = "%s %s " % (timestamp, systemIP)

    headMsg = syslog_header + APPNAMECONNECTION

    # Parse authentication messages
    mObj = authREObj.match(msg)
    if mObj:
        message = mObj.group(1)
        clientId = mObj.group(2)
        IP = mObj.group(3)
        event = "AuthSucceeded"
        if "failed" in message:
            event = "AuthFailed"
        eventMsg = "%s source=%s event=%s clientID=%s Message=%s" % (headMsg, IP, event, clientId, message)
        applogger.debug(eventMsg)
        sysLogger.info(eventMsg)
        return
        
    # Parse connection closed messages
    mObj = connREObj.match(msg)
    if mObj:
        message = mObj.group(2)
        IP = mObj.group(1)
        event = "ClosedNormal"
        if "by the client" in message:
            state = "ClosedByClient"
        if "not authorized" in message:
            event = "OperationUnauthorized"
        eventMsg = "%s source=%s event=%s clientID=%s Message=%s" % (headMsg, IP, event, clientId, message)
        applogger.debug(eventMsg)
        sysLogger.info(eventMsg)
        return
        
    # Process generic log
    # check if ClientIP is specified in message
    event = "NA"
    IP = "NA"
    mObj = genrREObj.match(msg)
    if mObj:
        IP = mObj.group(2)

    eventMsg = "%s source=%s event=%s clientID=%s Message=%s" % (headMsg, IP, event, clientId, msg)
    applogger.debug(eventMsg)
    sysLogger.info(eventMsg)


#
# Get all device data from Watson IoT Platform
#
def getDevices(client, device_limit, log_limit):

    # applogger.info("Start a new pool cycle ...")
    _getPageOfDevices(client, device_limit, log_limit, None )

#
# Get device data in chunks
# 
def _getPageOfDevices(client, device_limit, log_limit, bookmark):
    global lastISOTime
    global curISOTime

    deviceList = client.api.getDevices(parameters = {"_limit": device_limit, "_bookmark": bookmark, "_sort": "typeId,deviceId"})
    resultArray = deviceList['results']

    applogger.info("Process connection logs of " + str(len(resultArray)) + " devices")
    for device in resultArray:
        if "metadata" not in device:
            device["metadata"] = {}

        typeId = device["typeId"]
        deviceId = device["deviceId"]
        clientId = device["clientId"]

        # applogger.debug("ClientID=" + clientId)

        try:
            # get logs for the device 
            if log_limit == 0:
                applogger.debug("clientID:" + clientId + " from:" + lastISOTime + " to:" + curISOTime); 
                logresults = client.api.getConnectionLogs({"typeId":typeId, "deviceId":deviceId, "fromTime": lastISOTime, "toTime": curISOTime})
            else:
                if log_limit == -1:
                    logresults = client.api.getConnectionLogs({"typeId":typeId, "deviceId":deviceId})
                else:
                    logresults = client.api.getConnectionLogs({"typeId":typeId, "deviceId":deviceId, "_limit": log_limit})
 

            logMsgCount = 0  
            for log in logresults:
                processLogEvent(clientId, log)
                applogger.debug(clientId + " LOGMSG=" + json.dumps(log))
                logMsgCount += 1

            if logMsgCount > 0:
                applogger.info("ClientID:" + clientId + " Total events:" + str(logMsgCount))

        except Exception as e:
            applogger.error(str(e))


    # Next page
    if "bookmark" in deviceList:
        bookmark = deviceList["bookmark"]
        _getPageOfDevices(client, device_limit, log_limit, bookmark)

#
# Get device data and log events
#
def getEventFromAPI(client, device_limit, log_limit):
    try:
        getDevices(client, device_limit, log_limit)

    except ibmiotf.APIException as e:
        applogger.error(e.httpCode)
        applogger.error(str(e))
        return
    except Exception as e:
        applogger.info(str(e))
        return


#
# Get events from log file
# Log file should be in the following format:
# <ClientID> LOGMSG=<logMessage>
#
def getEventsFromLogFile(logf):
    # read log file and process log event
    with open(logf, "r") as f:
        for line in f:
            applogger.debug(line)
            lObj = logfREObj.match(line)
            if lObj:
                clientId = lObj.group(1)
                log = lObj.group(2)
                jslog = json.loads(log)
                processLogEvent(clientId, jslog)


#
# Pooling function to perodically invoke REST API to get device logs and data from WIoTP
#
def getDataAndProcess(): 
    global test_mode
    global fetchInit
    global configData
    global startLoop
    global stopLoop
    global threadStopped
    global lastISOTime
    global curISOTime

    cycle = 0
    loop = 0

    test_mode = configData['test_mode']
    nloop = int(configData['cycles'])
    device_limit = int(configData['device_fetch_limit'])
    log_limit = int(configData['log_fetch_limit'])
    interval = int(configData['log_fetch_interval'])
    test_log = configData['test_log']

    # Set current time in ISO8601 - needed for log fetch API
    curTime = time.gmtime()
    curISOTime = time.strftime("%Y-%m-%dT%H:%M:%S", curTime)
    applogger.info("Current time: " + curISOTime + "\n")

    # Get API client
    config = "application.cfg"
    client = None
    options = ibmiotf.application.ParseConfigFile(config)
    try:
        client = ibmiotf.application.Client(options)
        client.logger.setLevel(logging.INFO)

    except Exception as e:
        applogger.error(str(e))
        return

    while True:
        if startLoop == 1:
            loop += 1
        
            # set current time
            curTime = time.gmtime()
            curISOTime = time.strftime("%Y-%m-%dT%H:%M:%S", curTime)
   
            if nloop == 0: 
                applogger.info("WIoTP Log Fetch cycle [{0}]: Time From:{1} To:{2}".format(str(loop),lastISOTime, curISOTime))
            else:
                applogger.info("WIoTP Log Fetch cycle [{0}] of [{1}]: Time From:{2} To:{3}".format(str(loop),str(nloop),lastISOTime, curISOTime))

            if len(test_log) > 0 and test_mode == 1:
                # Get log from log file
                getEventsFromLogFile(test_log)
            else:
                if fetchInit == 0 and log_limit == 0:
                    # get all old logs when connecting for the first time
                    getEventFromAPI(client,device_limit,-1)
                    fetchInit = 1
                else:
                    getEventFromAPI(client,device_limit,log_limit)
    
            # set last time
            lastISOTime = curISOTime
    
            # check for test cycle
            if nloop > 0 and loop == nloop:
                break

        time.sleep(int(interval))
        if stopLoop == 1:
            break

    applogger.info("STOP and EXIT application \n")
    threadStopped = 1
    sys.exit(0)


#
# Set startLoop variable so that thread can start processing data
#
def start_thread():
    global startLoop
    global stopLoop
    print("Starting Application")
    stopLoop = 0
    startLoop = 1


#
# Set startLoop variable so that thread can start processing data
#
def stop_thread():
    global startLoop
    global stopLoop
    print("Stopping Application")
    stopLoop = 1
    startLoop = 0


# Configure syslog server and spawn thread to get connection logs from WIoTP and generate 
# syslog events
def get_wiotp_data():
    global sysLogger
    global systemIP
    global configData

    # Set up signal handler
    signal.signal(signal.SIGINT, signalHandler)

    applogger.info("Start qradar-connector")

    # Read configuration file to read qradar syslog server host IP and Port
    cwd = os.getcwd()
    configpath = cwd + "/application.cfg"

    # Get configuration data
    config = ConfigParser.ConfigParser()
    config.read(configpath)

    # SYSLOG server address and port
    syslog_server_address = config.get("qradar-syslog-server", "hostip")
    syslog_server_port = config.getint("qradar-syslog-server", "port")

    applogger.info("syslog_server_address: " + syslog_server_address )
    applogger.info("syslog_server_port: " + str(syslog_server_port) )

    # read parameters used for invoking WIoTP API calls and processing data
    configData = {}

    # Check for test mode
    configData['test_mode'] = config.get("qradar-connector", "replay-log-file")
    configData['test_log'] = config.get("qradar-connector", "log-file-name")

    # Set number of cycles - default is 0 (loop for ever)
    configData['cycles'] = config.getint("qradar-connector", "cycles")

    # Chunk limit for getting device data
    configData['device_fetch_limit'] = config.getint("qradar-connector", "device-fetch-limit")

    # Log fetch strategy
    # 0 (use time period), 1 (use limit), -1 (get all)
    configData['log_fetch_limit'] = config.getint("qradar-connector", "log-fetch-limit")

    # Log fetch pooling interval in seconds
    configData['log_fetch_interval'] = config.getint("qradar-connector", "log-fetch-interval")

    # Log Level - default INFO
    configData['level'] = config.get("qradar-connector", "level")

    systemIP = getLocalIP()

    # Set log level
    applogger.removeHandler(conlogger)
    conlogger.setLevel(configData['level'])
    applogger.addHandler(conlogger)

    applogger.debug("Configuration Data:")
    applogger.debug(json.dumps(configData, indent=4))

    # Set Syslog handler
    sysLogger.setLevel(logging.INFO)
    syslog_handler = logging.handlers.SysLogHandler( address=(syslog_server_address, syslog_server_port), facility=logging.handlers.SysLogHandler.LOG_LOCAL1)
    sysLogger.addHandler(syslog_handler)

    # Start thread to process data    
    thread = Thread(target = getDataAndProcess)
    thread.start()

 
if __name__ == '__main__':
    startLoop = 1
    get_wiotp_data()

