#include "img_utils.h"
#include "img_indexed.h"
#include <stdint.h>
#include <system.h>

void init_img_from_header(void) {
  volatile uint32_t *sdram_img_base =
      (volatile uint32_t *)(0x40000000 + (0x00400000 / 2));
  for (uint32_t i = 0; i < img_data_len; i++) {
    // The byteorder is weird TODO fix in gateware
    *(sdram_img_base + i) = img_data[i ^ 0b11];
  }
  flush_l2_cache();
}
