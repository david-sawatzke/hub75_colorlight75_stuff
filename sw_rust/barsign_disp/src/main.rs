#![no_std]
#![no_main]

use core::convert::TryInto;
use core::fmt::Write as _;

use barsign_disp::*;
use embedded_hal::blocking::serial::Write;
use embedded_hal::serial::Read;
use ethernet::{Eth, IpData, IpMacData};
use hal::*;
use heapless::Vec;
use litex_pac as pac;
use riscv_rt::entry;
use smoltcp::iface::{InterfaceBuilder, NeighborCache};
use smoltcp::socket::{TcpSocket, TcpSocketBuffer, UdpPacketMetadata, UdpSocket, UdpSocketBuffer};
use smoltcp::time::{Duration, Instant};
use smoltcp::wire::{EthernetAddress, IpAddress, IpCidr, Ipv4Address};

#[entry]
fn main() -> ! {
    let peripherals = unsafe { pac::Peripherals::steal() };

    let mut serial = UART {
        registers: peripherals.uart,
    };

    serial.bwrite_all(b"Hello world!\n").unwrap();

    let mut hub75 = hub75::Hub75::new(peripherals.hub75, peripherals.hub75_palette);
    let mut flash = img_flash::Flash::new(peripherals.spiflash_mmap);
    let mut delay = TIMER {
        registers: peripherals.timer0,
        sys_clk: 50_000_000,
    };
    let mut buffer = [0u8; 64];
    let out_data = heapless::Vec::new();
    let output = menu::Output { serial, out_data };
    // TODO First read ip & mac, and after setting them print them again to verify it worked
    // TODO spi-memory make command public to read unique id
    // TODO unique id length is dependent on the chip, so read jedec id

    let ip_data = IpData {
        ip: [192, 168, 1, 49],
    };

    let ip_mac = IpMacData::new(ip_data, &[0xde, 0xad, 0xbe, 0xef]);
    let mac_be = ip_mac.get_mac_be();

    peripherals
        .ethmac
        .mac_address1()
        .write(|w| unsafe { w.bits((mac_be >> 32) as u32) });
    peripherals
        .ethmac
        .mac_address0()
        .write(|w| unsafe { w.bits((mac_be & 0xFFFFFFFF) as u32) });

    let ip_address = IpAddress::Ipv4(Ipv4Address(ip_mac.ip));

    peripherals.ethmac.ip_address().write(|w| unsafe {
        w.bits(u32::from_be_bytes(
            ip_address.as_bytes().try_into().unwrap(),
        ))
    });
    let device = Eth::new(peripherals.ethmac, peripherals.ethmem);
    let mut neighbor_cache_entries = [None; 8];
    let neighbor_cache = NeighborCache::new(&mut neighbor_cache_entries[..]);
    let mut ip_addrs = [IpCidr::new(ip_address, 24)];
    let mut sockets_entries: [_; 2] = Default::default();
    let mut iface = InterfaceBuilder::new(device, &mut sockets_entries[..])
        .hardware_addr(EthernetAddress::from_bytes(&ip_mac.mac).into())
        .neighbor_cache(neighbor_cache)
        .ip_addrs(&mut ip_addrs[..])
        .finalize();

    let tcp_server_socket = {
        static mut TCP_SERVER_RX_DATA: [u8; 256] = [0; 256];
        static mut TCP_SERVER_TX_DATA: [u8; 256] = [0; 256];
        let tcp_rx_buffer = TcpSocketBuffer::new(unsafe { &mut TCP_SERVER_RX_DATA[..] });
        let tcp_tx_buffer = TcpSocketBuffer::new(unsafe { &mut TCP_SERVER_TX_DATA[..] });
        TcpSocket::new(tcp_rx_buffer, tcp_tx_buffer)
    };

    let udp_server_socket = {
        static mut UDP_SERVER_RX_DATA: [u8; 2048] = [0; 2048];
        static mut UDP_SERVER_TX_DATA: [u8; 2048] = [0; 2048];
        static mut UDP_SERVER_RX_METADATA: [UdpPacketMetadata; 32] = [UdpPacketMetadata::EMPTY; 32];
        static mut UDP_SERVER_TX_METADATA: [UdpPacketMetadata; 32] = [UdpPacketMetadata::EMPTY; 32];
        let udp_rx_buffer = unsafe {
            UdpSocketBuffer::new(&mut UDP_SERVER_RX_METADATA[..], &mut UDP_SERVER_RX_DATA[..])
        };
        let udp_tx_buffer = unsafe {
            UdpSocketBuffer::new(&mut UDP_SERVER_TX_METADATA[..], &mut UDP_SERVER_TX_DATA[..])
        };
        UdpSocket::new(udp_rx_buffer, udp_tx_buffer)
    };

    let tcp_server_handle = iface.add_socket(tcp_server_socket);
    let udp_server_handle = iface.add_socket(udp_server_socket);

    if let Ok(image) = img::load_image(flash.read_image()) {
        hub75.set_img_param(image.0, image.1);
        hub75.set_panel_params(image.2);
        hub75.write_img_data(0, image.3);
        // TODO indexed
        hub75.on();
    }

    let context = menu::Context {
        ip_mac,
        output,
        hub75,
        flash,
    };

    let mut r = menu::Runner::new(&menu::ROOT_MENU, &mut buffer, context);

    let mut time = Instant::from_millis(0);
    let mut telnet_active = false;
    loop {
        iface.poll(time).ok();
        // match iface.poll(time) {
        //     Ok(_) => {}
        //     Err(_) => {}
        // }

        // tcp:23: telnet for menu
        {
            let socket = iface.get_socket::<TcpSocket>(tcp_server_handle);
            if !socket.is_open() & socket.listen(23).is_err() {
                writeln!(r.context.output.serial, "Couldn't listen to telnet port").ok();
            }
            if !telnet_active & socket.is_active() {
                r.context.output.out_data.clear();
                r.context
                    .output
                    .out_data
                    .extend_from_slice(
                        // Taken from https://stackoverflow.com/a/4532395
                        // Does magic telnet stuff to behave more like a dumb serial terminal
                        b"\xFF\xFD\x22\xFF\xFA\x22\x01\x00\xFF\xF0\xFF\xFB\x01\r\nWelcome to the menu. Use \"help\" for help\r\n",
                    )
                    .expect("Should always work");
            }
            telnet_active = socket.is_active();

            if socket.may_recv() {
                while socket.can_recv() {
                    let mut buffer = [0u8; 64];
                    let received = {
                        match socket.recv_slice(&mut buffer) {
                            Ok(received) => received,
                            _ => 0,
                        }
                    };

                    for byte in &buffer[..received] {
                        if *byte != 0 {
                            r.input_byte(*byte);
                        }
                        // r.input_byte(if data == b'\n' { b'\r' } else { data });
                    }

                    // socket.send_slice(core::slice::from_ref(&data)).unwrap();
                }
            } else if socket.can_send() {
                socket.close();
            }

            if socket.can_send() {
                if let Ok(sent) = socket.send_slice(&r.context.output.out_data) {
                    let new_data = Vec::from_slice(&r.context.output.out_data[sent..])
                        .expect("New size is the same as the old size, can never fail");
                    r.context.output.out_data = new_data;
                }
            }
        }
        // udp:6454: artnet
        {
            let socket = iface.get_socket::<UdpSocket>(udp_server_handle);
            if !socket.is_open() & !socket.bind(6454).is_ok() {
                writeln!(r.context.output.serial, "Couldn't open artnet port").ok();
            }

            match socket.recv() {
                Ok((data, _endpoint)) => {
                    if let Ok((offset, data)) = artnet::packet2hub75(data) {
                        // Palette is set via the two *last* universes
                        let palette_offset = ((1 << 16) - 2) * 170;
                        if offset < palette_offset {
                            // r.context.hub75.write_img_data(offset, data);
                        } else {
                            r.context
                                .hub75
                                .set_palette((offset - palette_offset) as u8, data);
                        }
                        // writeln!(r.context.serial, "{}", offset);
                    }
                }
                Err(_) => (),
            };
        }
        if let Ok(data) = r.context.output.serial.read() {
            r.input_byte(if data == b'\n' { b'\r' } else { data });
        }

        // match iface.poll_delay(&sockets, time) {
        //     Some(Duration { millis: 0 }) => {}
        //     Some(delay_duration) => {
        //         // delay.delay_ms(delay_duration.total_millis() as u32);
        //         time += delay_duration
        //     }
        //     None => time += Duration::from_millis(1),
        // }
        time += Duration::from_millis(1);
    }
}
