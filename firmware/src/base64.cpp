#include "base64.h"

static const char kAlphabet[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

size_t base64_encode(const uint8_t* in, size_t len, char* out, size_t out_cap) {
  if (out == nullptr) {
    return 0;
  }
  const size_t need = 4 * ((len + 2) / 3) + 1;
  if (out_cap < need) {
    return 0;
  }
  size_t o = 0;
  size_t i = 0;
  while (i + 3 <= len) {
    const uint32_t n = (uint32_t)in[i] << 16 | (uint32_t)in[i + 1] << 8 | in[i + 2];
    out[o++] = kAlphabet[(n >> 18) & 63];
    out[o++] = kAlphabet[(n >> 12) & 63];
    out[o++] = kAlphabet[(n >> 6) & 63];
    out[o++] = kAlphabet[n & 63];
    i += 3;
  }
  if (i < len) {
    uint32_t n = (uint32_t)in[i] << 16;
    if (i + 1 < len) {
      n |= (uint32_t)in[i + 1] << 8;
    }
    out[o++] = kAlphabet[(n >> 18) & 63];
    out[o++] = kAlphabet[(n >> 12) & 63];
    out[o++] = (i + 1 < len) ? kAlphabet[(n >> 6) & 63] : '=';
    out[o++] = '=';
  }
  out[o] = '\0';
  return o;
}
