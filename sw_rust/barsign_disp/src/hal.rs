use litex_hal as hal;
use litex_pac as pac;

hal::uart! {
    UART: pac::UART,
}

hal::timer! {
    TIMER: pac::TIMER0,
}
