#include "pc_demo_protocol.h"

#include <string.h>

static const char *const k_action_names[] = {
    "NONE", "FORWARD", "BACK", "LEFT", "RIGHT", "STOP"
};

const char *pc_demo_action_name(pc_demo_action_t action)
{
    if ((unsigned)action >= (sizeof(k_action_names) / sizeof(k_action_names[0]))) {
        return "NONE";
    }
    return k_action_names[action];
}

int pc_demo_parse_cmd(const uint8_t *frame, size_t length,
                      pc_demo_action_t *action)
{
    static const char prefix[] = "@CMD:";
    static const char separator[] = ";TEXT:";
    size_t end = length;
    size_t split;
    size_t action_length;
    size_t i;

    if (frame == NULL || action == NULL || length < sizeof(prefix) - 1U ||
        length > PC_DEMO_MAX_LINE) {
        return 0;
    }
    while (end > 0U && (frame[end - 1U] == '\r' || frame[end - 1U] == '\n')) {
        --end;
    }
    if (end < sizeof(prefix) - 1U ||
        memcmp(frame, prefix, sizeof(prefix) - 1U) != 0) {
        return 0;
    }

    split = sizeof(prefix) - 1U;
    while (split + sizeof(separator) - 1U <= end &&
           memcmp(frame + split, separator, sizeof(separator) - 1U) != 0) {
        ++split;
    }
    if (split + sizeof(separator) - 1U > end) {
        return 0;
    }

    action_length = split - (sizeof(prefix) - 1U);
    for (i = 0U; i < sizeof(k_action_names) / sizeof(k_action_names[0]); ++i) {
        const size_t name_length = strlen(k_action_names[i]);
        if (action_length == name_length &&
            memcmp(frame + sizeof(prefix) - 1U,
                   k_action_names[i], name_length) == 0) {
            *action = (pc_demo_action_t)i;
            return 1;
        }
    }
    return 0;
}

