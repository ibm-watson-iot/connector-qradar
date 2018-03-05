# Connector Application for Watson IoT Platform and QRadar Integration 

This application performs the following tasks:
- Makes REST calls to get connection logs from WIoTP
- Normalizes the data needed for QRadar integration
- Generates and sends syslog events to QRadar platform

## Dependencies

- [Python 3.6](https://www.python.org/downloads/release/python-360/)
- [Python 2.7](https://www.python.org/downloads/release/python-2713/)
- [IBM Watson IoT Platform Python client library](https://github.com/ibm-watson-iot/iot-python)

Note: Support for MQTT with TLS requires at least Python v2.7.9 or v3.4, and openssl v1.0.1

## Deploy in IBM Cloud

You can deploy this application as Cloud Foundary application in IBM Cloud.
Before you begin, download and install the IBM Cloud command line interface. 

- [IBM Cloud CLI] (https://clis.ng.bluemix.net/)

Clone this repository locally:

```
git clone <this base URL>

For example:
git clone https://github.com/ibm-watson-iot/qradar-connector
```

Change to the directory where your code is located.

```
cd radar-wiotp-collector
```

Take note of the manifest.yml file. When deploying your app back to IBM Cloud, this file is used to 
determine your application’s URL, memory allocation, number of instances, and other crucial 
parameters. You can read more about the manifest file in the Cloud Foundry documentation.
Also pay attention to the README.md file, which contains details such as application 
configuration details.

Make changes to your application.cfg 

```
[application]
org = <your Watson IoT Platform organization id>
auth-method = token
auth-key = <API Key>
auth-token = <API Token>

[qradar-syslog-server]
hostip = <Host IP of QRadar SYSLOG server. Default 127.0.0.1>
port = <Port of QRadar SYSLOG server. Default 514>

[qradar-connector]
device-fetch-limit = <Number of devices processed in a batch. Default 100>
log-fetch-limit = <Connection log fetch stretagy. 0 (use time period), number (use limit), -1 (get all)>
log-fetch-interval = <Log fetch pooling interval in seconds. Default 10>
verbose = 0


Example application.cfg

[application]
org = ui1f0v
auth-method = token
auth-key = a-ui1f0v-saxzblldvv
auth-token = tD_yyAXN7tsGw5T7dj

[qradar-syslog-server]
hostip = 10.78.169.83
port = 514

[qradar-connector]
device-fetch-limit = 100
log-fetch-limit = -1
log-fetch-interval = 10
verbose = 0

```

Connect and log in to IBM Cloud.

```
bluemix api https://api.ng.bluemix.net
bluemix login -u <IBMid> -o org_name -s space_name
```

If you are using a federated ID, use the -sso option.

```
bluemix login  -o org_name -s space_name -sso
```

Note: You must add single or double quotes around username, org_name, and space_name if 
the value contains a space, for example, -o "my org". From your_new_directory, deploy your app 
to IBM Cloud by using the bluemix app push command. 
For more information about the bx app push command, see [Uploading your application](https://console.bluemix.net/docs/starters/upload_app.html).

```
bluemix app push qradar-connector
```

Access your app by browsing to https://qradar-connector.mybluemix.net.



