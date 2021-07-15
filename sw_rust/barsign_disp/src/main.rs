#![no_std]
#![no_main]

use panic_halt as _;

use embedded_hal::blocking::delay::DelayMs;
use embedded_hal::blocking::serial::Write;
use litex_hal as hal;
use litex_pac as pac;
use riscv_rt::entry;

hal::uart! {
    UART: pac::UART,
}

hal::timer! {
    TIMER: pac::TIMER0,
}
#[entry]
fn main() -> ! {
    let peripherals = pac::Peripherals::take().unwrap();

    let mut serial = UART {
        registers: peripherals.UART,
    };

    serial.bwrite_all(b"Hello world!\n").unwrap();

    let mut delay = TIMER {
        registers: peripherals.TIMER0,
        sys_clk: 50_000_000,
    };

    for _ in 0..5 {
        delay.delay_ms(1000 as u32);
        serial.bwrite_all(b"Hello again!\n").unwrap();
    }
    peripherals.CTRL.reset.write(|w| w.soc_rst().set_bit());
    panic!();
}
