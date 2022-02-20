use core::cmp::min;
use core::fmt::Write;
use core::mem::size_of;
use core::panic::PanicInfo;

use litex_pac as pac;

#[panic_handler]
fn panic(info: &PanicInfo) -> ! {
    let mut writer = PanicWriter {};
    writeln!(writer, "{}", info).ok();
    // And reboot!

    unsafe { (*pac::CTRL::ptr()).reset.write(|w| w.soc_rst().set_bit()) };
    loop {
        unsafe { (*pac::CTRL::ptr()).reset.write(|w| w.soc_rst().set_bit()) };
    }
}

struct PanicWriter {}

impl core::fmt::Write for PanicWriter {
    fn write_str(&mut self, s: &str) -> Result<(), core::fmt::Error> {
        let uart = unsafe { &(*pac::UART::ptr()) };
        for byte in s.as_bytes() {
            while uart.txfull.read().bits() != 0 {}
            unsafe {
                uart.rxtx.write(|w| w.rxtx().bits(*byte));
            }
        }
        Ok(())
    }
}
