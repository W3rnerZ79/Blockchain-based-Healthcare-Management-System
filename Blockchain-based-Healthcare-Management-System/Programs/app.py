from flask import Flask, request, jsonify, render_template
import mysql.connector
import hashlib
import json
import getpass
from datetime import datetime

app = Flask(__name__, template_folder='../templates')

# ==========================================
# CENTRAL DATABASE CONNECTION
# ==========================================
conn = mysql.connector.connect(
    host="localhost",       
    user="root",   
    password="Nov03@00$o4",# Update with your real password
    database="blockchain-based-healthcare-management-system" 
)
cursor = conn.cursor(dictionary=True) # Returns rows as nice Python dictionaries

def calculate_hash(index, timestamp, row_id, username, data_hash, previous_hash):
    block_string = f"{index}{timestamp}{row_id}{username}{data_hash}{previous_hash}".encode()
    return hashlib.sha256(block_string).hexdigest()

# ==========================================
# ENDPOINT 1: ADD A NEW BLOCK (POST Request)
# ==========================================
@app.route('/add', methods=['POST'])
def api_add_block():
    # Receive json payload from an external client
    client_data = request.get_json()
    
    if not client_data or 'item_name' not in client_data or 'quantity' not in client_data or 'username' not in client_data:
        return jsonify({"error": "Missing required fields: item_name, quantity, username"}), 400

    username = client_data['username']
    row_data = {"item_name": client_data['item_name'], "quantity": client_data['quantity']}
    
    # 1. Fetch last block details
    cursor.execute("SELECT block_index, current_hash FROM blockchain ORDER BY block_index DESC LIMIT 1")
    last_block = cursor.fetchone()
    
    serialized_data = json.dumps(row_data, sort_keys=True).encode()
    row_data_hash = hashlib.sha256(serialized_data).hexdigest()
    timestamp = str(datetime.now())
    
    if last_block is None:
        block_index = 0
        previous_hash = "0"
        row_id = 0
    else:
        block_index = int(last_block['block_index']) + 1
        previous_hash = str(last_block['current_hash'])
        row_id = block_index # simplified for sequencing
        
    current_hash = calculate_hash(block_index, timestamp, row_id, username, row_data_hash, previous_hash)
    
    # 2. Insert to MySQL
    cursor.execute('''
        INSERT INTO blockchain (block_index, timestamp, row_id, created_by, data_hash, previous_hash, current_hash)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    ''', (block_index, timestamp, row_id, username, row_data_hash, previous_hash, current_hash))
    conn.commit()
    
    return jsonify({
        "message": f"Block #{block_index} successfully added over the API!",
        "block_index": block_index,
        "created_by": username,
        "current_hash": current_hash
    }), 201

# ==========================================
# ENDPOINT 2: VERIFY INTEGRITY (GET Request)
# ==========================================
@app.route('/verify', methods=['GET'])
def api_verify_blockchain():
    cursor.execute("SELECT * FROM blockchain ORDER BY block_index ASC")
    # Convert cursor list mapping to ordered tuples manually for hash calculations
    blocks = cursor.fetchall()
    
    if not blocks:
        return jsonify({"message": "Blockchain is empty."}), 200
        
    cursor.execute("SELECT USER()")
    db_user = cursor.fetchone()['USER()']
    auditor_identity = f"API_Auditor via DB:{db_user}"
    
    chain_valid = True
    tampered_block_index = None

    for i in range(len(blocks)):
        b = blocks[i]
        
        # Pull by keys because dictionary=True is active
        recalculated_hash = calculate_hash(b['block_index'], b['timestamp'], b['row_id'], b['created_by'], b['data_hash'], b['previous_hash'])
        
        if recalculated_hash != b['current_hash'] or (i > 0 and b['previous_hash'] != blocks[i-1]['current_hash']):
            chain_valid = False
            tampered_block_index = b['block_index']
            break

    if chain_valid:
        cursor.execute('''
            INSERT INTO blockchain_ledger (block_index, status, audited_by) 
            VALUES (%s, %s, %s)
        ''', (blocks[-1]['block_index'], "VERIFIED_ACTIVE", auditor_identity))
        conn.commit()
        return jsonify({"status": "SUCCESS", "message": "Integrity check passed. Ledger updated."}), 200
    else:
        cursor.execute('''
            INSERT INTO blockchain_ledger (block_index, status, audited_by) 
            VALUES (%s, %s, %s)
        ''', (tampered_block_index, "TAMPER_ALERT", auditor_identity))
        conn.commit()
        return jsonify({"status": "TAMPER_DETECTED", "corrupted_block_index": tampered_block_index}), 400

# ==========================================
# VISUAL DASHBOARD ENDPOINT
# ==========================================
@app.route('/')
def home_dashboard():
    # This searches your 'templates' folder and shoots the index.html page to the browser
    return render_template('index.html')
# ==========================================
# RUNNING THE SERVER
# ==========================================
if __name__ == '__main__':
    # host='0.0.0.0' allows other computers on your Wi-Fi/network to reach your server
    app.run(host='0.0.0.0', port=5000, debug=True)