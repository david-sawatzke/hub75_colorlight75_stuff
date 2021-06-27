#include "spi.h"
#include <generated/csr.h>
#include <generated/mem.h>
#include <stdbool.h>

// For GD25Q16C
#define CMD_READ 0x03
#define CMD_READ_STATUS 0x05
#define CMD_BE_64 0xD8
#define CMD_WRITE_EN 0x06
#define CMD_WRITE_DIS 0x04
#define CMD_PAGE_PROGRAM 0x02

void spi_send_command(uint8_t cmd);
uint8_t spi_transfer(uint8_t byte);
void spi_delete_64k(uint32_t adr);
void spi_delete_img(void);
void spi_program_page(uint32_t adr, uint8_t *data);

void spi_init(void) {
  spiflash_mmap_master_phyconfig_write(
      0x010108); // xfer_len=8, xfer_width=1, xfer_mask=1, enables mosi as
                 // output but not miso
}

uint8_t spi_transfer(uint8_t byte) {
  while (spiflash_mmap_master_status_tx_ready_read() == 0)
    ;
  spiflash_mmap_master_rxtx_write(byte);
  while (spiflash_mmap_master_status_rx_ready_read() == 0)
    ;
  return spiflash_mmap_master_rxtx_read();
}

uint8_t spi_read_byte(uint32_t adr) {
  spiflash_mmap_master_cs_write(1); // CS on
  spi_transfer(CMD_READ);
  spi_transfer((adr >> 16) & 0xFF); // send adr
  spi_transfer((adr >> 8) & 0xFF);  // send adr
  spi_transfer((adr >> 0) & 0xFF);  // send adr
  uint8_t data = spi_transfer(0);
  spiflash_mmap_master_cs_write(0); // CS off
  return data;
}

void spi_send_command(uint8_t cmd) {
  spiflash_mmap_master_cs_write(1); // CS on
  spi_transfer(cmd);
  spiflash_mmap_master_cs_write(0); // CS off
}

void spi_delete_64k(uint32_t adr) {
  // Enable write mode
  spi_send_command(CMD_WRITE_EN);
  spiflash_mmap_master_cs_write(1); // CS on
  spi_transfer(CMD_BE_64);
  spi_transfer((adr >> 16) & 0xFF); // send adr
  spi_transfer((adr >> 8) & 0xFF);  // send adr
  spi_transfer((adr >> 0) & 0xFF);  // send adr
  spiflash_mmap_master_cs_write(0); // CS off, start erase cycle
  // Now let's wait until it's complete
  bool done = false;
  while (!done) {
    spiflash_mmap_master_cs_write(1); // CS on
    spi_transfer(CMD_READ_STATUS);
    uint8_t status = spi_transfer(0);
    spiflash_mmap_master_cs_write(0); // CS off
    done = !(status & 0x1);
  }
  // Write mode is disabled during the erase cycle
  // And ... we're done!
}

void spi_delete_img(void) {
  uint32_t start_adr = (1024 + 512) * 1024;
  uint32_t step = 64 * 1024;
  uint32_t steps = 512 / 64;
  for (uint32_t i = 0; i < steps; i++) {
    spi_delete_64k(start_adr + step * i);
  }
}

void spi_program_page(uint32_t adr, uint8_t *data) {
  spi_send_command(CMD_WRITE_EN);
  spiflash_mmap_master_cs_write(1); // CS on
  spi_transfer(CMD_PAGE_PROGRAM);
  spi_transfer((adr >> 16) & 0xFF); // send adr
  spi_transfer((adr >> 8) & 0xFF);  // send adr
  spi_transfer((adr >> 0) & 0xFF);  // send adr
  for (uint16_t i = 0; i < 256; i++) {
    spi_transfer(data[i]);
  }
  spiflash_mmap_master_cs_write(0); // CS on
  // Now let's wait until it's complete
  bool done = false;
  while (!done) {
    spiflash_mmap_master_cs_write(1); // CS on
    spi_transfer(CMD_READ_STATUS);
    uint8_t status = spi_transfer(0);
    spiflash_mmap_master_cs_write(0); // CS off
    done = !(status & 0x1);
  }
  // Write mode is disabled during the program cycle
}

void spi_program_image(uint32_t length) {
  spi_delete_img();
  uint32_t base_adr = (1024 + 512) * 1024;
  uint32_t step = 256;
  // Write Header
  bool indexed = hub75_ctrl_indexed_read();
  uint16_t width = hub75_ctrl_width_read();
  uint8_t data[256] = {
      width,        width >> 8,   0,    indexed << 7, length, length >> 8,
      length >> 16, length >> 24, 0x40, 0x1A,         0x58,   0xD1,
      0x01,         0x00,         0x5A, 0xDA};
  spi_program_page(base_adr, data);
  uint32_t page_count = ((length * 4 - 1) / step) + 1;
  uint8_t *sdram_img_base = (uint8_t *)(MAIN_RAM_BASE + (MAIN_RAM_SIZE / 2));
  for (uint32_t i = 0; i < page_count; i++) {
    spi_program_page(base_adr + i * step + step, sdram_img_base + i * step);
  }
}
