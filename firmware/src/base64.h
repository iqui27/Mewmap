#pragma once

#include <stddef.h>
#include <stdint.h>

// Writes base64 and a trailing NUL. Returns the character count excluding
// the NUL, or 0 when out_cap is too small.
size_t base64_encode(const uint8_t* in, size_t len, char* out, size_t out_cap);
