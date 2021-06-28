#include "artdmx.h"
#include <console.h>
#include <generated/mem.h>
#include <irq.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <system.h>
#include <uart.h>

#define ARTNET_LENGTH (18 + 3 * 170)

static int processartnet(uint8_t buffer[ARTNET_LENGTH]) {
  if (strncmp((char *)buffer, "Art-Net", 8) != 0) {
    puts("Invalid header");
    return -1;
  }
  if ((buffer[8] != 0) | (buffer[9] != 0x50)) {
    puts("Invalid command");
    return -1;
  }
  if ((buffer[10] != 0) | (buffer[11] != 14)) {
    puts("Invalid version");
    return -1;
  }
  uint16_t universe = buffer[14] | (buffer[15] << 8);
  uint16_t length = buffer[17] | (buffer[16] << 8);
  if (length > 510) {
    printf("Invalid length of  %x", length);
    return -1;
  }
  volatile uint32_t *sdram_img_base =
      (volatile uint32_t *)(MAIN_RAM_BASE + (MAIN_RAM_SIZE / 2));
  for (uint16_t i = 0; i < (length / 3); i++) {
    uint32_t adr = 18 + i * 3;
    uint32_t rgb =
        buffer[adr] + (buffer[adr + 1] << 8) + (buffer[adr + 2] << 16);
    *(sdram_img_base + universe * 170 + i) = rgb;
  }
  return 0;
}

void nonechowrite(void) {
  static uint8_t buffer[ARTNET_LENGTH];
  while (1) {
    if (readchar() != 'n' || readchar() != 'b') {
      puts("Invalid udp header");
      return;
    }
    uint16_t len = (uint16_t)readchar() | ((uint16_t)readchar() << 8);
    if (len > ARTNET_LENGTH) {
      printf("Invalid udp length of %x", len);
      return;
    }
    for (uint16_t i = 0; i < len; i++) {
      buffer[i] = (uint8_t)readchar();
    }
    if (processartnet(buffer) != 0) {
      return;
    }
  }
}
