#pragma once

#include <stdint.h>

// Shared with schema.json draft 0.1.0. Change both together.

#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

namespace config {

constexpr char kSchemaVersion[] = "0.1.0";

// Starting pin map. Not checked on a board.
// SPI pins 5, 18, 19, and 23 are left free for a future e-ink panel.
constexpr int kPinI2sBclk = 14;
constexpr int kPinI2sWs = 27;
constexpr int kPinI2sDin = 32;
constexpr int kPinButtonGreen = 13;
constexpr int kPinButtonRed = 21;

constexpr int kSampleRateHz = 16000;
constexpr int kFrameMs = 20;
constexpr int kFrameSamples = kSampleRateHz * kFrameMs / 1000;
constexpr int kClipMs = 2000;
constexpr int kClipSamples = kSampleRateHz * kClipMs / 1000;
constexpr int kClipBytes = kClipSamples * 2;
constexpr int kPreRollFrames = 8;

// Raw bytes per MQTT audio message. 480 is divisible by 3, so base64
// of a full slice has no padding. The last slice is 160 bytes.
constexpr int kChunkRawBytes = 480;
constexpr int kChunkCount = (kClipBytes + kChunkRawBytes - 1) / kChunkRawBytes;

constexpr uint32_t kDebounceMs = 40;
constexpr uint32_t kVoteLinkMs = 5000;

// Energy gate on the int16 samples after the >> 16 conversion.
// This number is a placeholder. It is not calibrated, and the schema
// forbids saying that it is.
constexpr float kEnergyRmsThreshold = 800.0f;
constexpr int kEnergyHotFrames = 3;

static_assert(kFrameSamples == 320, "20 ms at 16 kHz");
static_assert(kClipSamples == 32000, "2 s at 16 kHz");
static_assert(kClipBytes == 64000, "s16le clip size");
static_assert(kClipSamples % kFrameSamples == 0, "clip is a whole number of frames");
static_assert(kPreRollFrames < kClipSamples / kFrameSamples, "preroll fits in a clip");
static_assert(kChunkCount == 134, "chunk count");
static_assert(133 * kChunkRawBytes == 63840, "last chunk offset");
static_assert(kClipBytes - 133 * kChunkRawBytes == 160, "last chunk length");
static_assert(sizeof(DEVICE_ID) > 1, "DEVICE_ID is empty");
static_assert(sizeof(DEVICE_ID) <= 33, "DEVICE_ID longer than 32 characters");

}  // namespace config
