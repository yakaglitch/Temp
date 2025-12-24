# Umweltmess- und Langzeitdatenerfassungssystem (Raspberry Pi, BME280)

Dieses Repository enthält eine schlanke Umsetzung für ein langfristig wartbares
Umweltmesssystem auf Raspberry-Pi-Basis. Es erfasst Temperatur, Luftdruck und
relative Luftfeuchte über einen BME280, glättet die Messwerte (Moving Average)
und speichert sie in einer transparenten, redundanten CSV-Struktur. Zusätzlich
wird eine Live-Datei für eine read-only Webansicht bereitgestellt.

## Features

- 50 Hz Messzyklus (konfigurierbar)
- Glättung über 50 Samples (Moving Average)
- Speicherung im 1-Minuten-Takt
- CSV-Rotation (Jahr/Monat) + Backup-Dateien
- Live-JSON für die Webansicht (read-only)
- Robust bei Sensorfehlern (keine Dummy-Daten)

## Struktur

```
.
├── data/                # Datenspeicher (CSV + live.json)
│   └── BU/              # Backup-Dateien
├── src/
│   ├── bme280.py         # BME280 Treiber (smbus2)
│   └── env_logger.py     # Hauptprogramm
├── web/
│   └── index.html        # Live-Ansicht (read-only)
└── requirements.txt
```

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Ausführung

```bash
python src/env_logger.py
```

## Datenformate

**CSV pro Minute** (`data/YYYY.csv`, `data/YYYY_MM.csv` + Backups):

```
timestamp,epoch,temperature_c,pressure_hpa,humidity_rh
2025-12-01T12:34:00+00:00,1764592440,22.134,1009.331,41.882
```

**Live-Daten** (`data/live.json`):

```json
{
  "timestamp": "2025-12-01T12:34:12+00:00",
  "epoch": 1764592452,
  "temperature_c": 22.134,
  "pressure_hpa": 1009.331,
  "humidity_rh": 41.882
}
```

## Webzugriff (read-only)

- Stelle `data/` und `web/` über einen Webserver wie `nginx` read-only bereit.
- `web/index.html` lädt `data/live.json` für die Live-Ansicht.
- CSV-Dateien lassen sich über Autoindex direkt herunterladen.

## Hinweise

- Der I2C-Bus und die Adresse des Sensors sind in `src/env_logger.py` konfigurierbar.
- Das Projekt nutzt `smbus2` für den direkten I2C-Zugriff.
