import { 
    makeWASocket, 
    DisconnectReason, 
    useMultiFileAuthState
} from '@whiskeysockets/baileys';
import qrcode from 'qrcode-terminal';
import fs from 'fs';
import readline from 'readline';
import path from 'path';

// Helper function to read contacts from a file
function readContactsFromFile(filename) {
    try {
        const filePath = path.resolve(process.cwd(), filename);
        console.log(`Reading contacts from: ${filePath}`);
        const data = fs.readFileSync(filePath, 'utf-8');
        // Split by newline, trim, and filter out empty lines
        const contacts = data.split('\n')
            .map(line => line.trim())
            .filter(line => line.length > 0);
        console.log(`Found ${contacts.length} contacts:`, contacts);
        return contacts;
    } catch (error) {
        console.error('Error reading contacts file:', error.message);
        process.exit(1);
    }
}


// Main function
async function sendBulkMessages() {
    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout
    });

    try {
        // Ask for the message to send
        const message = await new Promise(resolve => {
            rl.question('Enter your message: ', resolve);
        });

        // Ask for the contacts file path
        const contactsFile = await new Promise(resolve => {
            rl.question('Enter path to contacts file (one number per line with country code, e.g., 1234567890): ', resolve);
        });

        // Read contacts
        const contacts = readContactsFromFile(contactsFile);
        console.log(`Found ${contacts.length} contacts to message.`);

        // Initialize WhatsApp connection
        const { state, saveCreds } = await useMultiFileAuthState('auth_info_baileys');
        
        const sock = makeWASocket({
            auth: state,
            browser: ['Bulk Sender', 'Chrome', '1.0.0'],
            generateHighQualityLinkPreview: true
        });

        // Handle QR code generation
        sock.ev.on('connection.update', async (update) => {
            const { connection, lastDisconnect, qr } = update;
            
            if (qr) {
                console.log('Scan the QR code below to log in:');
                qrcode.generate(qr, { small: true });
            }

            if (connection === 'close') {
                const shouldReconnect = lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
                console.log('Connection closed due to ', lastDisconnect?.error || 'unknown reason');
                if (shouldReconnect) {
                    console.log('Reconnecting...');
                    await new Promise(resolve => setTimeout(resolve, 5000));
                    sendBulkMessages();
                }
            } else if (connection === 'open') {
                console.log('✅ Connected to WhatsApp!');
                // Give it a moment to fully connect
                await new Promise(resolve => setTimeout(resolve, 2000));
                startSending(sock, contacts, message, rl);
            }
        });

        // Save credentials when updated
        sock.ev.on('creds.update', saveCreds);


    } catch (error) {
        console.error('Error:', error);
        rl.close();
        process.exit(1);
    }
}

// Function to send messages with delay
async function startSending(sock, contacts, message, rl) {
    console.log(`\nReady to send to ${contacts.length} contacts.`);
    console.log(`Message: ${message}\n`);

    const confirm = await new Promise(resolve => {
        rl.question('Type "SEND" to start sending (or anything else to cancel): ', resolve);
    });

    if (confirm.trim().toUpperCase() !== 'SEND') {
        console.log('Sending cancelled.');
        rl.close();
        process.exit(0);
    }

    let successCount = 0;
    let failCount = 0;
    const failedContacts = [];

    for (let i = 0; i < contacts.length; i++) {
        const contact = contacts[i].trim();
        if (!contact) continue;

        const phoneNumber = contact.endsWith('@s.whatsapp.net') ? contact : `${contact}@s.whatsapp.net`;
        
        try {
            console.log(`\n[${i + 1}/${contacts.length}] Sending to ${contact}...`);
            
            // Check if the contact is registered on WhatsApp
            const [result] = await sock.onWhatsApp(phoneNumber);
            
            if (!result || !result.exists) {
                throw new Error('This number is not registered on WhatsApp');
            }
            
            // Send the message
            await sock.sendMessage(phoneNumber, { 
                text: message 
            });
            
            console.log(`✅ Sent to ${contact}`);
            successCount++;
            
            // Add a delay between messages (2 seconds)
            if (i < contacts.length - 1) {
                process.stdout.write(`Waiting 2 seconds before next message...`);
                await new Promise(resolve => {
                    const spinner = ['|', '/', '-', '\\'];
                    let x = 0;
                    const interval = setInterval(() => {
                        process.stdout.write(`\r${spinner[x++ % 4]} Waiting ${2 - Math.floor(x/4)}s...`);
                    }, 250);
                    
                    setTimeout(() => {
                        clearInterval(interval);
                        process.stdout.clearLine();
                        process.stdout.cursorTo(0);
                        resolve();
                    }, 2000);
                });
            }
        } catch (error) {
            console.error(`\n❌ Failed to send to ${contact}:`, error.message);
            failCount++;
            failedContacts.push(contact);
            
            // If rate limited, wait longer
            if (error.message.includes('429') || error.message.includes('too many')) {
                console.log('Rate limited, waiting 30 seconds before continuing...');
                await new Promise(resolve => setTimeout(resolve, 30000));
            } else {
                // Shorter delay for other errors
                await new Promise(resolve => setTimeout(resolve, 2000));
            }
        }
    }

    console.log('\n📊 Sending Summary:');
    console.log(`✅ Success: ${successCount}`);
    console.log(`❌ Failed: ${failCount}`);
    
    if (failedContacts.length > 0) {
        console.log('\nFailed contacts:');
        failedContacts.forEach(contact => console.log(`- ${contact}`));
    }
    
    rl.close();
    process.exit(0);
}

// Start the bulk messaging
sendBulkMessages().catch(console.error);