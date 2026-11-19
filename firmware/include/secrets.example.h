#pragma once

// Copy to secrets.h (same directory) and fill in real values.
// secrets.h is gitignored. The build uses that file when it exists and
// these placeholders otherwise. Placeholders do not reach a real broker.
//
// DEVICE_ID is compiled into event ids. Use 1 to 32 characters from
// [A-Za-z0-9._:-] so the id matches schema.json. The password is compiled
// into the firmware image; do not commit secrets.h.

#define WIFI_SSID "your-ssid"
#define WIFI_PASSWORD "your-password"
#define MQTT_HOST "127.0.0.1"
#define MQTT_PORT 1883
#define MQTT_USER ""
#define MQTT_PASSWORD ""
#define MQTT_TOPIC_MEOW "meowmap/events/meow"
#define MQTT_TOPIC_VOTE "meowmap/events/vote"
#define DEVICE_ID "bowl-01"
