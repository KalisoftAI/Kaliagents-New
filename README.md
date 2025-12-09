# WhatsApp Bot with QR Code Authentication

A powerful WhatsApp bot built with Node.js that provides interactive features through both WhatsApp messages and a terminal interface. This bot uses the `@whiskeysockets/baileys` library for WhatsApp Web integration.

## 🚀 Features

- **Dual Interface**: Control the bot via WhatsApp messages or terminal
- **QR Code Authentication**: Easy login process
- **Interactive Menus**: Navigate features with ease
- **Real-time Status**: Monitor bot status and uptime
- **Message Broadcasting**: Send messages to multiple contacts
- **Auto-reconnect**: Automatically reconnects if connection is lost

## 📋 Prerequisites

- Node.js v14 or higher
- npm (comes with Node.js)
- A phone number for WhatsApp verification
- Basic terminal/command line knowledge

## 🛠️ Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/yourusername/whatsapp-bot.git
   cd whatsapp-bot
   ```

2. **Install dependencies**
   ```bash
   npm install
   ```

## 🔐 Authentication

### Method 1: QR Code (Recommended for Development)

1. Run the QR code generator:
   ```bash
   node whatsapp-qr.js
   ```
2. Open WhatsApp on your phone
3. Go to Menu (⋮) > Linked Devices > Link a Device
4. Scan the QR code shown in the terminal

### Method 2: Session File

After first authentication, an `auth_info_baileys` folder will be created containing your session data.

## 🚦 Quick Start

1. **Start the bot**:

   ```bash
   npm start
   ```

   or

   ```bash
   node index.js
   ```

2. **For QR code authentication**:
   ```bash
   node whatsapp-qr.js
   ```

## 🎮 Using the Bot

### WhatsApp Commands

- `!menu` - Show main menu
- `!help` - Show help information
- `!status` - Check bot status
- `!time` - Show current server time
- `!uptime` - Show bot uptime

### Terminal Interface

When you run the bot, you'll see a menu with these options:

1. Show Bot Status
2. Send Test Message
3. Get Uptime
4. Exit

## 🔧 Troubleshooting

### Common Issues

1. **QR Code Not Working**

   - Ensure your phone has an active internet connection
   - Try deleting the `auth_info_baileys` folder and restarting
   - Make sure you're scanning with the same WhatsApp account

2. **Connection Issues**

   ```bash
   # Clear npm cache
   npm cache clean --force

   # Delete node_modules and reinstall
   rm -rf node_modules package-lock.json
   npm install
   ```

3. **Logger Errors**
   If you see "logger.child is not a function":
   ```bash
   npm install pino@latest pino-pretty@latest
   ```

## 📂 Project Structure

- `index.js` - Main bot application
- `whatsapp-qr.js` - QR code authentication
- `package.json` - Project dependencies and scripts
- `auth_info_baileys/` - Session storage (created after first login)

## 📦 Dependencies

- `@whiskeysockets/baileys` - WhatsApp Web API
- `qrcode-terminal` - Generate QR codes in terminal
- `pino` - Logging
- `dotenv` - Environment variable management

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [WhiskeySockets](https://github.com/WhiskeySockets/Baileys) for the baileys library
- All open source contributors

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request
