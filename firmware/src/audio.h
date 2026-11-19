#pragma once

#include <stddef.h>
#include <stdint.h>

namespace audio {

void begin();
void poll();
bool clip_ready();
const int16_t* clip_samples();
float trigger_rms();
void release_clip();

}  // namespace audio
