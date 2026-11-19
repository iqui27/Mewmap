#include "base64.h"

#include <cstdio>
#include <cstring>
#include <string>

static int g_failed = 0;

static void expect(const char* name, const uint8_t* in, size_t len, const char* want) {
  char out[1024];
  const size_t n = base64_encode(in, len, out, sizeof(out));
  if (n != std::strlen(want) || std::strcmp(out, want) != 0) {
    std::printf("FAIL %s\n  got  (%zu) %s\n  want (%zu) %s\n", name, n, out, std::strlen(want),
                want);
    g_failed++;
    return;
  }
  std::printf("ok   %s\n", name);
}

int main() {
  expect("empty", nullptr, 0, "");
  const uint8_t f[] = {'f'};
  const uint8_t fo[] = {'f', 'o'};
  const uint8_t foo[] = {'f', 'o', 'o'};
  expect("f", f, 1, "Zg==");
  expect("fo", fo, 2, "Zm8=");
  expect("foo", foo, 3, "Zm9v");

  uint8_t zeros3[3] = {0, 0, 0};
  expect("3-zero", zeros3, 3, "AAAA");

  uint8_t zeros480[480];
  std::memset(zeros480, 0, sizeof(zeros480));
  std::string want480(640, 'A');
  expect("480-zero", zeros480, 480, want480.c_str());

  uint8_t zeros160[160];
  std::memset(zeros160, 0, sizeof(zeros160));
  std::string want160(53 * 4, 'A');
  want160 += "AA==";
  expect("160-zero", zeros160, 160, want160.c_str());

  char tiny[4];
  if (base64_encode(foo, 3, tiny, sizeof(tiny)) != 0) {
    std::printf("FAIL short-buffer should return 0\n");
    g_failed++;
  } else {
    std::printf("ok   short-buffer\n");
  }

  return g_failed == 0 ? 0 : 1;
}
