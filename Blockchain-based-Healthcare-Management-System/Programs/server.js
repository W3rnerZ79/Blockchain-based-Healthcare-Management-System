console.log("Starting script...");

const express = require('express');
const mysql = require('mysql2/promise');
const crypto = require('crypto');
const path = require('path');
const os = require('os');

const app = express();
app.use(express.json());

// ==========================================
// CENTRAL DATABASE CONNECTION
// ==========================================
// This connects to your specific database using the credentials you provided
const dbConfig = {
    host: 'localhost',
    user: 'root',
    password: 'Nov03@00$o4',
    database: 'blockchain-based-healthcare-management-system'
};

// Reusable hashing function using Node's crypto module
function calculateHash(index, timestamp, rowId, username, dataHash, previousHash) {
    const blockString = `${index}${timestamp}${rowId}${username}${dataHash}${previousHash}`;
    return crypto.createHash('sha256').update(blockString).digest('hex');
}

// ==========================================
// ENDPOINT 1: ADD A NEW BLOCK (POST Request)
// ==========================================
// Notice 'authenticateToken' is injected right into the middle of the route!
app.post('/add', authenticateToken, async (req, res) => {
    // Add patient_id to the destructured body
    const { patient_id, item_name, quantity } = req.body;
    const username = req.user.username;
    const role = req.user.role;

    if (role !== 'doctor') {
        return res.status(403).json({ error: "Access Denied: Only doctors can add records." });
    }

    if (!patient_id || !item_name || !quantity) {
        return res.status(400).json({ error: "Missing fields: patient_id, item_name, quantity" });
    }

    // Include patient_id in the cryptographic payload
    const rowData = { patient_id, item_name, quantity };
    
    try {
        const connection = await mysql.createConnection(dbConfig);
        const [rows] = await connection.execute("SELECT block_index, current_hash FROM blockchain ORDER BY block_index DESC LIMIT 1");
        const lastBlock = rows[0];
        
        const serializedData = JSON.stringify(rowData, Object.keys(rowData).sort());
        const rowDataHash = crypto.createHash('sha256').update(serializedData).digest('hex');
        const timestamp = new Date().toISOString();
        
        let blockIndex = lastBlock ? lastBlock.block_index + 1 : 0;
        let previousHash = lastBlock ? lastBlock.current_hash : "0";
        let rowId = blockIndex; 
        
        const currentHash = calculateHash(blockIndex, timestamp, rowId, username, rowDataHash, previousHash);
        
        // Update the SQL INSERT statement to include patient_id
        await connection.execute(`
            INSERT INTO blockchain (block_index, timestamp, row_id, created_by, patient_id, item_name, quantity, data_hash, previous_hash, current_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        `, [blockIndex, timestamp, rowId, username, patient_id, item_name, quantity, rowDataHash, previousHash, currentHash]);
        
        await connection.end();
        
        res.status(201).json({
            message: `Prescription successfully issued to ${patient_id}!`,
            block_index: blockIndex,
            current_hash: currentHash
        });

    } catch (error) {
        console.error(error);
        res.status(500).json({ error: "Internal server error" });
    }
});

// ==========================================
// ENDPOINT 2: VERIFY INTEGRITY (GET Request)
// ==========================================
app.get('/verify', async (req, res) => {
    try {
        const connection = await mysql.createConnection(dbConfig);
        const [blocks] = await connection.execute("SELECT * FROM blockchain ORDER BY block_index ASC");
        
        if (blocks.length === 0) {
            await connection.end();
            return res.status(200).json({ message: "Blockchain is empty." });
        }
        
        const [userRows] = await connection.execute("SELECT USER() AS db_user");
        const dbUser = userRows[0].db_user;
        const auditorIdentity = `API_Auditor via DB:${dbUser}`;
        
        let chainValid = true;
        let tamperedBlockIndex = null;

        for (let i = 0; i < blocks.length; i++) {
            const b = blocks[i];
            
            // --- NEW SECURITY CHECK: Verify the plain text payload ---
            // Inside the for-loop in your /verify endpoint:
            const rowData = { patient_id: b.patient_id, item_name: b.item_name, quantity: b.quantity };
            const serializedData = JSON.stringify(rowData, Object.keys(rowData).sort());
            const recalculatedDataHash = crypto.createHash('sha256').update(serializedData).digest('hex');
            
            if (recalculatedDataHash !== b.data_hash) {
                console.log(`❌ TAMPER DETECTED: Plain text payload altered in Block #${b.block_index}`);
                chainValid = false;
                tamperedBlockIndex = b.block_index;
                break;
            }

            // --- ORIGINAL SECURITY CHECK: Verify the chain links ---
            const recalculatedCurrentHash = calculateHash(
                b.block_index, 
                b.timestamp, 
                b.row_id, 
                b.created_by, 
                b.data_hash, 
                b.previous_hash
            );
            
            if (recalculatedCurrentHash !== b.current_hash || (i > 0 && b.previous_hash !== blocks[i-1].current_hash)) {
                console.log(`❌ TAMPER DETECTED: Chain broken at Block #${b.block_index}`);
                chainValid = false;
                tamperedBlockIndex = b.block_index;
                break;
            }
        }

        if (chainValid) {
            const latestIndex = blocks[blocks.length - 1].block_index;
            await connection.execute(`
                INSERT INTO blockchain_ledger (block_index, status, audited_by) 
                VALUES (?, ?, ?)
            `, [latestIndex, "VERIFIED_ACTIVE", auditorIdentity]);
            
            await connection.end();
            return res.status(200).json({ status: "SUCCESS", message: "Integrity check passed. Ledger updated." });
        } else {
            await connection.execute(`
                INSERT INTO blockchain_ledger (block_index, status, audited_by) 
                VALUES (?, ?, ?)
            `, [tamperedBlockIndex, "TAMPER_ALERT", auditorIdentity]);
            
            await connection.end();
            return res.status(400).json({ status: "TAMPER_DETECTED", corrupted_block_index: tamperedBlockIndex });
        }

    } catch (error) {
        console.error(error);
        res.status(500).json({ error: "Internal server error" });
    }
});

// ==========================================
// ENDPOINT 3: FETCH FULL LEDGER (GET Request)
// ==========================================
app.get('/blocks', authenticateToken, async (req, res) => {
    // RBAC: Patients are strictly forbidden from pulling the full chain
    if (req.user.role === 'patient') {
        return res.status(403).json({ error: "Access Denied: Patients cannot view the full network ledger." });
    }

    try {
        const connection = await mysql.createConnection(dbConfig);
        const [blocks] = await connection.execute("SELECT * FROM blockchain ORDER BY block_index ASC");
        await connection.end();
        res.status(200).json(blocks);
    } catch (error) {
        res.status(500).json({ error: "Failed to fetch full ledger." });
    }
});

// ==========================================
// ENDPOINT 4: FETCH USER-SPECIFIC LEDGER (GET Request)
// ==========================================
app.get('/blocks/user/:username', authenticateToken, async (req, res) => {
    const targetUser = req.params.username;
    
    // RBAC: A patient can only request their own specific username
    if (req.user.role === 'patient' && req.user.username !== targetUser) {
        return res.status(403).json({ error: "Access Denied: You can only view your own medical records." });
    }
    
    try {
        const connection = await mysql.createConnection(dbConfig);
        const [blocks] = await connection.execute(
            "SELECT * FROM blockchain WHERE created_by = ? OR patient_id = ? ORDER BY block_index ASC", 
            [targetUser, targetUser]
        );
        
        await connection.end();
        res.status(200).json(blocks);
        
    } catch (error) {
        res.status(500).json({ error: "Failed to fetch user records." });
    }
});

// ==========================================
// ENDPOINT 5: REPAIR ENGINE (POST Request)
// ==========================================
app.post('/repair', async (req, res) => {
    const { block_index, correct_item, correct_qty } = req.body;

    if (block_index === undefined || !correct_item || correct_qty === undefined) {
        return res.status(400).json({ error: "Missing required fields." });
    }

    try {
        const connection = await mysql.createConnection(dbConfig);

        // 1. Serialize and hash the corrected data payload
        const correctedPayload = { item_name: correct_item, quantity: correct_qty };
        const serializedData = JSON.stringify(correctedPayload, Object.keys(correctedPayload).sort());
        const newDataHash = crypto.createHash('sha256').update(serializedData).digest('hex');

        // 2. Update the tampered row with the clean data and its new data_hash
        await connection.execute(`
            UPDATE blockchain 
            SET item_name = ?, quantity = ?, data_hash = ?
            WHERE block_index = ?
        `, [correct_item, correct_qty, newDataHash, block_index]);

        // 3. HEAL THE CHAIN: Fetch all blocks to recalculate the staggered links
        const [allBlocks] = await connection.execute("SELECT * FROM blockchain ORDER BY block_index ASC");

        for (let i = 0; i < allBlocks.length; i++) {
            // Skip healthy blocks that came before the hack
            if (allBlocks[i].block_index < block_index) continue;

            const b = allBlocks[i];
            let newPrevHash = b.previous_hash;

            // If it's a subsequent block, its previous_hash must update to match the block right before it
            if (i > 0) {
                newPrevHash = allBlocks[i - 1].current_hash; 
            }

            // Generate the brand new current_hash fingerprint
            const newCurrHash = calculateHash(
                b.block_index, 
                b.timestamp, 
                b.row_id, 
                b.created_by, 
                b.data_hash, 
                newPrevHash
            );

            // Update the database with the pristine cryptographic seals
            await connection.execute(`
                UPDATE blockchain 
                SET previous_hash = ?, current_hash = ? 
                WHERE block_index = ?
            `, [newPrevHash, newCurrHash, b.block_index]);

            // Update our local array so the next loop iteration sees the newly updated hash
            allBlocks[i].current_hash = newCurrHash;
        }

        // 4. Log the successful repair operation to the ledger
        const [userRows] = await connection.execute("SELECT USER() AS db_user");
        const repairUser = `API_Admin via DB:${userRows[0].db_user}`;

        await connection.execute(`
            INSERT INTO blockchain_ledger (block_index, status, audited_by) 
            VALUES (?, ?, ?)
        `, [allBlocks[allBlocks.length - 1].block_index, "REPAIRED_HEALED", repairUser]);

        await connection.end();
        res.status(200).json({ message: `🎉 SUCCESS: Chain fully healed starting from Block #${block_index}!` });

    } catch (error) {
        console.error(error);
        res.status(500).json({ error: "Internal server error during repair." });
    }
});

const bcrypt = require('bcrypt');
const jwt = require('jsonwebtoken');

// In a real app, this goes in a hidden .env file. For development, we'll hardcode it.
const JWT_SECRET = "super_secret_healthcare_key_123";

// ==========================================
// AUTH ENDPOINT 1: REGISTER USER (POST)
// ==========================================
app.post('/register', async (req, res) => {
    const { username, password, role } = req.body;

    if (!username || !password || !role) {
        return res.status(400).json({ error: "Missing required fields." });
    }

    try {
        // Hash the password with a "salt" factor of 10 for security
        const salt = await bcrypt.genSalt(10);
        const hashedPassword = await bcrypt.hash(password, salt);

        const connection = await mysql.createConnection(dbConfig);
        await connection.execute(`
            INSERT INTO users (username, password_hash, role) 
            VALUES (?, ?, ?)
        `, [username, hashedPassword, role]);
        
        await connection.end();
        res.status(201).json({ message: `User ${username} successfully registered as a ${role}!` });

    } catch (error) {
        // Error code 1062 is MySQL's code for a duplicate entry (username already taken)
        if (error.code === 'ER_DUP_ENTRY') {
            return res.status(400).json({ error: "Username already exists." });
        }
        console.error(error);
        res.status(500).json({ error: "Failed to register user." });
    }
});

// ==========================================
// AUTH ENDPOINT 2: LOGIN (POST)
// ==========================================
app.post('/login', async (req, res) => {
    const { username, password } = req.body;

    try {
        const connection = await mysql.createConnection(dbConfig);
        const [users] = await connection.execute("SELECT * FROM users WHERE username = ?", [username]);
        await connection.end();

        if (users.length === 0) {
            return res.status(401).json({ error: "Invalid username or password." });
        }

        const user = users[0];

        // Compare the typed password against the hashed password in the database
        const validPassword = await bcrypt.compare(password, user.password_hash);
        if (!validPassword) {
            return res.status(401).json({ error: "Invalid username or password." });
        }

        // Generate the JWT "ID Badge" containing their name and role
        const token = jwt.sign(
            { username: user.username, role: user.role }, 
            JWT_SECRET, 
            { expiresIn: '2h' } // Token expires in 2 hours
        );

        res.status(200).json({ 
            message: "Login successful!", 
            token: token,
            role: user.role
        });

    } catch (error) {
        console.error(error);
        res.status(500).json({ error: "Internal server error during login." });
    }
});

// ==========================================
// MIDDLEWARE: SECURITY GUARD
// ==========================================
function authenticateToken(req, res, next) {
    const authHeader = req.headers['authorization'];
    const token = authHeader && authHeader.split(' ')[1]; 

    if (!token) {
        return res.status(401).json({ error: "Access denied. No ID badge provided." });
    }

    jwt.verify(token, JWT_SECRET, (err, decodedUser) => {
        if (err) {
            return res.status(403).json({ error: "Invalid or expired ID badge." });
        }
        req.user = decodedUser; 
        next(); 
    });
}

// ==========================================
// VISUAL DASHBOARD ENDPOINT
// ==========================================
// Serves the HTML frontend from a 'templates' folder
app.get('/', (req, res) => {
    // The '..' tells Node to go up one folder level, just like in Python
    res.sendFile(path.join(__dirname, '..', 'templates', 'index.html'));
});
// ==========================================
// RUNNING THE SERVER
// ==========================================
const PORT = 5000;
app.listen(PORT, '0.0.0.0', () => {
    console.log(`Server is running on http://localhost:${PORT}`);
});