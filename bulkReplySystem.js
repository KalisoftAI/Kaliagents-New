import { makeWASocket, DisconnectReason, useMultiFileAuthState } from '@whiskeysockets/baileys';
import qrcode from 'qrcode-terminal';
import fs from 'fs';
import path from 'path';
import readline from 'readline';
import { fileURLToPath } from 'url';
import { dirname } from 'path';
import 'colors';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Configuration
const CONFIG = {
    dataDir: path.join(__dirname, 'data'),
    campaignsDir: path.join(__dirname, 'data', 'campaigns'),
    contactsDir: path.join(__dirname, 'data', 'contact_lists')
};

// Ensure directories exist
[CONFIG.dataDir, CONFIG.campaignsDir, CONFIG.contactsDir].forEach(dir => {
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
    }
});

// Helper functions
const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
});

const question = (query) => new Promise(resolve => rl.question(query, resolve));

// Main class for the reply system
class BulkReplySystem {
    constructor() {
        this.sock = null;
        this.currentCampaign = null;
        this.isConnected = false;
    }

    // Initialize the system
    async init() {
        console.clear();
        console.log('🚀 WhatsApp Bulk Reply System\n'.bold.cyan);
        await this.initializeWhatsApp();
        await this.showMainMenu();
    }

    // Initialize WhatsApp connection
    async initializeWhatsApp() {
        if (this.isConnected) return;

        console.log('🔌 Connecting to WhatsApp...');
        
        const { state, saveCreds } = await useMultiFileAuthState('auth_info_baileys');
        
        this.sock = makeWASocket({
            auth: state,
            printQRInTerminal: false,
            browser: ['Bulk Reply System', 'Chrome', '1.0.0']
        });

        // Handle connection updates
        this.sock.ev.on('connection.update', (update) => {
            const { connection, lastDisconnect, qr } = update;
            
            if (qr) {
                console.log('📱 Scan the QR code below to log in:');
                qrcode.generate(qr, { small: true });
            }

            if (connection === 'close') {
                const shouldReconnect = lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
                if (shouldReconnect) {
                    console.log('Connection closed. Reconnecting...');
                    this.initializeWhatsApp();
                }
            } else if (connection === 'open') {
                console.log('✅ Connected to WhatsApp!');
                this.isConnected = true;
            }
        });

        // Save credentials when updated
        this.sock.ev.on('creds.update', saveCreds);

        // Track message status updates (delivered, read)
        this.sock.ev.on('message-receipt.update', async (updates) => {
            for (const { key, receipt } of updates) {
                try {
                    // Find which campaign this message belongs to
                    const campaigns = await this.getCampaigns();
                    for (const campaign of campaigns) {
                        const campaignFile = path.join(CONFIG.campaignsDir, String(campaign.id), 'campaign.json');
                        const campaignData = JSON.parse(fs.readFileSync(campaignFile, 'utf-8'));
                        
                        // Check if this message is part of the campaign
                        const messageIndex = campaignData.messages?.findIndex(m => m.id === key.id);
                        if (messageIndex !== -1) {
                            // Update message status
                            campaignData.messages[messageIndex].status = {
                                ...campaignData.messages[messageIndex].status,
                                [receipt.userJid]: {
                                    status: receipt.type,
                                    timestamp: new Date().toISOString()
                                }
                            };
                            
                            // Update campaign stats
                            if (receipt.type === 'read') {
                                campaignData.stats.read = (campaignData.stats.read || 0) + 1;
                            } else if (receipt.type === 'delivery') {
                                campaignData.stats.delivered = (campaignData.stats.delivered || 0) + 1;
                            }
                            
                            // Save updated campaign data
                            fs.writeFileSync(campaignFile, JSON.stringify(campaignData, null, 2));
                            break;
                        }
                    }
                } catch (error) {
                    console.error('Error updating message status:', error.message);
                }
            }
        });

        // Handle incoming messages and responses
        this.sock.ev.on('messages.upsert', async (m) => {
            if (!m.messages || m.type !== 'notify') return;
            
            const message = m.messages[0];
            if (!message.message) return;
            
            const from = message.key.remoteJid;
            const isGroup = from.endsWith('@g.us');
            const sender = isGroup ? message.key.participant : from;
            
            // Check if this is a response to a campaign message
            const campaigns = await this.getCampaigns();
for (const campaign of campaigns) {
    try {
        const campaignFile = path.join(CONFIG.campaignsDir, String(campaign.id), 'campaign.json');
        const campaignData = JSON.parse(fs.readFileSync(campaignFile, 'utf-8'));
                    
                    // Check if sender is in this campaign's recipients
                    const recipient = campaignData.recipients?.find(r => r.number === sender);
                    if (recipient) {
                        // This is a response to our campaign
                        const response = {
                            from: sender,
                            message: message.message.conversation || 'Media message',
                            timestamp: new Date().toISOString(),
                            isGroup,
                            groupInfo: isGroup ? { groupId: from, sender: sender } : undefined
                        };
                        
                        // Add to responses
                        const responsesFile = path.join(CONFIG.campaignsDir, campaign.id, 'responses.json');
                        let responses = [];
                        if (fs.existsSync(responsesFile)) {
                            responses = JSON.parse(fs.readFileSync(responsesFile, 'utf-8'));
                        }
                        responses.push(response);
                        fs.writeFileSync(responsesFile, JSON.stringify(responses, null, 2));
                        
                        // Update campaign stats
                        campaignData.stats.responses = (campaignData.stats.responses || 0) + 1;
                        fs.writeFileSync(campaignFile, JSON.stringify(campaignData, null, 2));
                        
                        console.log(`\n📩 New response to campaign "${campaignData.name}" from ${sender}`);
                        break;
                    }
                } catch (error) {
                    console.error('Error processing response:', error.message);
                }
            }
        });

        // Wait for connection
        while (!this.isConnected) {
            await new Promise(resolve => setTimeout(resolve, 1000));
        }
    }

    // Show main menu
    async showMainMenu() {
        console.clear();
        console.log('📱 WhatsApp Bulk Reply System\n'.bold.cyan);
        
        const choice = await this.promptMenu([
            'Start a new campaign',
            'View previous campaigns',
            'Check message analytics',
            'Exit'
        ]);

        switch (choice) {
            case 0:
                await this.createNewCampaign();
                break;
            case 1:
                await this.viewCampaigns();
                break;
            case 2:
                await this.showAnalytics();
                break;
            case 3:
                console.log('👋 Goodbye!');
                process.exit(0);
        }

        await this.showMainMenu();
    }

 async promptMenu(options) {
    console.log('\n'.repeat(options.length));
    options.forEach((option, index) => {
        console.log(`${index + 1}. ${option}`);
    });
    
    const choice = await question('\nChoose an option (number): ');
    return parseInt(choice) - 1;
}
    // Create a new campaign
async createNewCampaign() {
    console.clear();
    console.log('🆕 Create New Campaign\n'.bold.cyan);
    
    try {
        // Get campaign details
        const name = await question('📝 Campaign name: ');
        const message = await question('💬 Enter your message: ');
        
        // Show available contact lists
        const contactLists = fs.readdirSync(CONFIG.contactsDir)
            .filter(file => file.endsWith('.txt'));
        
        if (contactLists.length === 0) {
            console.log('\n⚠️ No contact lists found. Please create a contacts file first.'.yellow);
            console.log('Create a text file in the data/contact_lists/ directory with one number per line.');
            await question('\nPress Enter to continue...');
            return;
        }
        
        console.log('\n📋 Available contact lists:');
        contactLists.forEach((list, index) => {
            console.log(`  ${index + 1}. ${list}`);
        });
        
        const listChoice = parseInt(await question('\nSelect a contact list (number): ')) - 1;
        const selectedList = contactLists[listChoice];
        
        // Create campaign directory
        const campaignId = Date.now();
        const campaignDir = path.join(CONFIG.campaignsDir, campaignId.toString());
        fs.mkdirSync(campaignDir, { recursive: true });

        // Read contacts and create recipients.json
        const contacts = fs.readFileSync(
            path.join(CONFIG.contactsDir, selectedList),
            'utf-8'
        )
        .split('\n')
        .map(line => line.trim())
        .filter(line => line.length > 0);

        // Create recipients array with proper formatting
        const recipients = contacts.map(number => ({
            number: number.endsWith('@s.whatsapp.net') ? number : `${number}@s.whatsapp.net` 
        }));

        // Save recipients.json
        fs.writeFileSync(
            path.join(campaignDir, 'recipients.json'),
            JSON.stringify(recipients, null, 2)
        );
        
        // Save campaign data
        const campaignData = {
            id: campaignId,
            name,
            message,
            contactList: selectedList,
            status: 'draft',
            createdAt: new Date().toISOString(),
            recipients: recipients,  // Include recipients in campaign data
            stats: {
                total: recipients.length,  // Set actual count from recipients
                sent: 0,
                delivered: 0,
                read: 0,
                responses: 0
            }
        };
        
        fs.writeFileSync(
            path.join(campaignDir, 'campaign.json'),
            JSON.stringify(campaignData, null, 2)
        );
        
        console.log(`\n✅ Campaign "${name}" created successfully!`.green);
        console.log(`📋 ${recipients.length} recipients loaded from ${selectedList}`.green);
        console.log('🚀 Ready to send messages!');
        
        const confirm = await question('\nStart sending messages now? (y/n): ');
        if (confirm.toLowerCase() === 'y') {
            await this.startCampaign(campaignId);
        }
        
    } catch (error) {
        console.error('❌ Error creating campaign:', error.message);
        await question('\nPress Enter to continue...');
    }
}

    // Start sending campaign messages
    async startCampaign(campaignId) {
        const campaignDir = path.join(CONFIG.campaignsDir, campaignId.toString());
        const campaignData = JSON.parse(fs.readFileSync(path.join(campaignDir, 'campaign.json')));
        
        console.clear();
        console.log(`🚀 Starting Campaign: ${campaignData.name}\n`.bold.cyan);
        
        // Read contacts
        const contacts = fs.readFileSync(
            path.join(CONFIG.contactsDir, campaignData.contactList),
            'utf-8'
        ).split('\n')
        .map(line => line.trim())
        .filter(line => line.length > 0);
        
        campaignData.stats.total = contacts.length;
        campaignData.status = 'sending';
        this.saveCampaignData(campaignId, campaignData);
        
        console.log(`📤 Sending to ${contacts.length} contacts...\n`);
        
        // Send messages with rate limiting
        for (let i = 0; i < contacts.length; i++) {
            const contact = contacts[i];
            const progress = `[${i + 1}/${contacts.length}]`.padEnd(10);
            
            try {
                process.stdout.write(`${progress} Sending to ${contact}... `);
                
                await this.sock.sendMessage(`${contact}@s.whatsapp.net`, {
                    text: campaignData.message
                });
                
                campaignData.stats.sent++;
                this.saveCampaignData(campaignId, campaignData);
                
                process.stdout.write('✅\n');
                
                // Rate limiting: 2 seconds between messages
                if (i < contacts.length - 1) {
                    process.stdout.write(`⏳ Waiting 2s... (${Math.round(((i + 1) / contacts.length) * 100)}%)`);
                    await new Promise(resolve => {
                        setTimeout(() => {
                            process.stdout.clearLine();
                            process.stdout.cursorTo(0);
                            resolve();
                        }, 2000);
                    });
                }
                
            } catch (error) {
                console.error(`❌ Failed to send to ${contact}:`, error.message);
            }
        }
        
        campaignData.status = 'sent';
        campaignData.completedAt = new Date().toISOString();
        this.saveCampaignData(campaignId, campaignData);
        
        console.log(`\n🎉 Campaign "${campaignData.name}" completed!`.green);
        console.log(`📊 Sent: ${campaignData.stats.sent}/${campaignData.stats.total}`);
        
        await question('\nPress Enter to continue...');
    }

    // Save campaign data
    saveCampaignData(campaignId, data) {
        const campaignDir = path.join(CONFIG.campaignsDir, campaignId.toString());
        fs.writeFileSync(
            path.join(campaignDir, 'campaign.json'),
            JSON.stringify(data, null, 2)
        );
    }

    // View previous campaigns
    async viewCampaigns() {
        try {
            console.clear();
            console.log('📋 Previous Campaigns\n'.bold.cyan);
            
            // Ensure campaigns directory exists
            if (!fs.existsSync(CONFIG.campaignsDir)) {
                console.log('No campaigns found.'.gray);
                await question('\nPress Enter to continue...');
                return;
            }
            
            // Read all campaign directories
            const campaigns = [];
            const dirs = fs.readdirSync(CONFIG.campaignsDir, { withFileTypes: true });
            
            for (const dirent of dirs) {
                if (dirent.isDirectory()) {
                    try {
                        const campaignPath = path.join(CONFIG.campaignsDir, dirent.name, 'campaign.json');
                        if (fs.existsSync(campaignPath)) {
                            const data = JSON.parse(fs.readFileSync(campaignPath, 'utf-8'));
                            campaigns.push({ id: dirent.name, ...data });
                        }
                    } catch (e) {
                        console.error(`Error reading campaign ${dirent.name}:`, e.message);
                    }
                }
            }
            
            if (campaigns.length === 0) {
                console.log('No valid campaigns found.'.gray);
                await question('\nPress Enter to continue...');
                return;
            }
            
            // Sort by creation date (newest first)
            campaigns.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
            
            // Display campaigns
            console.log('\nAvailable Campaigns:');
            campaigns.forEach((campaign, index) => {
                const status = campaign.status === 'sent' ? '✅' : '⏳';
                console.log(`${index + 1}. ${status} ${campaign.name} (${campaign.stats.sent}/${campaign.stats.total}) - ${new Date(campaign.createdAt).toLocaleString()}`);
            });
            
            const choice = await question('\nSelect a campaign to view details (or press Enter to go back): ');
            if (choice && !isNaN(choice) && choice > 0 && choice <= campaigns.length) {
                const selected = campaigns[parseInt(choice) - 1];
                if (selected && selected.id) {
                    // Ensure the ID is passed as a string
                    await this.viewCampaignDetails(String(selected.id));
                }
            }
            
        } catch (error) {
            console.error('❌ Error loading campaigns:', error.message);
            await question('\nPress Enter to continue...');
        }
    }

    // View campaign details
    async viewCampaignDetails(campaignId) {
        try {
            // Ensure campaignId is a string
            campaignId = String(campaignId);
            
            // Validate campaign directory exists
            const campaignDir = path.join(CONFIG.campaignsDir, campaignId);
            if (!fs.existsSync(campaignDir)) {
                throw new Error(`Campaign directory not found: ${campaignId}`);
            }
            
            // Check if campaign file exists
            const campaignFile = path.join(campaignDir, 'campaign.json');
            if (!fs.existsSync(campaignFile)) {
                throw new Error('Campaign data file not found');
            }
            
            // Read and parse campaign data with error handling
            let campaignData;
            try {
                campaignData = JSON.parse(fs.readFileSync(campaignFile, 'utf-8'));
            } catch (e) {
                throw new Error(`Failed to parse campaign data: ${e.message}`);
            }
            
            console.clear();
            console.log(`📊 Campaign: ${campaignData.name || 'Unnamed Campaign'}\n`.bold.cyan);
            console.log(`📝 Message: ${campaignData.message || 'No message'}`);
            console.log(`📅 Created: ${campaignData.createdAt ? new Date(campaignData.createdAt).toLocaleString() : 'Unknown'}`);
            
            if (campaignData.completedAt) {
                console.log(`✅ Completed: ${new Date(campaignData.completedAt).toLocaleString()}`);
            } else {
                console.log('🔄 Status: In Progress');
            }
            
            // Display statistics with default values if not present
            const stats = campaignData.stats || {};
            console.log('\n📊 Statistics:');
            console.log(`├── Total Contacts: ${stats.total || 0}`);
            console.log(`├── Messages Sent: ${stats.sent || 0}`);
            console.log(`├── Messages Delivered: ${stats.delivered || 0}`);
            console.log(`├── Messages Read: ${stats.read || 0}`);
            console.log(`└── Responses: ${stats.responses || 0}`);
            
            // Show menu options
            console.log('\nOptions:');
            console.log('1. View responses');
            console.log('2. Send follow-up');
            console.log('3. Back to list');
            
            const choice = await question('\nChoose an option: ');
            
            switch (choice) {
                case '1':
                    await this.viewCampaignResponses(campaignIdStr);
                    break;
                case '2':
                    await this.sendFollowUp(campaignIdStr);
                    break;
                default:
                    return;
            }
        } catch (error) {
            console.error('❌ Error viewing campaign details:', error.message);
            await question('\nPress Enter to continue...');
        }
    }

    // Helper method to get all campaigns
    async getCampaigns() {
        if (!fs.existsSync(CONFIG.campaignsDir)) {
            return [];
        }
        
        const campaigns = [];
        const dirs = fs.readdirSync(CONFIG.campaignsDir, { withFileTypes: true });
        
        for (const dirent of dirs) {
            if (dirent.isDirectory()) {
                try {
                    const campaignPath = path.join(CONFIG.campaignsDir, dirent.name, 'campaign.json');
                    if (fs.existsSync(campaignPath)) {
                        const data = JSON.parse(fs.readFileSync(campaignPath, 'utf-8'));
                        campaigns.push({ id: dirent.name, ...data });
                    }
                } catch (e) {
                    console.error(`Error reading campaign ${dirent.name}:`, e.message);
                }
            }
        }
        
        return campaigns;
    }

    // View campaign responses
    async viewCampaignResponses(campaignId) {
        console.clear();
        console.log('📨 Campaign Responses\n'.bold.cyan);
        
        try {
            // Ensure campaignId is a string
            const campaignIdStr = String(campaignId);
            
            // Construct paths safely
            const campaignDir = path.join(CONFIG.campaignsDir, campaignIdStr);
            const campaignFile = path.join(campaignDir, 'campaign.json');
            const responsesPath = path.join(campaignDir, 'responses.json');
            
            // Check if campaign directory and files exist
            if (!fs.existsSync(campaignDir)) {
                throw new Error(`Campaign directory not found: ${campaignIdStr}`);
            }
            if (!fs.existsSync(campaignFile)) {
                throw new Error('Campaign data file not found');
            }
            
            // Load campaign data
            const campaignData = JSON.parse(fs.readFileSync(campaignFile, 'utf-8'));
            
            // Check if responses file exists
            if (!fs.existsSync(responsesPath)) {
                console.log('No responses yet.'.gray);
                await question('\nPress Enter to continue...');
                return;
            }
            
            // Read and parse responses with error handling
            let responses;
            try {
                responses = JSON.parse(fs.readFileSync(responsesPath, 'utf-8'));
            } catch (e) {
                throw new Error(`Failed to parse responses: ${e.message}`);
            }
            
            // Display campaign info
            console.log(`📊 Campaign: ${campaignData.name || 'Unnamed Campaign'}`);
            console.log(`📅 Created: ${campaignData.createdAt ? new Date(campaignData.createdAt).toLocaleString() : 'Unknown'}\n`);
            
            // Display responses
            if (!Array.isArray(responses) || responses.length === 0) {
                console.log('No responses found.'.gray);
            } else {
                console.log(`📋 Found ${responses.length} responses (${campaignData.stats?.responses || 0} total):\n`);
                responses.slice(0, 20).forEach((response, index) => {
                    const timestamp = response.timestamp ? new Date(response.timestamp).toLocaleString() : 'Unknown time';
                    const from = response.from ? response.from.split('@')[0] : 'Unknown';
                    console.log(`#${index + 1} [${timestamp}]`);
                    console.log(`From: ${from}`);
                    if (response.isGroup) {
                        console.log(`Group: ${response.groupInfo?.groupId?.split('@')[0] || 'Unknown'}`);
                    }
                    console.log(`Message: ${response.message || 'No message content'}`);
                    console.log('─'.repeat(50));
                });
                
                if (responses.length > 20) {
                    console.log(`\n... and ${responses.length - 20} more responses.`);
                }
                
                // Show message status summary
                console.log('\n📊 Message Status:');
                console.log(`├── Total Sent: ${campaignData.stats?.sent || 0}`);
                console.log(`├── Delivered: ${campaignData.stats?.delivered || 0}`);
                console.log(`├── Read: ${campaignData.stats?.read || 0}`);
                console.log(`└── Response Rate: ${campaignData.stats?.sent ? 
                    Math.round(((campaignData.stats.responses || 0) / campaignData.stats.sent) * 100) : 0}%`);
            }
            
            await question('\nPress Enter to continue...');
            
        } catch (error) {
            console.error('❌ Error loading responses:', error.message);
            await question('\nPress Enter to continue...');
        }
    }

    // Send follow-up to campaign
   async sendFollowUp(campaignId) {
    console.clear();
    console.log('📤 Send Follow-up\n'.bold.cyan);
    
    try {
        // Ensure campaignId is a string and use consistent variable name
        campaignId = String(campaignId);
        console.log('Processing campaign ID (as string):', campaignId);
        
        // Construct paths safely
        const campaignDir = path.join(CONFIG.campaignsDir, campaignId);
        const campaignFile = path.join(campaignDir, 'campaign.json');
        
        // Validate campaign directory and file
        if (!fs.existsSync(campaignDir) || !fs.existsSync(campaignFile)) {
            throw new Error('Campaign data not found. The campaign might have been deleted.');
        }
        
        // Read and parse campaign data
        const campaignData = JSON.parse(fs.readFileSync(campaignFile, 'utf-8'));
        
        // Debug: Log campaign data structure
        console.log('Campaign directory exists:', fs.existsSync(campaignDir));
console.log('Campaign file exists:', fs.existsSync(campaignFile));
console.log('Campaign file path:', campaignFile);


        // Check WhatsApp connection
        if (!this.sock?.user) {
            throw new Error('Not connected to WhatsApp. Please make sure you are logged in.');
        }
        
        // Get follow-up message
        const message = (await question('✏️  Enter your follow-up message (or press Enter to cancel): ')).trim();
        if (!message) {
            console.log('\n❌ Follow-up cancelled.');
            await question('\nPress Enter to continue...');
            return;
        }
        
        // Get recipients from campaign data or try to load from file
        let recipients = [];
        
        // Try to get from campaign data first
        if (campaignData.recipients?.length > 0) {
            recipients = campaignData.recipients;
            console.log(`\nℹ️  Found ${recipients.length} recipients in campaign data.`);
        } 
        // If no recipients in campaign data, try to load from recipients.json
        else {
            const recipientsFile = path.join(campaignDir, 'recipients.json');
            if (fs.existsSync(recipientsFile)) {
                try {
                    recipients = JSON.parse(fs.readFileSync(recipientsFile, 'utf-8'));
                    console.log(`\nℹ️  Loaded ${recipients.length} recipients from recipients.json`);
                } catch (e) {
                    console.error('❌ Error loading recipients file:', e.message);
                }
            }
        }
        
        // In the "If still no recipients, check for messages.json" section, replace with:
if (recipients.length === 0) {
    const messagesFile = path.join(campaignDir, 'messages.json');
    if (fs.existsSync(messagesFile)) {
        try {
            const messages = JSON.parse(fs.readFileSync(messagesFile, 'utf-8'));
            // Extract unique recipients from sent messages
            const recipientSet = new Set();
            messages.forEach(msg => {
                if (msg.key && msg.key.remoteJid) {
                    // Extract the phone number from the JID
                    const number = msg.key.remoteJid.split('@')[0];
                    if (number) recipientSet.add(number);
                }
            });
            
            if (recipientSet.size > 0) {
                recipients = Array.from(recipientSet).map(number => ({ 
                    number: number.endsWith('@s.whatsapp.net') ? number : `${number}@s.whatsapp.net`
                }));
                console.log(`\nℹ️  Found ${recipients.length} recipients from sent messages history.`);
                
                // Update campaign data with found recipients
                campaignData.recipients = recipients;
                fs.writeFileSync(campaignFile, JSON.stringify(campaignData, null, 2));
            } else {
                console.log('\nℹ️  No recipients found in message history.');
            }
        } catch (e) {
            console.error('❌ Error loading messages file:', e.message);
        }
    } else {
        console.log('\nℹ️  No message history file found for this campaign.');
    }
}
        
        // Final check if we have recipients
        if (recipients.length === 0) {
            throw new Error('No recipients found for this campaign. Cannot send follow-up.');
        }
        
        // Show confirmation
        const confirm = await question(`\nSend this follow-up to ${recipients.length} contacts? (y/n): `);
        if (confirm.toLowerCase() !== 'y') {
            console.log('\n❌ Follow-up cancelled.');
            await question('\nPress Enter to continue...');
            return;
        }
        
        console.log('\n🚀 Sending follow-ups...');
        
        // Create follow-up data
        const followUpData = {
            id: `followup_${Date.now()}`,
            message: message,
            sentAt: new Date().toISOString(),
            recipients: []
        };
        
        // Track results
        let successCount = 0;
        let failCount = 0;
        
        // Send messages
        for (let i = 0; i < recipients.length; i++) {
            const recipient = recipients[i];
            const phoneNumber = recipient.number.endsWith('@s.whatsapp.net') ? 
                recipient.number : 
                `${recipient.number}@s.whatsapp.net`;
            
            try {
                // Show progress
                const progress = Math.round(((i + 1) / recipients.length) * 100);
                process.stdout.write(`\r⏳ Sending to ${i + 1}/${recipients.length} (${progress}%)...`);
                
                // Send message
                await this.sock.sendMessage(phoneNumber, { text: message });
                
                // Update success count
                successCount++;
                
                // Save successful delivery
                followUpData.recipients.push({
                    number: recipient.number,
                    status: 'sent',
                    timestamp: new Date().toISOString()
                });
                
                // Add delay to avoid rate limiting (1 second between messages)
                if (i < recipients.length - 1) {
                    await new Promise(resolve => setTimeout(resolve, 1000));
                }
                
            } catch (error) {
                console.error(`\n❌ Error sending to ${recipient.number}:`, error.message);
                failCount++;
                
                // Save failed delivery
                followUpData.recipients.push({
                    number: recipient.number,
                    status: 'failed',
                    error: error.message,
                    timestamp: new Date().toISOString()
                });
            }
        }
        
        // Save follow-up data
        const followUpsPath = path.join(campaignDir, 'followups.json');
        let followUps = [];
        
        if (fs.existsSync(followUpsPath)) {
            followUps = JSON.parse(fs.readFileSync(followUpsPath, 'utf-8'));
        }
        
        followUps.push(followUpData);
        fs.writeFileSync(followUpsPath, JSON.stringify(followUps, null, 2));
        
        // Show summary
        console.log(`\n\n✅ Follow-up completed!`);
        console.log(`   - Successfully sent: ${successCount}`);
        console.log(`   - Failed to send: ${failCount}`);
        
        // Update campaign stats
        if (campaignData.stats) {
            campaignData.stats.followUpsSent = (campaignData.stats.followUpsSent || 0) + successCount;
            fs.writeFileSync(campaignFile, JSON.stringify(campaignData, null, 2));
        }
        
    } catch (error) {
        console.error('\n❌ Error in sendFollowUp:', error.message);
        if (error.stack) {
            console.error('Stack:', error.stack.split('\n').slice(0, 3).join('\n'));
        }
    } finally {
        await question('\nPress Enter to continue...');
    }
}
    // Show analytics dashboard
    async showAnalytics() {
        console.clear();
        console.log('📊 Analytics Dashboard\n'.bold.cyan);
        
        try {
            const campaigns = await this.getCampaigns();
            
            if (campaigns.length === 0) {
                console.log('No campaigns found. Create a campaign to see analytics.'.gray);
                await question('\nPress Enter to continue...');
                return;
            }
            
            // Sort campaigns by creation date (newest first)
            campaigns.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
            
            // Display summary statistics
            console.log('📈 Campaign Performance Summary\n'.bold.underline);
            
            // Overall stats
            const totalCampaigns = campaigns.length;
            const totalMessages = campaigns.reduce((sum, c) => sum + (c.stats?.sent || 0), 0);
            const totalResponses = campaigns.reduce((sum, c) => sum + (c.stats?.responses || 0), 0);
            const avgResponseRate = totalMessages > 0 
                ? Math.round((totalResponses / totalMessages) * 100) 
                : 0;
                
            console.log(`📊 Total Campaigns: ${totalCampaigns}`);
            console.log(`📤 Total Messages Sent: ${totalMessages}`);
            console.log(`📥 Total Responses: ${totalResponses}`);
            console.log(`📊 Average Response Rate: ${avgResponseRate}%\n`);
            
            // Campaign list with key metrics
            console.log('📋 Campaign Performance'.bold.underline);
            console.log('─'.repeat(100));
            console.log('Name'.padEnd(20) + 'Sent'.padStart(10) + 'Delivered'.padStart(12) + 'Read'.padStart(10) + 'Responses'.padStart(12) + 'Rate'.padStart(10) + 'Status'.padStart(15));
            console.log('─'.repeat(100));
            
            for (const campaign of campaigns) {
                const stats = campaign.stats || {};
                const responseRate = stats.sent > 0 
                    ? Math.round(((stats.responses || 0) / stats.sent) * 100) 
                    : 0;
                const status = campaign.completedAt ? '✅ Completed' : '⏳ In Progress';
                const delivered = stats.delivered || 0;
                const read = stats.read || 0;
                
                console.log(
                    `${campaign.name.substring(0, 18).padEnd(20)}` +
                    `${stats.sent || 0}`.padStart(10) +
                    `${delivered}`.padStart(12) +
                    `${read}`.padStart(10) +
                    `${stats.responses || 0}`.padStart(12) +
                    `${responseRate}%`.padStart(10) +
                    status.padStart(15)
                );
            }
            
            // Show response time analysis if we have response data
            const campaignsWithResponses = campaigns.filter(c => c.stats?.responses > 0);
            if (campaignsWithResponses.length > 0) {
                console.log('\n⏱️  Response Time Analysis'.bold.underline);
                
                // Calculate average response time for each campaign
                for (const campaign of campaignsWithResponses) {
                    try {
                        const responsesPath = path.join(CONFIG.campaignsDir, campaign.id, 'responses.json');
                        if (fs.existsSync(responsesPath)) {
                            const responses = JSON.parse(fs.readFileSync(responsesPath, 'utf-8'));
                            if (responses.length > 0) {
                                const campaignStart = new Date(campaign.createdAt);
                                const responseTimes = responses
                                    .filter(r => r.timestamp)
                                    .map(r => (new Date(r.timestamp) - campaignStart) / (1000 * 60)); // in minutes
                                
                                if (responseTimes.length > 0) {
                                    const avgResponseTime = Math.round(responseTimes.reduce((a, b) => a + b, 0) / responseTimes.length);
                                    const minTime = Math.min(...responseTimes);
                                    const maxTime = Math.max(...responseTimes);
                                    
                                    console.log(`\n📊 ${campaign.name}:`);
                                    console.log(`   ├── First Response: ${minTime.toFixed(0)} minutes`);
                                    console.log(`   ├── Last Response: ${maxTime.toFixed(0)} minutes`);
                                    console.log(`   └── Average Response Time: ${avgResponseTime} minutes`);
                                }
                            }
                        }
                    } catch (e) {
                        console.error(`Error analyzing response times for ${campaign.name}:`, e.message);
                    }
                }
            }
            
            // Show best performing campaign
            if (campaigns.length > 1) {
                const bestCampaign = [...campaigns].sort((a, b) => {
                    const aRate = a.stats?.sent ? (a.stats.responses || 0) / a.stats.sent : 0;
                    const bRate = b.stats?.sent ? (b.stats.responses || 0) / b.stats.sent : 0;
                    return bRate - aRate;
                })[0];
                
                if (bestCampaign?.stats?.sent > 0) {
                    const responseRate = Math.round(((bestCampaign.stats.responses || 0) / bestCampaign.stats.sent) * 100);
                    console.log(`\n🏆 Best Performing Campaign: ${bestCampaign.name} (${responseRate}% response rate)`);
                }
            }
            
            await question('\nPress Enter to continue...');
            
        } catch (error) {
            console.error('❌ Error loading analytics:', error.message);
            await question('\nPress Enter to continue...');
        }
    }
}

// Start the application
const app = new BulkReplySystem();
app.init().catch(console.error);

// Handle process termination
process.on('SIGINT', () => {
    console.log('\n👋 Goodbye!');
    process.exit(0);
});