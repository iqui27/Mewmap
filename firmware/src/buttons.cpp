#include "buttons.h"

#include "config.h"

#include <Arduino.h>

namespace buttons {
namespace {

struct Button {
  int pin;
  const char* choice;
  int stable;
  int last;
  uint32_t changed_at;
};

Button g_green = {config::kPinButtonGreen, "green", HIGH, HIGH, 0};
Button g_red = {config::kPinButtonRed, "red", HIGH, HIGH, 0};
const char* g_queue[2] = {nullptr, nullptr};

void enqueue(const char* choice) {
  if (g_queue[0] == nullptr) {
    g_queue[0] = choice;
    return;
  }
  if (g_queue[1] == nullptr) {
    g_queue[1] = choice;
    return;
  }
  Serial.println("meowmap: dropped extra button edge");
}

void service(Button* button, uint32_t now) {
  const int level = digitalRead(button->pin);
  if (level != button->last) {
    button->last = level;
    button->changed_at = now;
  }
  if (now - button->changed_at < config::kDebounceMs) {
    return;
  }
  if (level == button->stable) {
    return;
  }
  button->stable = level;
  // Active low: a press is the transition into LOW. The release is ignored
  // so a held button does not repeat.
  if (level == LOW) {
    enqueue(button->choice);
  }
}

}  // namespace

void begin() {
  pinMode(g_green.pin, INPUT_PULLUP);
  pinMode(g_red.pin, INPUT_PULLUP);
  g_green.last = g_green.stable = digitalRead(g_green.pin);
  g_red.last = g_red.stable = digitalRead(g_red.pin);
  const uint32_t now = millis();
  g_green.changed_at = now;
  g_red.changed_at = now;
}

const char* poll() {
  const uint32_t now = millis();
  service(&g_green, now);
  service(&g_red, now);
  const char* choice = g_queue[0];
  g_queue[0] = g_queue[1];
  g_queue[1] = nullptr;
  return choice;
}

}  // namespace buttons
