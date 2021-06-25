#include "spi.h"
#include <generated/csr.h>

// For GD25Q16C
#define CMD_READ 0x03

void spi_init(void);
uint8_t spi_transfer(uint8_t byte);

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
  spi_init();
  spiflash_mmap_master_cs_write(1); // CS on
  spi_transfer(CMD_READ);
  spi_transfer((adr >> 16) & 0xFF); // send adr
  spi_transfer((adr >> 8) & 0xFF);  // send adr
  spi_transfer((adr >> 0) & 0xFF);  // send adr
  uint8_t data = spi_transfer(0);
  spiflash_mmap_master_cs_write(0); // CS off
  return data;
}
