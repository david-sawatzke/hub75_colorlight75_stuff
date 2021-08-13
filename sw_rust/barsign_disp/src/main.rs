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

    let tcp_server_socket = {
        static mut TCP_SERVER_RX_DATA: [u8; 8192] = [0; 8192];
        static mut TCP_SERVER_TX_DATA: [u8; 8192] = [0; 8192];
        let tcp_rx_buffer = TcpSocketBuffer::new(unsafe { &mut TCP_SERVER_RX_DATA[..] });
        let tcp_tx_buffer = TcpSocketBuffer::new(unsafe { &mut TCP_SERVER_TX_DATA[..] });
        TcpSocket::new(tcp_rx_buffer, tcp_tx_buffer)
    };

    let mut sockets_entries: [_; 1] = Default::default();
    let mut sockets = SocketSet::new(&mut sockets_entries[..]);
    let tcp_server_handle = sockets.add(tcp_server_socket);

    let mut time = Instant::from_millis(0);
    loop {
        match iface.poll(&mut sockets, time) {
            Ok(_) => {}
            Err(_) => {}
        }

        // tcp:6970: echo
        {
            let mut socket = sockets.get::<TcpSocket>(tcp_server_handle);
            if !socket.is_open() {
                socket.listen(6970).unwrap()
            }

            if socket.may_recv() {
                while socket.can_recv() {
                    let data = socket.recv(|buffer| (1, buffer[0])).unwrap();
                    socket.send_slice(core::slice::from_ref(&data)).unwrap();
                }
            } else if socket.may_send() {
                socket.close();
            }
        }

        if let Ok(data) = r.context.serial.read() {
            r.input_byte(if data == b'\n' { b'\r' } else { data });
        }

        match iface.poll_delay(&sockets, time) {
            Some(Duration { millis: 0 }) => {}
            Some(delay_duration) => {
                delay.delay_ms(delay_duration.total_millis() as u32);
                time += delay_duration
            }
            None => time += Duration::from_millis(1),
        }
    }
}
