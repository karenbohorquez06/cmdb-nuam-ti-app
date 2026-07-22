from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
import sqlite3
from datetime import datetime
import json
import os
 
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
 
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
 
def get_db():
    conn = sqlite3.connect('cmdb_quality.db')
    conn.row_factory = sqlite3.Row
    return conn
 
@app.route('/')
def index():
    return render