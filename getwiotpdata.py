# *****************************************************************************
# Copyright (c) 2018 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# Contributors:
#
# *****************************************************************************

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


# SYSLOG setup - Application name and logger
APPNAME = "WIoTP:Connection: "
logger = logging.getLogger('SyslogLogger')

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

#
# Function to process device log messages and generate syslog events
#
def processLogEvent(log, verbose):
    # This function parses log event and generate syslog event.
    # Log event from WIoTP is in JSON format. Example of a typical log event:
    # {"timestamp": "2018-02-28T20:02:50.585Z", "message": "Token auth succeeded: ClientID='d:li0f0v:NXPDev:testSub', ClientIP=32.97.110.54"}
    timestamp = log["timestamp"]
    msg = log["message"]

    syslog_header = "%s " % (timestamp)
    headMsg = syslog_header + APPNAME + "INFO: "
    dMsg = None

    # Parse authentication messages
    mObj = authREObj.match(msg)
    if mObj:
        message = mObj.group(1)
        clientId = mObj.group(2)
        IP = mObj.group(3)
        type = "Token"
        event = "AuthSucceeded"
        if "failed" in message:
            event = "AuthFailed"
            headMsg = syslog_header + APPNAME + "ERROR: "
        eventMsg = "%s%s: EventID=%s Type=%s ClientID=%s Message=%s" % (headMsg, IP,event,type,clientId,message)
        if verbose:
            print( "Event: " + eventMsg)
        logger.info(eventMsg)
        return
        
    # Parse connection closed messages
    mObj = connREObj.match(msg)
    if mObj:
        message = mObj.group(2)
        IP = mObj.group(1)
        type = "Normal"
        event = "ConnClosed"
        if "by client" in message:
            type = "ByClient"
        if "not authorized" in message:
            type = "Unauthorized"
        eventMsg = "%s%s: EventID=%s Type=%s ClientID=Unknown Message=%s" % (headMsg,IP,event,type,message)
        if verbose:
            print( "Event: " + eventMsg)
        logger.info(eventMsg)
        return
        
    # Process generic log
    # check if ClientIP is specified in message
    event = "Unknown"
    mObj = genrREObj.match(msg)
    if mObj:
        IP = mObj.group(2)
        dMsg = "%s: EventID=%s Type=Unknown ClientID=Unknown Message=%s" % (IP,event,message)
    else:
        dMsg = "Unknown: EventID=Unknown Type=Unknown ClientID=Unknown Message=%s" % (json.dumps(log))

    if dMsg != None:
        eventMsg = headMsg + dMsg
        if verbose:
            print( "Event: " + eventMsg)
    else:
        eventMsg = headMsg + log
        if verbose:
            print( "Event: " + eventMsg)
    logger.info(eventMsg)


#
# Get all device data from Watson IoT Platform
#
def getDevices(client, device_limit, log_limit, verbose):

    if verbose:
        print("Get Devices ...")
    _getPageOfDevices(client, device_limit, log_limit, verbose, None )

#
# Get device data in chunks
# 
def _getPageOfDevices(client, device_limit, log_limit, verbose, bookmark):

    deviceList = client.api.getDevices(parameters = {"_limit": device_limit, "_bookmark": bookmark, "_sort": "typeId,deviceId"})
    resultArray = deviceList['results']
    for device in resultArray:
        if "metadata" not in device:
            device["metadata"] = {}

        typeId = device["typeId"]
        deviceId = device["deviceId"]

        if verbose:
            print("DeviceType: " + typeId + " DeviceId: " + deviceId)

        try:
            # get logs for the device 
            if log_limit == 0:
                logresults = client.api.getConnectionLogs({"typeId":typeId, "deviceId":deviceId, "fromTime": lastISOTime, "toTime": curISOTime})
            else:
                if log_limit == -1:
                    logresults = client.api.getConnectionLogs({"typeId":typeId, "deviceId":deviceId})
                else:
                    logresults = client.api.getConnectionLogs({"typeId":typeId, "deviceId":deviceId, "_limit": log-fetch-limit})
 
  
            for log in logresults:
                processLogEvent(log, verbose)
                if verbose:
                    print(json.dumps(log))

        except Exception as e:
            print(str(e))


    # Next page
    if "bookmark" in deviceList:
        bookmark = deviceList["bookmark"]
        _getPageOfDevices(client, device_limit, log_limit, verbose, bookmark)

#
# Get device data and log events
#
def getEventFromAPI(client, device_limit, log_limit, verbose):
    try:
        getDevices(client, device_limit, log_limit, verbose)

    except ibmiotf.APIException as e:
        print(e.httpCode)
        print(str(e))
        return
    except Exception as e:
        print(str(e))
        return

#
# Pooling function to perodically invoke REST API to get device logs and data from WIoTP
#
def poll_pm(device_limit, log_limit, interval, nloop, verbose, lock): 
    t = threading.currentThread()
    cycle = 0
    loop = 0

    # Set current time in ISO8601 - needed for log fetch API
    curTime = time.gmtime()
    curISOTime = time.strftime("%Y-%m-%dT%H:%M:%S", curTime)
    print("Current time: " + curISOTime + "\n")

    # Get API client
    config = "application.cfg"
    client = None
    options = ibmiotf.application.ParseConfigFile(config)
    try:
        client = ibmiotf.application.Client(options)
        client.logger.setLevel(logging.INFO)

    except Exception as e:
        print(str(e))
        return

    while getattr(t, "continue_run", True):
        loop += 1
        lock.acquire()
        if verbose:
            print("App: Lock acquired. Loop [{0}] of [{1}]: test:[{2}]".format(str(loop),str(nloop),str(cycle)))
    
        # set current time
        curTime = time.gmtime()
        curISOTime = time.strftime("%Y-%m-%dT%H:%M:%S", curTime)

        getEventFromAPI(client,device_limit,log_limit,verbose)

        # set last time
        lastISOTime = curISOTime

        lock.release()
        
        # check for test cycle
        if nloop > 0 and loop == nloop:
            t.continue_run = False

        time.sleep(int(interval))

    print("STOP Loop \n")


# Configure syslog server and spawn thread to get connection logs from WIoTP and generate 
# syslog events
def get_wiotp_data():
    print("Start processing thread")

    # Read configuration file to read qradar syslog server host IP and Port
    cwd = os.getcwd()
    configpath = cwd + "/application.cfg"

    # Use safe config parser to specify default values
    default_values = {
        'qradar-syslog-server': '127.0.0.1', 
        'qradar-syslog-port': 514,
        'no-cycles': 0,
        'device-fetch-limit': 100,
        'log-fetch-limit': -1,
        'log-fetch-interval': 15,
        'verbose': True
    }

    config = ConfigParser.SafeConfigParser(default_values)
    config.read(configpath)

    # SYSLOG server address and port
    syslog_server_address = config.get("qradar-syslog-server", "hostip")
    syslog_server_port = config.getint("qradar-syslog-server", "port")

    print("syslog_server_address: " + syslog_server_address )
    print("syslog_server_port: " + str(syslog_server_port) )

    # read parameters used for invoking WIoTP API calls and processing data

    # Number of test cycles - default is 0 - loop for ever
    no_cycles = config.getint("qradar-connector", "no-cycles")

    # Chunk limit for getting device data
    device_fetch_limit = config.getint("qradar-connector", "device-fetch-limit")

    # Log fetch strategy
    # 0 (use time period), 1 (use limit), -1 (get all)
    log_fetch_limit = config.getint("qradar-connector", "log-fetch-limit")

    # Log fetch pooling interval in seconds
    log_fetch_interval = config.getint("qradar-connector", "log-fetch-interval")

    # verbose mode - default True
    verbose = config.getboolean("qradar-connector", "verbose")
    
    print("device_fetch_limit: " + str(device_fetch_limit))
    print("log_fetch_limit: " + str(log_fetch_limit))
    print("log_fetch_interval: " + str(log_fetch_interval))
    print("no_cycles: " + str(no_cycles))
    print("verbose: " + str(verbose))

    logger.setLevel(logging.INFO)
    syslog_handler = logging.handlers.SysLogHandler( address=(syslog_server_address, syslog_server_port), facility=logging.handlers.SysLogHandler.LOG_LOCAL1)
    logger.addHandler(syslog_handler)
    lock = threading.Lock()
    thread_runner = Thread(target=poll_pm, args=(device_fetch_limit, log_fetch_limit, log_fetch_interval, no_cycles, verbose, lock))
    thread_runner.daemon = True
    thread_runner.continue_run = True
    thread_runner.start()
    thread_runner.join()
   
if __name__ == '__main__':
    get_wiotp_data() 
