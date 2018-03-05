__author__ = 'IBM'

from flask import Flask, render_template, request, jsonify
import atexit
import os
import json
from subprocess import Popen

app = Flask(__name__)

port = int(os.getenv('PORT', 8000))
cwd = os.getcwd()
progpath = cwd + "/getwiotpdata.py"

@app.route('/')
def home():
    print("Starting program: " + progpath)
    return render_template('index.html')

@app.route('/start', methods=['GET', 'POST'])
def start():
    pid = os.spawnlp(os.P_NOWAIT, "python", progpath, None)
    return render_template('start.html', PID=pid)


@atexit.register
def shutdown():
    # Add any cleanup
    print("Stop Application")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port, debug=True)


