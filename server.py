__author__ = 'IBM'

from flask import Flask, render_template, request, jsonify
import atexit
import os
import json
import sys
from subprocess import Popen
from getwiotpdata import get_wiotp_data
from getwiotpdata import start_thread
from getwiotpdata import stop_thread

app = Flask(__name__)

port = int(os.getenv('PORT', 8000))

@app.route('/')
def home():
    print("Starting WIoTP QRadar-Connector Application")
    return render_template('index.html')


@app.route('/start', methods=['GET', 'POST'])
def start():
    start_thread()
    return render_template('start.html')


@app.route('/stop')
@app.route('/stop', methods=['POST'])
def stop():
    stop_thread()
    return render_template('stop.html')

@atexit.register
def shutdown():
    # Add any cleanup
    stop_thread()
    print("Stop Application")
    sys.exit(0)


if __name__ == '__main__':
    get_wiotp_data()
    app.run(host='0.0.0.0', port=port, debug=True)


