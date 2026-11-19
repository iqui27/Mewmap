#pragma once

#include <stddef.h>
#include <stdint.h>

namespace publisher {

enum class SubmitResult { Ok, Busy, Rejected };

void begin();
void poll();
bool busy();
bool meow_active();

SubmitResult submit_meow(const int16_t* samples, size_t count, float trigger_rms);
SubmitResult submit_vote(const char* choice, const char* related_meow_or_null);

// Pointer is valid until the next meow replaces it. nullptr when none.
const char* linkable_meow_id(uint32_t now_ms, uint32_t window_ms);

}  // namespace publisher
