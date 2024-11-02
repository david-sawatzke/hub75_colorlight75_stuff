use core::fmt::Write;
use embedded_hal::prelude::_embedded_hal_serial_Write;

use crate::ethernet::IpMacData;
use crate::hal;
use crate::hub75::{Hub75, OutputMode};
use crate::img_flash::Flash;
use heapless::Vec;
use litex_pac::pac;
pub use menu::Runner;
use menu::*;

pub struct Output {
    pub serial: hal::UART,
    // Should be large enough for the help output
    pub out_data: Vec<u8, 500>,
}

impl core::fmt::Write for Output {
    fn write_str(&mut self, s: &str) -> Result<(), core::fmt::Error> {
        self.serial.write_str(s).ok();
        for byte in s.as_bytes() {
            if *byte == b'\n' {
                self.out_data.push(b'\r').ok();
            }
            self.out_data.push(*byte).ok();
        }
        Ok(())
    }
}

pub struct Context {
    pub output: Output,
    pub hub75: Hub75,
    pub flash: Flash,
    pub ip_mac: IpMacData,
}

impl core::fmt::Write for Context {
    fn write_str(&mut self, s: &str) -> Result<(), core::fmt::Error> {
        self.output.write_str(s).ok();
        Ok(())
    }
}
pub const ROOT_MENU: Menu<Context> = Menu {
    label: "root",
    items: &[
        &Item {
            item_type: ItemType::Callback {
                function: reboot,
                parameters: &[],
            },
            command: "reboot",
            help: Some("Reboot the soc"),
        },
        &Item {
            item_type: ItemType::Callback {
                function: default_image,
                parameters: &[],
            },
            command: "default_image",
            help: Some("Displays the default image"),
        },
        &Item {
            item_type: ItemType::Callback {
                function: default_indexed_image,
                parameters: &[],
            },
            command: "default_indexed_image",
            help: Some("Displays the default indexed image"),
        },
        &Item {
            item_type: ItemType::Callback {
                function: load_spi_image,
                parameters: &[],
            },
            command: "load_spi_image",
            help: Some("Displays the spi image"),
        },
        &Item {
            item_type: ItemType::Callback {
                function: save_spi_image,
                parameters: &[],
            },
            command: "save_spi_image",
            help: Some("Saves the current image in spi flash"),
        },
        &Item {
            item_type: ItemType::Callback {
                function: on,
                parameters: &[],
            },
            command: "on",
            help: Some("Turn display off"),
        },
        &Item {
            item_type: ItemType::Callback {
                function: off,
                parameters: &[],
            },
            command: "off",
            help: Some("Turn display off"),
        },
        &Item {
            item_type: ItemType::Callback {
                function: get_image_param,
                parameters: &[],
            },
            command: "get_image_param",
            help: Some("Get configured width & length"),
        },
        &Item {
            item_type: ItemType::Callback {
                function: set_image_param,
                parameters: &[
                    Parameter::Mandatory {
                        parameter_name: "width",
                        help: None,
                    },
                    Parameter::Mandatory {
                        parameter_name: "length",
                        help: None,
                    },
                ],
            },
            command: "set_image_param",
            help: Some("Set width & length"),
        },
        &Item {
            item_type: ItemType::Callback {
                function: get_panel_param,
                parameters: &[
                    Parameter::Mandatory {
                        parameter_name: "output",
                        help: None,
                    },
                    Parameter::Mandatory {
                        parameter_name: "chain_num",
                        help: None,
                    },
                ],
            },
            command: "get_panel_param",
            help: Some("Get virtual location of panel in 32 increments"),
        },
        &Item {
            item_type: ItemType::Callback {
                function: set_panel_param,
                parameters: &[
                    Parameter::Mandatory {
                        parameter_name: "output",
                        help: None,
                    },
                    Parameter::Mandatory {
                        parameter_name: "chain_num",
                        help: None,
                    },
                    Parameter::Mandatory {
                        parameter_name: "x",
                        help: Some("x offset in steps of 32"),
                    },
                    Parameter::Mandatory {
                        parameter_name: "y",
                        help: Some("y offset in steps of 32"),
                    },
                    Parameter::Mandatory {
                        parameter_name: "rotation",
                        help: Some("Clockwise rotation in 90° increments"),
                    },
                ],
            },
            command: "set_panel_param",
            help: Some("Set virtual location of panel in 32 increments"),
        },
        &Item {
            item_type: ItemType::Callback {
                function: set_default_panel_params,
                parameters: &[],
            },
            command: "set_default_panel_params",
            help: Some("Sets the default panel parameters"),
        },
    ],
    entry: None,
    exit: None,
};

fn reboot(_menu: &Menu<Context>, _item: &Item<Context>, _args: &[&str], _context: &mut Context) {
    // Safe, because the soc is reset *now*
    unsafe { (*pac::Ctrl::ptr()).reset().write(|w| w.soc_rst().set_bit()) };
}

fn default_image(
    _menu: &Menu<Context>,
    _item: &Item<Context>,
    _args: &[&str],
    context: &mut Context,
) {
    use crate::img;
    let hub75 = &mut context.hub75;
    let image = img::load_default_image();
    hub75.set_img_param(image.0, image.1);
    hub75.write_img_data(0, image.3);
    hub75.set_mode(OutputMode::FullColor);
    hub75.on();
}

fn default_indexed_image(
    _menu: &Menu<Context>,
    _item: &Item<Context>,
    _args: &[&str],
    context: &mut Context,
) {
    use crate::img;
    let hub75 = &mut context.hub75;
    let image = img::load_default_indexed_image();
    hub75.set_img_param(image.0, image.1);
    hub75.write_img_data(0, image.3);
    hub75.set_mode(OutputMode::Indexed);
    hub75.set_palette(0, image.4);
    hub75.on();
}

fn load_spi_image(
    _menu: &Menu<Context>,
    _item: &Item<Context>,
    _args: &[&str],
    context: &mut Context,
) {
    use crate::img;
    let hub75 = &mut context.hub75;
    let image = img::load_image(context.flash.read_image()).unwrap();
    hub75.set_img_param(image.0, image.1);
    hub75.set_panel_params(image.2);
    hub75.write_img_data(0, image.3);
    // TODO indexed
    hub75.on();
}

fn save_spi_image(
    _menu: &Menu<Context>,
    _item: &Item<Context>,
    _args: &[&str],
    context: &mut Context,
) {
    use crate::img;
    let hub75 = &mut context.hub75;
    let (width, length) = hub75.get_img_param();
    let img_data = img::write_image(
        width,
        length,
        hub75.get_panel_params(),
        hub75.read_img_data(),
    )
    .unwrap();
    context.flash.write_image(img_data);
}

fn on(_menu: &Menu<Context>, _item: &Item<Context>, _args: &[&str], context: &mut Context) {
    context.hub75.on();
}

fn off(_menu: &Menu<Context>, _item: &Item<Context>, _args: &[&str], context: &mut Context) {
    context.hub75.off();
}

fn get_image_param(
    _menu: &Menu<Context>,
    _item: &Item<Context>,
    _args: &[&str],
    context: &mut Context,
) {
    let (width, length) = context.hub75.get_img_param();
    writeln!(
        context.output,
        r#"{{"width": {}, "length": {}}}"#,
        width, length
    )
    .unwrap();
}

fn set_image_param(
    _menu: &Menu<Context>,
    item: &Item<Context>,
    args: &[&str],
    context: &mut Context,
) {
    let width: Result<u16, _> = argument_finder(item, args, "width")
        .unwrap()
        .unwrap()
        .parse();
    let length: Result<u32, _> = argument_finder(item, args, "length")
        .unwrap()
        .unwrap()
        .parse();
    if width.is_err() || length.is_err() {
        writeln!(context.output, "Invalid number given").unwrap();
        return;
    }
    context.hub75.set_img_param(width.unwrap(), length.unwrap());
}
fn get_panel_param(
    _menu: &Menu<Context>,
    item: &Item<Context>,
    args: &[&str],
    context: &mut Context,
) {
    let output: Result<u8, _> = argument_finder(item, args, "output")
        .unwrap()
        .unwrap()
        .parse();
    let chain_num: Result<u8, _> = argument_finder(item, args, "chain_num")
        .unwrap()
        .unwrap()
        .parse();
    if output.is_err() || chain_num.is_err() {
        writeln!(context.output, "Invalid number given").unwrap();
        return;
    }
    let (x, y, rotation) = context
        .hub75
        .get_panel_param(output.unwrap(), chain_num.unwrap());
    writeln!(
        context.output,
        r#"{{"x": {}, "y": {}, "rotation": {}}}"#,
        x, y, rotation
    )
    .unwrap();
}
fn set_panel_param(
    _menu: &Menu<Context>,
    item: &Item<Context>,
    args: &[&str],
    context: &mut Context,
) {
    let output: Result<u8, _> = argument_finder(item, args, "output")
        .unwrap()
        .unwrap()
        .parse();
    let chain_num: Result<u8, _> = argument_finder(item, args, "chain_num")
        .unwrap()
        .unwrap()
        .parse();
    let x: Result<u8, _> = argument_finder(item, args, "x").unwrap().unwrap().parse();
    let y: Result<u8, _> = argument_finder(item, args, "y").unwrap().unwrap().parse();
    let rot: Result<u8, _> = argument_finder(item, args, "rotation")
        .unwrap()
        .unwrap()
        .parse();
    if output.is_err() || chain_num.is_err() || x.is_err() || y.is_err() {
        writeln!(context.output, "Invalid number given").unwrap();
        return;
    }
    context.hub75.set_panel_param(
        output.unwrap(),
        chain_num.unwrap(),
        x.unwrap(),
        y.unwrap(),
        rot.unwrap(),
    );
}

fn set_default_panel_params(
    _menu: &Menu<Context>,
    _item: &Item<Context>,
    _args: &[&str],
    context: &mut Context,
) {
    context.hub75.set_panel_param(0, 0, 0, 0, 0);
    context.hub75.set_panel_param(0, 1, 0, 1, 0);
    context.hub75.set_panel_param(0, 2, 2, 0, 0);
    context.hub75.set_panel_param(0, 3, 2, 1, 0);
}

// fn set_mac_ip(_menu: &Menu<Context>, item: &Item<Context>, args: &[&str], context: &mut Context) {
//     let mac_arg: &str = argument_finder(item, args, "mac").unwrap().unwrap();
//     let ip_arg: &str = argument_finder(item, args, "ip").unwrap().unwrap();
//     let mut ip: [u8; 4] = [0, 0, 0, 0];
//     let mut mac: [u8; 6] = [0, 0, 0, 0, 0, 0];
//     for (i, section) in ip_arg.split_on(".").enumerate() {
//         ip[i] = section.parse().unwrap();
//     }
//     for (i, section) in mac_arg.split_on(":").enumerate() {
//         mac[i] = section.parse_hex().unwrap();
//     }
// }
