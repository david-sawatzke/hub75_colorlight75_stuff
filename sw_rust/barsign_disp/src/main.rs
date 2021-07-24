#![no_std]
#![no_main]

use panic_halt as _;

use embedded_hal::blocking::delay::DelayMs;
use embedded_hal::blocking::serial::Write;
use embedded_hal::serial::Read;
pub mod hal;
pub mod hub75;
pub mod img;
pub mod menu;
use hal::*;
use litex_pac as pac;
use nb::block;
use riscv_rt::entry;
#[entry]
fn main() -> ! {
    let peripherals = pac::Peripherals::take().unwrap();

    let mut serial = UART {
        registers: peripherals.UART,
    };

    serial.bwrite_all(b"Hello world!\n").unwrap();

    let hub75 = hub75::Hub75::new(peripherals.HUB75, peripherals.HUB75_PALETTE);

    let mut delay = TIMER {
        registers: peripherals.TIMER0,
        sys_clk: 50_000_000,
    };
    let mut buffer = [0u8; 64];
    let context = menu::Context { serial, hub75 };
    let mut r = menu::Runner::new(&menu::ROOT_MENU, &mut buffer, context);

    loop {
        let mut data = block!(r.context.serial.read()).unwrap();
        r.input_byte(if data == b'\n' { b'\r' } else { data });
    }
}
