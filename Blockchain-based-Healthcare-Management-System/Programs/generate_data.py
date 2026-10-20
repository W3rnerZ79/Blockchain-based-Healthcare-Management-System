import hashlib
import datetime
import random
import json

# 1. SHA-256 Helper Function
def calculate_sha256(string_data):
    return hashlib.sha256(string_data.encode('utf-8')).hexdigest()

blockchain = []

# 2. Block Generation Function (Strictly matching server.js logic)
def add_block(index, created_by, patient_id, item_name, quantity, previous_hash):
    # Match Node.js new Date().toISOString() millisecond format
    timestamp = datetime.datetime.utcnow().isoformat(timespec='milliseconds') + "Z"
    row_id = index
    
    # Match Node.js JSON.stringify with alphabetically sorted keys and no spaces
    payload_dict = {
        "item_name": item_name,
        "patient_id": patient_id,
        "quantity": quantity
    }
    data_payload = json.dumps(payload_dict, separators=(',', ':'), sort_keys=True)
    data_hash = calculate_sha256(data_payload)
    
    # Match Node.js template literal sequence exactly
    block_header = f"{index}{timestamp}{row_id}{created_by}{data_hash}{previous_hash}"
    current_hash = calculate_sha256(block_header)
    
    block = {
        "block_index": index,
        "timestamp": timestamp,
        "row_id": row_id, 
        "created_by": created_by,
        "patient_id": patient_id,
        "data_hash": data_hash,
        "previous_hash": previous_hash,
        "current_hash": current_hash,
        "item_name": item_name,
        "quantity": quantity
    }
    
    blockchain.append(block)
    return current_hash

# 3. Realistic Data Pools
medicines = [
    'Atorvastatin', 'Levothyroxine', 'Lisinopril', 'Metformin', 
    'Amlodipine', 'Metoprolol', 'Albuterol', 'Omeprazole', 
    'Losartan', 'Gabapentin', 'Amoxicillin', 'Sertraline'
]
quantities = [15, 30, 60, 90, 120] 

doctors = [
    'Dr. Smith', 'Dr. Johnson', 'Dr. Williams', 'Dr. Brown', 
    'Dr. Jones', 'Dr. Garcia', 'Dr. Miller', 'Dr. Davis',
    'Dr. Rodriguez', 'Dr. Martinez'
]

patients = [
    'James Wilson', 'Mary Taylor', 'John Anderson', 'Patricia Thomas', 
    'Robert Jackson', 'Jennifer White', 'Michael Harris', 'Linda Martin', 
    'William Thompson', 'Elizabeth Garcia', 'David Martinez', 'Barbara Robinson', 
    'Richard Clark', 'Susan Rodriguez', 'Joseph Lewis', 'Jessica Lee'
]

# 4. Generate Sample Data
last_hash = "0"
last_hash = add_block(0, "System", "None", "Genesis Block", 0, last_hash)

# Generate 200 perfect blocks
for i in range(1, 201):
    doc = random.choice(doctors)
    pat = random.choice(patients)
    med = random.choice(medicines)
    qty = random.choice(quantities)
    
    last_hash = add_block(i, doc, pat, med, qty, last_hash)

# 5. Output SQL Statements
print("INSERT INTO blockchain (block_index, timestamp, row_id, created_by, patient_id, data_hash, previous_hash, current_hash, item_name, quantity) VALUES")
for i, b in enumerate(blockchain):
    end_char = ";" if i == len(blockchain) - 1 else ","
    print(f"({b['block_index']}, '{b['timestamp']}', {b['row_id']}, '{b['created_by']}', '{b['patient_id']}', '{b['data_hash']}', '{b['previous_hash']}', '{b['current_hash']}', '{b['item_name']}', {b['quantity']}){end_char}")