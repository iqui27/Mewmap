#include "audio.h"
#include "buttons.h"
#include "config.h"
#include "publisher.h"

#include <Arduino.h>

namespace {

bool g_clip_held = false;

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("meowmap firmware 0.1.0");
  Serial.println("early prototype: no on-device classifier, e-ink is not wired");
  Serial.println("this build has not been verified on hardware");
  buttons::begin();
  audio::begin();
  publisher::begin();
}

void loop() {
  publisher::poll();

  const char* choice = buttons::poll();
  if (choice != nullptr) {
    const char* related = publisher::linkable_meow_id(millis(), config::kVoteLinkMs);
    const publisher::SubmitResult result = publisher::submit_vote(choice, related);
    if (result != publisher::SubmitResult::Ok) {
      Serial.println("meowmap: dropped vote; a vote is already waiting");
    }
  }

  if (g_clip_held && !publisher::meow_active()) {
    audio::release_clip();
    g_clip_held = false;
  }

  if (!g_clip_held && !publisher::busy()) {
    audio::poll();
    if (audio::clip_ready()) {
      const publisher::SubmitResult result = publisher::submit_meow(
          audio::clip_samples(), static_cast<size_t>(config::kClipSamples), audio::trigger_rms());
      if (result == publisher::SubmitResult::Ok) {
        g_clip_held = true;
      } else if (result == publisher::SubmitResult::Rejected) {
        Serial.println("meowmap: dropped clip");
        audio::release_clip();
      }
    }
  }
}
