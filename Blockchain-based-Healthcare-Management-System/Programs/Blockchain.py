import mysql.connector
import hashlib
import json
import getpass
from datetime import datetime

conn = mysql.connector.connect(
    host="localhost",       
    user="root",   
    password="Nov03@00$o4", 
    database="blockchain-based-healthcare-management-system" 
)

cursor = conn.cursor()

def calculate_hash(index, timestamp, row_id, username, data_hash, previous_hash):
    block_string = f"{index}{timestamp}{row_id}{username}{data_hash}{previous_hash}".encode()
    return hashlib.sha256(block_string).hexdigest()

def add_new_block(row_id, row_data, username=None):
    if not username:
        username = getpass.getuser()

    # FORCE MySQL to give us the current_hash explicitly as the last item
    cursor.execute("SELECT block_index, current_hash FROM blockchain ORDER BY block_index DESC LIMIT 1")
    last_block = cursor.fetchone()
    
    serialized_data = json.dumps(row_data, sort_keys=True).encode()
    row_data_hash = hashlib.sha256(serialized_data).hexdigest()
    timestamp = str(datetime.now())
    
    if last_block is None:
        block_index = 0
        previous_hash = "0"
    else:
        block_index = last_block[0] + 1
        previous_hash = str(last_block[1])
        
    block_string = f"{block_index}{timestamp}{row_id}{username}{row_data_hash}{previous_hash}".encode()
    current_hash = hashlib.sha256(block_string).hexdigest()
    
    cursor.execute('''
    INSERT INTO blockchain (block_index, timestamp, row_id, created_by, data_hash, previous_hash, current_hash)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ''', (block_index, timestamp, row_id, username, row_data_hash, previous_hash, current_hash))
    
    conn.commit()
    print(f"Block #{block_index} added successfully!")

def verify_and_log_blockchain():
    cursor.execute("SELECT * FROM blockchain ORDER BY block_index ASC")
    blocks = cursor.fetchall()
    
    if not blocks:
        print("Blockchain is empty. Nothing to verify.")
        return
        
    # Grab the current MySQL database connection user
    cursor.execute("SELECT USER()")
    db_user = cursor.fetchone()[0]
    
    auditor_identity = f"{getpass.getuser()} via DB:{db_user}"
    
    chain_valid = True
    tampered_block_index = None

    # ==========================================
    # THE MISSING VERIFICATION LOOP
    # ==========================================
    for i in range(len(blocks)):
        current_block = blocks[i]
        
        # 1. Unpack columns exactly as they sit in your MySQL table
        b_index     = current_block[0]
        b_timestamp = current_block[1]
        b_row_id    = current_block[2]
        b_user      = current_block[3]  # created_by column
        b_data_hash = current_block[4]  # data_hash column
        b_prev_hash = current_block[5]  # previous_hash column
        b_curr_hash = current_block[6]  # current_hash column
        
        # 2. Re-calculate the fingerprint to see if the data matches what was signed
        recalculated_hash = calculate_hash(b_index, b_timestamp, b_row_id, b_user, b_data_hash, b_prev_hash)
        
        # 3. Check for Data Modification
        if recalculated_hash != b_curr_hash:
            print(f"❌ TAMPERING DETECTED: Data inside Block #{b_index} has been altered!")
            chain_valid = False
            tampered_block_index = b_index
            break # Stop scanning immediately
            
        # 4. Check for Broken Chain Links
        if i > 0:
            previous_block = blocks[i-1]
            prev_block_curr_hash = previous_block[6] # Prior block's current_hash
            
            if b_prev_hash != prev_block_curr_hash:
                print(f"❌ LINK BROKEN: The chain between Block #{b_index-1} and #{b_index} is broken!")
                chain_valid = False
                tampered_block_index = b_index
                break
    # ==========================================

    # Log the result to the blockchain_ledger table
    if chain_valid:
        latest_index = blocks[-1][0]
        cursor.execute('''
            INSERT INTO blockchain_ledger (block_index, status, audited_by) 
            VALUES (%s, %s, %s)
        ''', (latest_index, "VERIFIED_ACTIVE", auditor_identity))
        print(f"✅ INTEGRITY CHECK PASSED. Audit log saved by: {auditor_identity}")
    else:
        cursor.execute('''
            INSERT INTO blockchain_ledger (block_index, status, audited_by) 
            VALUES (%s, %s, %s)
        ''', (tampered_block_index, "TAMPER_ALERT", auditor_identity))
        print(f"⚠️ TAMPER ALERT LOGGED for Block #{tampered_block_index} by: {auditor_identity}")
        
    conn.commit()

def repair_blockchain():
    """Finds tampered blocks, restores correct data, and completely heals the chain."""
    print("\n[REPAIR ENGINE] Scanning for the exact point of failure...")
    
    # 1. Fetch all blocks to find where the link broke
    cursor.execute("SELECT * FROM blockchain ORDER BY block_index ASC")
    blocks = cursor.fetchall()
    
    tampered_index = None
    
    for i in range(len(blocks)):
        current_block = blocks[i]
        b_index, b_timestamp, b_row_id, b_user, b_data_hash, b_prev_hash, b_curr_hash = current_block
        
        # Recalculate hash to find the broken row
        recalculated_hash = calculate_hash(b_index, b_timestamp, b_row_id, b_user, b_data_hash, b_prev_hash)
        
        if recalculated_hash != b_curr_hash or (i > 0 and b_prev_hash != blocks[i-1][6]):
            tampered_index = b_index
            print(f"🔧 Found data corruption starting at Block #{tampered_index}!")
            break

    if tampered_index is None:
        print("✅ No corruption found. Database is already healthy.")
        return

    # 2. Get the authentic backup data from the administrator
    print(f"\n--- RESTORE DATA FOR BLOCK #{tampered_index} ---")
    correct_item = input("Enter correct Item Name (from backup log): ")
    correct_qty = int(input("Enter correct Quantity (from backup log): "))
    
    # 3. Serialize and hash the corrected data payload
    corrected_payload = {"item_name": correct_item, "quantity": correct_qty}
    serialized_data = json.dumps(corrected_payload, sort_keys=True).encode()
    new_data_hash = hashlib.sha256(serialized_data).hexdigest()
    
    # 4. Update the tampered row with the clean data
    print(f"Restoring clean data payload to Block #{tampered_index}...")
    cursor.execute('''
        UPDATE blockchain 
        SET data_hash = %s 
        WHERE block_index = %s
    ''', (new_data_hash, tampered_index))
    conn.commit()
    
    # 5. HEAL THE CHAIN: Loop through the table from the broken block to the very end
    # and recalculate all hashes so the staircase links align perfectly again.
    print("Recalculating cryptographic chain links...")
    cursor.execute("SELECT * FROM blockchain ORDER BY block_index ASC")
    all_blocks = cursor.fetchall()
    
    for i in range(len(all_blocks)):
        # Skip healthy blocks that came before the hack
        if i < tampered_index:
            continue
            
        current_block = all_blocks[i]
        b_index, b_timestamp, b_row_id, b_user, b_data_hash, b_prev_hash, b_curr_hash = current_block
        
        # If it's a subsequent block, its previous_hash must update to match the block right before it
        if i > 0:
            b_prev_hash = all_blocks[i-1][6] # Get prior block's updated current_hash
            
        # Generate the brand new current_hash fingerprint
        new_curr_hash = calculate_hash(b_index, b_timestamp, b_row_id, b_user, b_data_hash, b_prev_hash)
        
        # Update the database with the pristine cryptographic seals
        cursor.execute('''
            UPDATE blockchain 
            SET previous_hash = %s, current_hash = %s 
            WHERE block_index = %s
        ''', (b_prev_hash, new_curr_hash, b_index))
        
        # Update our local array so the next loop iteration sees the newly updated hash
        all_blocks[i] = (b_index, b_timestamp, b_row_id, b_user, b_data_hash, b_prev_hash, new_curr_hash)

    # 6. Log the successful repair operation to the ledger
    import getpass
    cursor.execute("SELECT USER()")
    db_user = cursor.fetchone()[0]
    repair_user = f"{getpass.getuser()} via DB:{db_user}"
    
    cursor.execute('''
        INSERT INTO blockchain_ledger (block_index, status, audited_by) 
        VALUES (%s, %s, %s)
    ''', (all_blocks[-1][0], "REPAIRED_HEALED", repair_user))
    
    conn.commit()
    print(f"🎉 SUCCESS: Chain fully healed! System health status logged as REPAIRED_HEALED.")

# ---INTERACTIVE USER INTERFACE ---

if __name__ == "__main__":
    while True:
        print("\n=== SQL BLOCKCHAIN MENU ===")
        print("1. Add a new row to the chain")
        print("2. Verify database integrity")
        print("3. Run Repair Engine")
        print("4. Exit")  
        
        choice = input("Choose an option (1-4): ").strip()
        
        if choice == "1":
            
            name = input("Enter Item Name: ")
            qty = int(input("Enter Quantity: "))
            pass
            
        elif choice == "2":
            verify_and_log_blockchain()
            
        elif choice == "3":
            repair_blockchain()
            
        elif choice == "4":
            print("\nClosing database connection. Goodbye!")
            cursor.close()
            conn.close()
            break
            
        else:
            print("Invalid option. Please choose between 1 and 4.")