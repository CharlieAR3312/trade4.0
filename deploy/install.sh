#!/bin/bash
# install.sh - Script de instalacion para Google Cloud (Ubuntu/Debian)

echo "🚀 Iniciando instalacion segura del Bot de Bitcoin en GCloud..."

# 1. Actualizar el sistema e instalar Python y Git
echo "📦 Instalando dependencias del sistema..."
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip python3-venv git -y

# 2. Crear usuario dedicado sin privilegios (trading_bot)
if ! id "trading_bot" &>/dev/null; then
    echo "🛡️ Creando usuario 'trading_bot' para ejecucion segura..."
    sudo useradd -m -s /bin/bash trading_bot
fi

# 3. Mover el bot a la ruta de produccion
BOT_DIR="/opt/bitcoin-bot"
echo "📁 Configurando directorio $BOT_DIR..."
sudo mkdir -p $BOT_DIR
sudo cp -r ./* $BOT_DIR/
sudo chown -R trading_bot:trading_bot $BOT_DIR
sudo chmod -R 750 $BOT_DIR

# 4. Crear el entorno virtual e instalar librerias (como trading_bot)
echo "🐍 Creando entorno virtual e instalando dependencias (requirements.txt)..."
sudo -u trading_bot -H bash -c "cd $BOT_DIR && python3 -m venv venv && source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt"

# 5. Configurar el archivo .env si no existe
if [ ! -f "$BOT_DIR/.env" ]; then
    echo "⚙️  Creando archivo .env de ejemplo..."
    sudo -u trading_bot -H bash -c "cat <<EOT > $BOT_DIR/.env
# Credenciales de Binance (Reemplaza esto con tus claves reales)
BINANCE_API_KEY=tu_api_key_aqui
BINANCE_SECRET_KEY=tu_secret_key_aqui

# Credenciales de Telegram
TELEGRAM_BOT_TOKEN=tu_token_del_bot_de_botfather
TELEGRAM_CHAT_ID=tu_chat_id
TELEGRAM_AUTHORIZED_USER_ID=tu_id_de_usuario_autorizado

# Opciones: \"paper\" (simulado) o \"live\" (dinero real)
BOT_TRADING_MODE=paper

# Riesgo
BOT_STOP_LOSS_ATR_MULT=1.5
BOT_RISK_PER_TRADE_PCT=0.015
EOT"
    sudo chmod 600 $BOT_DIR/.env
    echo "⚠️ ATENCION: Por favor edita el archivo $BOT_DIR/.env con tus credenciales."
fi

# 6. Instalar y habilitar el servicio de Systemd
echo "🔧 Configurando el servicio de ejecución 24/7 (Systemd)..."
sudo cp $BOT_DIR/deploy/bitcoin-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable bitcoin-bot
sudo systemctl restart bitcoin-bot

echo "✅ Instalacion segura completada."
echo "Usuario de ejecucion: trading_bot (No root)"
echo "Para ver estado: sudo systemctl status bitcoin-bot"
echo "Para ver logs: sudo journalctl -fu bitcoin-bot"
