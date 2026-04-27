#!/bin/bash
# install.sh - Script de instalacion para Google Cloud (Ubuntu/Debian)

echo "🚀 Iniciando instalacion del Bot de Bitcoin en GCloud..."

# 1. Actualizar el sistema e instalar Python y Git
echo "📦 Instalando dependencias del sistema..."
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip python3-venv git -y

# 2. Mover el bot a la ruta de produccion (Asumiendo que este script se corre desde la carpeta del bot)
BOT_DIR="/opt/bitcoin-bot"
CURRENT_DIR=$(pwd)

if [ "$CURRENT_DIR" != "$BOT_DIR" ]; then
    echo "📁 Moviendo archivos del bot a $BOT_DIR..."
    sudo mkdir -p $BOT_DIR
    sudo cp -r ./* $BOT_DIR/
    sudo chown -R $USER:$USER $BOT_DIR
    cd $BOT_DIR || exit
fi

# 3. Crear el entorno virtual de Python
echo "🐍 Creando entorno virtual de Python..."
python3 -m venv venv
source venv/bin/activate

# 4. Instalar librerías de Python
echo "📥 Instalando librerias de Python..."
pip install --upgrade pip
pip install python-binance python-telegram-bot python-dotenv

# 5. Configurar el archivo .env si no existe
if [ ! -f ".env" ]; then
    echo "⚙️  Creando archivo .env de ejemplo..."
    cat <<EOT >> .env
# Credenciales de Binance (Reemplaza esto con tus claves reales)
BINANCE_API_KEY=tu_api_key_aqui
BINANCE_SECRET_KEY=tu_secret_key_aqui

# Credenciales de Telegram (Reemplaza esto con los tuyos)
TELEGRAM_BOT_TOKEN=tu_token_del_bot_de_botfather
TELEGRAM_CHAT_ID=tu_chat_id
TELEGRAM_AUTHORIZED_USER_ID=tu_id_de_usuario_autorizado

# Opciones: "paper" (simulado) o "live" (dinero real)
BOT_TRADING_MODE=paper
EOT
    echo "⚠️ ATENCION: Por favor edita el archivo $BOT_DIR/.env con tus credenciales usando: nano .env"
fi

# 6. Instalar y habilitar el servicio de Systemd
echo "🔧 Configurando el servicio de ejecución 24/7 (Systemd)..."
sudo cp deploy/bitcoin-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable bitcoin-bot
sudo systemctl start bitcoin-bot

echo "✅ Instalacion completada."
echo "Para ver si el bot esta corriendo, usa: sudo systemctl status bitcoin-bot"
echo "Para ver los logs en tiempo real, usa: sudo journalctl -fu bitcoin-bot"
