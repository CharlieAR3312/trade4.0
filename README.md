# 🚀 Bitcoin Active Scalper Bot

Trading bot automatizado para el par **BTC/USDT** en Binance, diseñado para capturar micro-fluctuaciones del mercado mediante análisis técnico de alta frecuencia (RSI) y una gestión de capital inteligente (Profit-Split).

---

## 🛠 Características Principales

*   **Estrategia Active Scalper:** Entradas basadas en el indicador **RSI** (Relative Strength Index) en temporalidades de 15 minutos.
*   **Gestión de Profit 50/50:** Recupera el 100% de tu inversión inicial + el 50% de la ganancia en USDT. El otro 50% de ganancia se mantiene en BTC para acumulación a largo plazo.
*   **True Break-Even Tracking:** Seguimiento preciso del costo promedio ponderado. El bot nunca vende en pérdida, asegurando que cada salida sea rentable sobre el costo real de adquisición.
*   **Control Total vía Telegram:** Panel interactivo para monitorear el estado, ver el PnL, pausar/reanudar y recibir notificaciones en tiempo real.
*   **Motor de Volatilidad (ATR):** Ajuste dinámico de umbrales basado en el Average True Range del mercado.

---

## 📈 Lógica de Trading

### Compras (Entrada)
*   **Gatillo:** RSI <= 30 (Zona de sobreventa).
*   **Nivel 2 (DCA):** RSI <= 25 para promediar precio si la caída continúa.

### Ventas (Salida)
*   **Condición 1:** Precio actual > Costo Promedio (Profit asegurado).
*   **Condición 2:** RSI >= 70 (Sobrecompra) **O** Trailing Stop activo (caída de 1.5% desde el pico).

---

## 📲 Comandos de Telegram

*   `/start`: Activa el panel de control interactivo.
*   `/status`: Muestra el precio actual, el costo promedio, el RSI y el profit real de la operación abierta.
*   `/pnl`: Reporte detallado de ganancias históricas y métricas de rendimiento.
*   `/logs`: Visualiza las últimas líneas de actividad del bot en el servidor.
*   `/help`: Lista de comandos disponibles.

---

## 🚀 Instalación y Despliegue

### Requisitos
*   Python 3.8+
*   API Key de Binance (con permisos de Spot Trading).
*   Token de Bot de Telegram y Chat ID.

### Configuración
1.  Clona el repositorio: `git clone https://github.com/CharlieAR3312/bitcoin-bot.git`
2.  Instala dependencias: `pip install -r requirements.txt`
3.  Configura tus credenciales en el archivo `config.py` o mediante variables de entorno en un archivo `.env`.

### Ejecución en Google Cloud (GCP)
El bot incluye archivos de configuración para desplegarse como un servicio de sistema (`systemd`):
```bash
# Actualizar código en el servidor
git pull origin main
sudo cp -r * /opt/bitcoin-bot/
sudo systemctl restart bitcoin-bot
```

---

## ⚠️ Descargo de Responsabilidad (Disclaimer)

Este software es para fines educativos y herramientas de trading. El trading de criptomonedas conlleva un riesgo significativo de pérdida de capital. No inviertas dinero que no puedas permitirte perder. El autor no se hace responsable de las pérdidas financieras incurridas por el uso de este bot.

---
*Desarrollado con ❤️ para maximizar satoshis y dólares.*
