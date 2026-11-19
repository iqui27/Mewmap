#include "audio.h"

#include "config.h"

#include <Arduino.h>
#include <driver/i2s.h>

#include <cmath>
#include <cstring>

namespace audio {
namespace {

constexpr i2s_port_t kPort = I2S_NUM_0;
constexpr int kClipFrames = config::kClipSamples / config::kFrameSamples;

int16_t g_clip[config::kClipSamples];
int32_t g_raw[config::kFrameSamples];
int16_t g_frame[config::kFrameSamples];
int16_t g_ring[config::kPreRollFrames][config::kFrameSamples];

enum class State { Listen, Capture, Hold };

State g_state = State::Listen;
bool g_i2s = false;
int g_ring_i = 0;
int g_ring_filled = 0;
int g_clip_frames = 0;
int g_hot = 0;
float g_trigger_rms = 0.0f;
uint32_t g_last_error_ms = 0;

float frame_rms(const int16_t* frame, size_t n) {
  uint64_t acc = 0;
  for (size_t i = 0; i < n; ++i) {
    const int32_t sample = frame[i];
    acc += static_cast<uint64_t>(static_cast<int64_t>(sample) * sample);
  }
  return sqrtf(static_cast<float>(acc) / static_cast<float>(n));
}

void convert_frame() {
  // The INMP441 shifts out a 24-bit sample inside a 32-bit I2S word.
  // Keeping the top 16 bits is a starting point, not a calibration.
  // A different board may need another shift before the int16 values
  // mean anything.
  for (int i = 0; i < config::kFrameSamples; ++i) {
    g_frame[i] = static_cast<int16_t>(g_raw[i] >> 16);
  }
}

bool read_frame() {
  size_t got = 0;
  while (got < static_cast<size_t>(config::kFrameSamples)) {
    size_t bytes = 0;
    const size_t want = (static_cast<size_t>(config::kFrameSamples) - got) * sizeof(int32_t);
    const esp_err_t err = i2s_read(kPort, g_raw + got, want, &bytes, pdMS_TO_TICKS(100));
    if (err != ESP_OK || bytes < sizeof(int32_t) || bytes % sizeof(int32_t) != 0) {
      const uint32_t now = millis();
      if (now - g_last_error_ms > 2000) {
        Serial.print("meowmap: i2s read failed (");
        Serial.print(static_cast<int>(err));
        Serial.println(")");
        g_last_error_ms = now;
      }
      return false;
    }
    got += bytes / sizeof(int32_t);
  }
  convert_frame();
  return true;
}

void push_ring() {
  memcpy(g_ring[g_ring_i], g_frame, sizeof(g_frame));
  g_ring_i = (g_ring_i + 1) % config::kPreRollFrames;
  if (g_ring_filled < config::kPreRollFrames) {
    g_ring_filled++;
  }
}

void copy_preroll() {
  const int start = (g_ring_filled == config::kPreRollFrames) ? g_ring_i : 0;
  g_clip_frames = 0;
  for (int n = 0; n < g_ring_filled; ++n) {
    const int idx = (start + n) % config::kPreRollFrames;
    memcpy(g_clip + g_clip_frames * config::kFrameSamples, g_ring[idx], sizeof(g_frame));
    g_clip_frames++;
  }
}

void pause_i2s() {
  if (g_i2s) {
    i2s_stop(kPort);
  }
}

void resume_i2s() {
  if (!g_i2s) {
    return;
  }
  i2s_zero_dma_buffer(kPort);
  i2s_start(kPort);
}

}  // namespace

void begin() {
  i2s_config_t cfg;
  memset(&cfg, 0, sizeof(cfg));
  cfg.mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_RX);
  cfg.sample_rate = config::kSampleRateHz;
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;
  cfg.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  cfg.dma_buf_count = 8;
  cfg.dma_buf_len = 256;
  cfg.use_apll = false;
  cfg.tx_desc_auto_clear = false;
  cfg.fixed_mclk = 0;
  cfg.mclk_multiple = I2S_MCLK_MULTIPLE_256;
  cfg.bits_per_chan = I2S_BITS_PER_CHAN_32BIT;

  const esp_err_t installed = i2s_driver_install(kPort, &cfg, 0, nullptr);
  if (installed != ESP_OK) {
    Serial.print("meowmap: i2s install failed (");
    Serial.print(static_cast<int>(installed));
    Serial.println("). Mic capture is off.");
    return;
  }

  i2s_pin_config_t pins;
  memset(&pins, 0, sizeof(pins));
  pins.mck_io_num = I2S_PIN_NO_CHANGE;
  pins.bck_io_num = config::kPinI2sBclk;
  pins.ws_io_num = config::kPinI2sWs;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num = config::kPinI2sDin;
  const esp_err_t pin_err = i2s_set_pin(kPort, &pins);
  if (pin_err != ESP_OK) {
    Serial.print("meowmap: i2s pins failed (");
    Serial.print(static_cast<int>(pin_err));
    Serial.println("). Mic capture is off.");
    i2s_driver_uninstall(kPort);
    return;
  }

  // Low 16 bits: sample width. High 16 bits: slot width. The INMP441
  // expects a bit clock; whether this divider is right has to be checked
  // on a board (scope or a recorded tone). It has not been.
  const uint32_t bits = static_cast<uint32_t>(I2S_BITS_PER_SAMPLE_32BIT) |
                        (static_cast<uint32_t>(I2S_BITS_PER_CHAN_32BIT) << 16);
  const esp_err_t clk_err = i2s_set_clk(kPort, config::kSampleRateHz, bits, I2S_CHANNEL_MONO);
  if (clk_err != ESP_OK) {
    Serial.print("meowmap: i2s clock failed (");
    Serial.print(static_cast<int>(clk_err));
    Serial.println("). Mic capture is off.");
    i2s_driver_uninstall(kPort);
    return;
  }

  g_i2s = true;
  Serial.println("meowmap: i2s driver installed. Capture is uncalibrated and unverified.");
}

void poll() {
  if (!g_i2s || g_state == State::Hold) {
    return;
  }
  if (!read_frame()) {
    return;
  }

  if (g_state == State::Listen) {
    push_ring();
    const float rms = frame_rms(g_frame, config::kFrameSamples);
    if (rms >= config::kEnergyRmsThreshold) {
      g_hot++;
    } else {
      g_hot = 0;
    }
    if (g_hot >= config::kEnergyHotFrames) {
      g_trigger_rms = rms;
      copy_preroll();
      g_hot = 0;
      g_state = State::Capture;
      Serial.print("meowmap: energy gate open, frame rms ");
      Serial.print(rms, 1);
      Serial.print(", threshold ");
      Serial.print(config::kEnergyRmsThreshold, 1);
      Serial.println(" (uncalibrated)");
    }
    return;
  }

  memcpy(g_clip + g_clip_frames * config::kFrameSamples, g_frame, sizeof(g_frame));
  g_clip_frames++;
  if (g_clip_frames >= kClipFrames) {
    g_state = State::Hold;
    pause_i2s();
    Serial.println("meowmap: 2s clip held for publish");
  }
}

bool clip_ready() { return g_state == State::Hold; }

const int16_t* clip_samples() { return g_clip; }

float trigger_rms() { return g_trigger_rms; }

void release_clip() {
  g_state = State::Listen;
  g_clip_frames = 0;
  g_hot = 0;
  g_ring_i = 0;
  g_ring_filled = 0;
  g_trigger_rms = 0.0f;
  resume_i2s();
}

}  // namespace audio
