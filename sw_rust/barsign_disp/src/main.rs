#![no_std]
#![no_main]

use panic_halt as _;

use barsign_disp::*;
use embedded_hal::blocking::delay::DelayMs;
use embedded_hal::blocking::serial::Write;
use embedded_hal::serial::Read;
use ethernet::Eth;
use hal::*;
use litex_pac as pac;
use nb::block;
use riscv_rt::entry;
use smoltcp::iface::{EthernetInterfaceBuilder, NeighborCache};
use smoltcp::socket::{
    SocketSet, TcpSocket, TcpSocketBuffer, UdpPacketMetadata, UdpSocket, UdpSocketBuffer,
};
use smoltcp::time::{Duration, Instant};
use smoltcp::wire::{EthernetAddress, IpAddress, IpCidr};

#[entry]
fn main() -> ! {
    let peripherals = pac::Peripherals::take().unwrap();

    let mut serial = UART {
        registers: peripherals.UART,
    };

    serial.bwrite_all(b"Hello world!\n").unwrap();

    let hub75 = hub75::Hub75::new(peripherals.HUB75, peripherals.HUB75_PALETTE);
    let flash = img_flash::Flash::new(peripherals.SPIFLASH_MMAP);
    let mut delay = TIMER {
        registers: peripherals.TIMER0,
        sys_clk: 50_000_000,
    };
    let mut buffer = [0u8; 64];
    let context = menu::Context {
        serial,
        hub75,
        flash,
    };
    let mut r = menu::Runner::new(&menu::ROOT_MENU, &mut buffer, context);

    let device = Eth::new(peripherals.ETHMAC, peripherals.ETHMEM);
    let mut neighbor_cache_entries = [None; 8];
    let neighbor_cache = NeighborCache::new(&mut neighbor_cache_entries[..]);
    let mut ip_addrs = [IpCidr::new(IpAddress::v4(192, 168, 1, 50), 24)];
    let mut iface = EthernetInterfaceBuilder::new(device)
        .ethernet_addr(EthernetAddress::from_bytes(&[
            0xF6, 0x48, 0x74, 0xC8, 0xC4, 0x83,
        ]))
        .neighbor_cache(neighbor_cache)
        .ip_addrs(&mut ip_addrs[..])
        .finalize();

    let mut socket_set_entries: [_; 0] = Default::default();
    let mut socket_set = SocketSet::new(&mut socket_set_entries[..]);

    let mut time = Instant::from_millis(0);
    loop {
        match iface.poll(&mut socket_set, time) {
            Ok(_) => {}
            Err(_) => {}
        }
        if let Ok(data) = r.context.serial.read() {
            r.input_byte(if data == b'\n' { b'\r' } else { data });
        }
        match iface.poll_delay(&socket_set, time) {
            Some(Duration { millis: 0 }) => {}
            Some(delay_duration) => {
                delay.delay_ms(delay_duration.total_millis() as u32);
                time += delay_duration
            }
            None => time += Duration::from_millis(1),
        }
    }
}
