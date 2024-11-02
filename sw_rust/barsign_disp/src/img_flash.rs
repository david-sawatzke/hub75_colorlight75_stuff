use crate::hal;
use litex_pac as pac;
use spi_memory::{prelude::*, series25::Flash as Flash25};

static FLASH_SIZE: usize = (16 / 8) * 1024 * 1024;
static SECTOR_SIZE: usize = 4 * 1024;
pub struct Flash {
    memory: Flash25<hal::SpiMem, hal::SpiCS>,
}

impl Flash {
    pub fn new(spi: pac::SpiflashMmap) -> Self {
        let spi = hal::SpiMem::new(spi);
        let memory = Flash25::init(spi.0, spi.1).unwrap();
        Self { memory }
    }

    pub fn read_byte(&mut self, offset: usize) -> u8 {
        let eeprom =
            unsafe { core::slice::from_raw_parts_mut((0x80000000) as *mut u8, 0x00200000) };
        eeprom[offset]
    }

    pub fn read_manual_byte(&mut self, offset: usize) -> u8 {
        let mut data = [0];
        self.memory.read(offset as u32, &mut data).unwrap();
        data[0]
    }

    pub fn memory_read_test(&mut self) -> bool {
        for address in 0..FLASH_SIZE {
            if self.read_byte(address) != self.read_manual_byte(address) {
                return false;
            }
        }
        true
    }

    pub fn write_image(&mut self, data: impl Iterator<Item = u8>) {
        // Working around the fact that `chunks()` doesn't exist on iterators.
        let mut data_iter = data.enumerate();
        let mut count = 0;
        let mut done = false;
        let img_offset = (FLASH_SIZE / 4) * 3;
        while !done {
            let mut data = [0; 256];
            for i in 0..256 {
                if let Some((iter_count, data_byte)) = data_iter.next() {
                    data[i] = data_byte;
                    count = iter_count;
                } else {
                    // Fill the rest up
                    count += 1;
                    data[i] = 0;
                    done = true;
                }
            }
            let offset = count & !0xFF;
            if ((offset) & (SECTOR_SIZE - 1)) == 0 {
                self.memory
                    .erase_sectors((img_offset + count) as u32, 1)
                    .unwrap();
            }
            self.memory
                .write_bytes((img_offset + offset) as u32, &mut data)
                .unwrap();
        }
    }

    pub fn read_image(&mut self) -> &[u8] {
        let img_offset = (FLASH_SIZE / 4) * 3;
        // Small hack
        unsafe {
            core::slice::from_raw_parts((0x80000000 + img_offset) as *const u8, 0x00200000 / 4)
        }
    }
}
