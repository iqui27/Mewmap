#include "publisher.h"

#include "base64.h"
#include "config.h"
#include "food_option.h"

#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <mbedtls/sha256.h>

#include <cmath>
#include <cstring>
#include <ctime>

namespace publisher {
namespace {

WiFiClient g_net;
PubSubClient g_mqtt(g_net);

struct MeowJob {
  bool active;
  bool stamped;
  const int16_t* samples;
  float trigger_rms;
  char event_id[80];
  char captured_at[32];
  char sha256_hex[65];
  bool header_sent;
  int next_chunk;
};

struct VoteJob {
  bool pending;
  bool stamped;
  char event_id[80];
  char captured_at[32];
  char choice[8];
  char related[80];
  bool has_related;
};

MeowJob g_meow = {};
VoteJob g_vote = {};
char g_last_meow_id[80] = {};
uint32_t g_last_meow_ms = 0;
bool g_last_meow_valid = false;
uint32_t g_seq = 0;
bool g_ntp = false;
uint32_t g_wifi_attempt = 0;
bool g_wifi_started = false;
uint32_t g_mqtt_attempt = 0;
bool g_logged_clock = false;
char g_payload[2048];

bool little_endian() {
  const uint16_t probe = 1;
  uint8_t bytes[2];
  memcpy(bytes, &probe, sizeof(bytes));
  return bytes[0] == 1;
}

void make_event_id(char* dest, size_t n) {
  const uint32_t seq = g_seq++;
  const unsigned mac = static_cast<unsigned>(ESP.getEfuseMac() & 0xffffu);
  snprintf(dest, n, "%s-%04x-%lu-%lu", DEVICE_ID, mac, static_cast<unsigned long>(millis()),
           static_cast<unsigned long>(seq));
}

bool sha256_pcm(const int16_t* samples, char* hex_out, size_t hex_n) {
  if (hex_n < 65) {
    return false;
  }
  mbedtls_sha256_context ctx;
  mbedtls_sha256_init(&ctx);
  int rc = mbedtls_sha256_starts_ret(&ctx, 0);
  if (rc == 0) {
    rc = mbedtls_sha256_update_ret(&ctx, reinterpret_cast<const unsigned char*>(samples),
                                   config::kClipBytes);
  }
  unsigned char sum[32];
  if (rc == 0) {
    rc = mbedtls_sha256_finish_ret(&ctx, sum);
  }
  mbedtls_sha256_free(&ctx);
  if (rc != 0) {
    return false;
  }
  static const char* kHex = "0123456789abcdef";
  for (int i = 0; i < 32; ++i) {
    hex_out[i * 2] = kHex[sum[i] >> 4];
    hex_out[i * 2 + 1] = kHex[sum[i] & 0x0f];
  }
  hex_out[64] = '\0';
  return true;
}

bool stamp(char* dest, size_t n) {
  const time_t now = time(nullptr);
  // time() is 1970 until SNTP lands. Refuse those stamps so the schema's
  // date-time is a real clock reading when we publish.
  if (now < 1700000000) {
    return false;
  }
  struct tm tm_utc;
  if (gmtime_r(&now, &tm_utc) == nullptr) {
    return false;
  }
  return strftime(dest, n, "%Y-%m-%dT%H:%M:%SZ", &tm_utc) > 0;
}

bool ensure_stamp(char* dest, size_t n, bool* stamped) {
  if (*stamped) {
    return true;
  }
  if (!stamp(dest, n)) {
    if (!g_logged_clock) {
      Serial.println("meowmap: waiting for NTP before publishing");
      g_logged_clock = true;
    }
    return false;
  }
  g_logged_clock = false;
  *stamped = true;
  return true;
}

void add_audio(JsonObject audio, bool with_sha) {
  audio["sample_rate_hz"] = config::kSampleRateHz;
  audio["channels"] = 1;
  audio["bit_depth"] = 16;
  audio["encoding"] = "pcm_s16le";
  audio["duration_ms"] = config::kClipMs;
  audio["byte_length"] = config::kClipBytes;
  if (with_sha) {
    audio["sha256"] = g_meow.sha256_hex;
  }
}

bool publish_doc(const JsonDocument& doc, const char* topic) {
  const size_t need = measureJson(doc);
  if (need + 1 > sizeof(g_payload)) {
    Serial.print("meowmap: json is ");
    Serial.print(static_cast<unsigned>(need));
    Serial.println(" bytes and does not fit the payload buffer");
    return false;
  }
  const size_t written = serializeJson(doc, g_payload, sizeof(g_payload));
  if (written == 0 || written != need) {
    Serial.println("meowmap: json serialize failed");
    return false;
  }
  if (!g_mqtt.publish(topic, g_payload, false)) {
    Serial.println("meowmap: mqtt publish failed");
    return false;
  }
  return true;
}

bool publish_header() {
  JsonDocument doc;
  doc["schema_version"] = config::kSchemaVersion;
  doc["event_type"] = "meow";
  doc["event_id"] = g_meow.event_id;
  doc["device_id"] = DEVICE_ID;
  doc["captured_at"] = g_meow.captured_at;
  doc["message_role"] = "header";
  add_audio(doc["audio"].to<JsonObject>(), true);
  JsonObject detector = doc["detector"].to<JsonObject>();
  detector["method"] = "energy_rms";
  detector["frame_ms"] = config::kFrameMs;
  detector["trigger_rms"] = g_meow.trigger_rms;
  detector["threshold"] = config::kEnergyRmsThreshold;
  detector["consecutive_frames"] = config::kEnergyHotFrames;
  detector["calibrated"] = false;
  return publish_doc(doc, MQTT_TOPIC_MEOW);
}

bool publish_chunk(int index) {
  const int offset = index * config::kChunkRawBytes;
  int len = config::kClipBytes - offset;
  if (len > config::kChunkRawBytes) {
    len = config::kChunkRawBytes;
  }
  char encoded[700];
  const uint8_t* raw = reinterpret_cast<const uint8_t*>(g_meow.samples) + offset;
  if (base64_encode(raw, static_cast<size_t>(len), encoded, sizeof(encoded)) == 0) {
    Serial.println("meowmap: base64 buffer too small");
    return false;
  }

  JsonDocument doc;
  doc["schema_version"] = config::kSchemaVersion;
  doc["event_type"] = "meow";
  doc["event_id"] = g_meow.event_id;
  doc["device_id"] = DEVICE_ID;
  doc["captured_at"] = g_meow.captured_at;
  doc["message_role"] = "audio_chunk";
  add_audio(doc["audio"].to<JsonObject>(), false);
  JsonObject chunk = doc["chunk"].to<JsonObject>();
  chunk["index"] = index;
  chunk["count"] = config::kChunkCount;
  chunk["byte_offset"] = offset;
  chunk["byte_length"] = len;
  chunk["pcm_base64"] = encoded;
  return publish_doc(doc, MQTT_TOPIC_MEOW);
}

bool publish_vote() {
  if (!ensure_stamp(g_vote.captured_at, sizeof(g_vote.captured_at), &g_vote.stamped)) {
    return false;
  }
  JsonDocument doc;
  doc["schema_version"] = config::kSchemaVersion;
  doc["event_type"] = "vote";
  doc["event_id"] = g_vote.event_id;
  doc["device_id"] = DEVICE_ID;
  doc["captured_at"] = g_vote.captured_at;
  doc["choice"] = g_vote.choice;
  const FoodOption option = current_food_option();
  JsonObject opt = doc["option"].to<JsonObject>();
  opt["option_id"] = option.option_id;
  opt["label"] = option.label;
  opt["source"] = option.source;
  if (g_vote.has_related) {
    doc["related_meow_event_id"] = g_vote.related;
  } else {
    doc["related_meow_event_id"] = nullptr;
  }
  if (!publish_doc(doc, MQTT_TOPIC_VOTE)) {
    return false;
  }
  Serial.print("meowmap: published vote ");
  Serial.println(g_vote.event_id);
  return true;
}

void publish_next_meow_part() {
  if (!ensure_stamp(g_meow.captured_at, sizeof(g_meow.captured_at), &g_meow.stamped)) {
    return;
  }
  if (!g_meow.header_sent) {
    if (!publish_header()) {
      return;
    }
    g_meow.header_sent = true;
    Serial.print("meowmap: published meow header ");
    Serial.println(g_meow.event_id);
    return;
  }
  if (g_meow.next_chunk >= config::kChunkCount) {
    g_meow.active = false;
    g_meow.samples = nullptr;
    return;
  }
  if (!publish_chunk(g_meow.next_chunk)) {
    return;
  }
  g_meow.next_chunk++;
  if (g_meow.next_chunk == config::kChunkCount) {
    Serial.print("meowmap: published meow audio ");
    Serial.println(g_meow.event_id);
    g_meow.active = false;
    g_meow.samples = nullptr;
  }
}

void ensure_wifi() {
  if (WiFi.status() == WL_CONNECTED) {
    if (!g_ntp) {
      configTime(0, 0, "pool.ntp.org", "time.nist.gov");
      g_ntp = true;
      Serial.println("meowmap: ntp started");
    }
    return;
  }
  const uint32_t now = millis();
  if (g_wifi_started && now - g_wifi_attempt < 5000) {
    return;
  }
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  g_wifi_started = true;
  g_wifi_attempt = now;
  Serial.print("meowmap: wifi connecting to ");
  Serial.println(WIFI_SSID);
}

void ensure_mqtt() {
  if (g_mqtt.connected()) {
    return;
  }
  const uint32_t now = millis();
  if (g_mqtt_attempt != 0 && now - g_mqtt_attempt < 3000) {
    return;
  }
  g_mqtt_attempt = now;
  g_mqtt.setServer(MQTT_HOST, MQTT_PORT);
  const bool ok = MQTT_USER[0] == '\0' ? g_mqtt.connect(DEVICE_ID)
                                       : g_mqtt.connect(DEVICE_ID, MQTT_USER, MQTT_PASSWORD);
  if (ok) {
    Serial.println("meowmap: mqtt connected");
  } else {
    Serial.println("meowmap: mqtt connect failed");
  }
}

}  // namespace

void begin() {
  // Room for one audio chunk plus the MQTT header. A full 2 s clip is
  // about 85 KB of base64, so it is sent as many small messages.
  g_mqtt.setBufferSize(3072);
  g_mqtt.setSocketTimeout(2);
}

void poll() {
  ensure_wifi();
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }
  ensure_mqtt();
  if (!g_mqtt.connected()) {
    return;
  }
  g_mqtt.loop();
  // A vote is one message and should not wait behind a 134-chunk clip.
  if (g_vote.pending) {
    if (publish_vote()) {
      g_vote.pending = false;
    }
    return;
  }
  if (g_meow.active) {
    publish_next_meow_part();
  }
}

bool busy() { return g_meow.active || g_vote.pending; }

bool meow_active() { return g_meow.active; }

SubmitResult submit_meow(const int16_t* samples, size_t count, float trigger_rms) {
  if (g_meow.active) {
    return SubmitResult::Busy;
  }
  if (samples == nullptr || count != static_cast<size_t>(config::kClipSamples)) {
    return SubmitResult::Rejected;
  }
  if (!(trigger_rms >= 0.0f) || !isfinite(trigger_rms)) {
    return SubmitResult::Rejected;
  }
  if (!little_endian()) {
    Serial.println("meowmap: refused clip; PCM must be little-endian");
    return SubmitResult::Rejected;
  }
  if (!sha256_pcm(samples, g_meow.sha256_hex, sizeof(g_meow.sha256_hex))) {
    Serial.println("meowmap: sha256 failed");
    return SubmitResult::Rejected;
  }
  g_meow.samples = samples;
  g_meow.trigger_rms = trigger_rms;
  g_meow.header_sent = false;
  g_meow.next_chunk = 0;
  g_meow.stamped = stamp(g_meow.captured_at, sizeof(g_meow.captured_at));
  make_event_id(g_meow.event_id, sizeof(g_meow.event_id));
  snprintf(g_last_meow_id, sizeof(g_last_meow_id), "%s", g_meow.event_id);
  g_last_meow_ms = millis();
  g_last_meow_valid = true;
  g_meow.active = true;
  Serial.print("meowmap: queued meow ");
  Serial.println(g_meow.event_id);
  return SubmitResult::Ok;
}

SubmitResult submit_vote(const char* choice, const char* related) {
  if (g_vote.pending) {
    return SubmitResult::Busy;
  }
  if (choice == nullptr || (strcmp(choice, "green") != 0 && strcmp(choice, "red") != 0)) {
    return SubmitResult::Rejected;
  }
  snprintf(g_vote.choice, sizeof(g_vote.choice), "%s", choice);
  if (related != nullptr && related[0] != '\0') {
    snprintf(g_vote.related, sizeof(g_vote.related), "%s", related);
    g_vote.has_related = true;
  } else {
    g_vote.related[0] = '\0';
    g_vote.has_related = false;
  }
  make_event_id(g_vote.event_id, sizeof(g_vote.event_id));
  g_vote.stamped = stamp(g_vote.captured_at, sizeof(g_vote.captured_at));
  g_vote.pending = true;
  Serial.print("meowmap: queued vote ");
  Serial.println(g_vote.choice);
  return SubmitResult::Ok;
}

const char* linkable_meow_id(uint32_t now_ms, uint32_t window_ms) {
  if (g_meow.active) {
    return g_meow.event_id;
  }
  if (g_last_meow_valid && now_ms - g_last_meow_ms <= window_ms) {
    return g_last_meow_id;
  }
  return nullptr;
}

}  // namespace publisher
