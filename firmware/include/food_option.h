#pragma once

// The voting booth is supposed to show one food on an e-ink panel.
// No panel is selected in this scaffold, so there is no driver and the
// only honest answer is "nothing is on screen".

struct FoodOption {
  const char* option_id;
  const char* label;
  const char* source;
};

inline FoodOption current_food_option() {
  return {"unassigned", "", "none"};
}
