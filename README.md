# 🚀 Bitcoin Active Scalper Bot (v2.0 - Audit Edition)

Trading bot automatizado para el par **BTC/USDT** en Binance, diseñado para capturar micro-fluctuaciones del mercado mediante análisis técnico de alta frecuencia (RSI) y una gestión de capital de grado financiero.

---

## 🛠 Características Principales

*   **Estrategia Active Scalper:** Entradas basadas en el indicador **RSI** (Relative Strength Index) y volatilidad **ATR**.
*   **Gestión de Riesgo Dinámica (Stop Loss):** Protege el capital mediante un Stop Loss dinámico basado en ATR. El bot prioriza la supervivencia del capital sobre el "bag holding".
*   **Contabilidad de Doble Cubeta:** Separa estrictamente la **Posición Activa** (capital en riesgo) de la **Ganancia Acumulada** (BTC netos). Esto garantiza un cálculo de Break-Even real y sin distorsiones.
*   **Gestión de Profit Split:** Recupera el 100% de la inversión + el 50% de la ganancia en USDT. El excedente se mueve a una bóveda de beneficios acumulados con costo base cero.
*   **Reconciliación por Delta:** Compara el balance esperado de la estrategia contra el exchange en tiempo real, ignorando fondos externos o "dust" previo.
*   **Precisión Bancaria:** Uso de `decimal.Decimal` en todos los cálculos financieros para eliminar errores de redondeo de punto flotante.

---

## 📈 Lógica de Trading

### Compras (Entrada)
*   **Gatillo Principal:** RSI <= 30 (Sobreventa).
*   **Nivel 2 (DCA):** RSI <= 25 para promediar precio si la caída continúa.
*   **Position Sizing:** El tamaño de la orden se calcula automáticamente para que una ejecución de Stop Loss no exceda el **1.5% del capital total**.

### Ventas (Salida)
*   **Profit Split:** Precio > Costo Promedio + RSI >= 70 (Sobrecompra) **O** Trailing Stop activo.
*   **Stop Loss:** Gatillo dinámico basado en ATR (típicamente entre 1% y 3% según la volatilidad).

---

## 📲 Comandos de Telegram

*   `/start`: Panel de control interactivo.
*   `/status`: Precio actual, costo promedio real, RSI y balance detallado (Activo vs Acumulado).
*   `/pnl`: Reporte de ROI basado en capital máximo desplegado y BTC netos ganados.
*   `/logs`: Visualiza la actividad reciente.

---

## 🚀 Instalación y Despliegue

### Modo Demo (Seguro y Offline)
Puedes probar la lógica completa del bot sin red y sin API Keys:
```bash
python -m bitcoin_bot.main --demo
```

### Configuración Live
1.  Clona el repositorio.
2.  Instala dependencias: `pip install -r requirements.txt`
3.  Crea un archivo `.env` con tus credenciales:
    ```env
    BINANCE_API_KEY=tu_key
    BINANCE_SECRET_KEY=tu_secret
    TELEGRAM_BOT_TOKEN=tu_token
    TELEGRAM_CHAT_ID=tu_id
    TELEGRAM_AUTHORIZED_USER_ID=tu_id
    ```
4.  Ejecuta el bot: `python -m bitcoin_bot.main`

---

## ⚠️ Descargo de Responsabilidad (Disclaimer)

Este software es para fines educativos. El trading de criptomonedas conlleva un riesgo significativo. El autor no se hace responsable de las pérdidas financieras incurridas. **Nunca operes con dinero que no puedas permitirte perder.**
