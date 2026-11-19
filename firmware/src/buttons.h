#pragma once

namespace buttons {

void begin();
// "green", "red", or nullptr when nothing new was pressed.
const char* poll();

}  // namespace buttons
