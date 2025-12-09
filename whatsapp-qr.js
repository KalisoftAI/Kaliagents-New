import { makeWASocket, useMultiFileAuthState, DisconnectReason } from '@whiskeysockets/baileys';
import qrcode from 'qrcode-terminal';

// Custom logger to prevent 'logger.child is not a function' error
const customLogger = {
    level: 'silent',
    trace: () => {},
    debug: () => {},
    info: () => {},
    warn: () => {},
    error: () => {},
    fatal: () => {},
    child: () => customLogger
};

async function connectToWhatsApp() {
    console.clear();
    console.log('🚀 Initializing WhatsApp QR Code Scanner...\n');
    console.log('Please wait while we connect to WhatsApp...\n');

    try {
        const { state, saveCreds } = await useMultiFileAuthState('auth_info_baileys');
        
        const sock = makeWASocket({
            auth: state,
            printQRInTerminal: false,
            logger: customLogger,
            browser: ['WhatsApp Bot', 'Chrome', '1.0.0']
        });

        sock.ev.on('connection.update', async (update) => {
            const { qr, connection, lastDisconnect } = update;

            if (qr) {
                showQrCode(qr);
            }

            if (connection === 'open') {
                console.clear();
                console.log('\n✅ Successfully connected to WhatsApp!');
                console.log('You can now close this window and start the main bot with:');
                console.log('node index.js\n');
                
                // Keep the connection alive for a few seconds before exiting
                setTimeout(() => {
                    process.exit(0);
                }, 5000);
            }

            if (connection === 'close') {
                const shouldReconnect = lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut;
                if (shouldReconnect) {
                    console.log('\n🔄 Connection lost. Reconnecting...');
                    setTimeout(connectToWhatsApp, 2000);
                } else {
                    console.log('\n❌ Connection closed. Please restart the scanner.\n');
                    process.exit(1);
                }
            }
        });

        sock.ev.on('creds.update', saveCreds);

    } catch (error) {
        console.error('\n❌ Error:', error.message);
        console.log('\nTrying to reconnect...');
        setTimeout(connectToWhatsApp, 5000);
    }
}

function showQrCode(qr) {
    console.clear();
    console.log('\n' + '='.repeat(60));
    console.log('🔍 SCAN WHATSAPP QR CODE');
    console.log('='.repeat(60));
    console.log('📱 INSTRUCTIONS:');
    console.log('1. Open WhatsApp on your phone');
    console.log('2. Tap Menu (⋮) > Linked Devices > Link a Device');
    console.log('3. Scan the QR code below:');
    console.log('='.repeat(60) + '\n');
    
    qrcode.generate(qr, { small: false });
    
    console.log('\n' + '='.repeat(60));
    console.log('💡 TIP: Keep this window open while scanning');
    console.log('      The connection will be established automatically');
    console.log('='.repeat(60) + '\n');
}

// Start the connection
connectToWhatsApp().catch(console.error);