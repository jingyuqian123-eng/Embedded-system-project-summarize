#ifndef PC_DEMO_PROTOCOL_H
#define PC_DEMO_PROTOCOL_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define PC_DEMO_BAUDRATE          115200U
#define PC_DEMO_MAX_LINE          200U
#define PC_DEMO_MAX_IMAGE_WIDTH   480U
#define PC_DEMO_MAX_IMAGE_BYTES   6144U

typedef enum {
    PC_DEMO_ACTION_NONE = 0,
    PC_DEMO_ACTION_FORWARD,
    PC_DEMO_ACTION_BACK,
    PC_DEMO_ACTION_LEFT,
    PC_DEMO_ACTION_RIGHT,
    PC_DEMO_ACTION_STOP
} pc_demo_action_t;

/* Parse a complete @CMD:...;TEXT:... frame, with optional CR/LF at the end. */
int pc_demo_parse_cmd(const uint8_t *frame, size_t length,
                      pc_demo_action_t *action);

const char *pc_demo_action_name(pc_demo_action_t action);

#ifdef __cplusplus
}
#endif

#endif /* PC_DEMO_PROTOCOL_H */

